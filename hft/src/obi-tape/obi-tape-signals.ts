/**
 * OFI / dual-signal matching & clipped execution.
 *
 * Flag byte per ticker:
 *   0b0001 OBI_LONG   0b0010 OBI_SHORT   0b0100 TAPE_BURST   0b1000 LOCKED
 *
 * Default HFT_SIGNAL_MODE=ofi: long = OBI long ∧ micro-price support,
 * tape burst is a VPIN veto not a required AND. dual = old OBI∧tape.
 * Size = Avellaneda–Stoikov lag×inventory haircut; sit out when haircut is thin.
 */
import { AlpacaExecutor } from "../common/alpaca-exec.js";
import { CFG, confidenceNotionalMult, effectiveConfidenceFloor } from "../common/config.js";
import { canEnterBuy, logMarginSkip, marginSnapshot, resolveHftNotionalUsd } from "../common/margin-guard.js";
import { dayTradeBuysHalted, KillSwitch } from "../common/kill-switch.js";
import { nowNs, nsToMs } from "../common/latency.js";
import { fileLogger, stdoutTag } from "../common/logger.js";
import { hftExtendedHoursFlag, hftLimitTif, ordersAllowed, shouldTtlCancelWorking } from "../common/market-session.js";
import { logTradeNewsBlock, tradeNewsAllowsLong, tradeNewsSizingTilt } from "./trade-news.js";
import {
  OPEN_ORDER_STATUSES,
  filledShareQty,
  resolveOrderFill,
  shouldReleasePending,
} from "../common/order-lifecycle.js";
import { issuerCachedLongQty, skipBuyAlreadyLong } from "../common/issuer-siblings.js";
import { L2Book } from "./l2-book.js";
import { bookSpreadOk, chargedSpreadBps, entryLimitPx } from "./order-pricing.js";
import { TapeVelocity } from "./tape-velocity.js";
import { flowIsSellToxic, microPriceDriftBps, microPriceSupportsLong } from "./micro-price.js";
import { execDelayFeeBps, effectiveBudgetMs } from "./exec-delay.js";
import { CircuitBreaker } from "../common/circuit-breaker.js";
import { fuseObiMicro, fuseObiTape, shouldEnterEv } from "./trade-ev.js";
import { sizeHftClip } from "./firm-risk.js";
import { resolveSignalMode, signalConfidence, wantsDirection } from "./signal-mode.js";

const log = stdoutTag("[OBI/EXEC]");

export const F_OBI_LONG = 0b0001;
export const F_OBI_SHORT = 0b0010;
export const F_TAPE_BURST = 0b0100;
export const F_LOCKED = 0b1000;

let orderCounter = 0;
function nextClientOrderId(): string {
  orderCounter = (orderCounter + 1) | 0;
  return `obi-${Date.now().toString(36)}-${orderCounter}`;
}

export type Position = {
  ticker: string;
  side: "buy" | "sell";
  entryPx: number;
  qty: number;
  brokerId: string;
  openedMs: number;
};

export class ObiTapeSignals {
  /** Per-ticker flag byte, indexed by ticker (Uint8 cheap to read). */
  private readonly flags = new Map<string, number>();
  /** Open position per ticker (single shot per cooldown). */
  readonly openPositions = new Map<string, Position>();
  private readonly pending = new Set<string>();
  private inFlightOrders = 0;
  private readonly maxInFlight = Number(process.env.HFT_MAX_IN_FLIGHT_ORDERS ?? 48);

  constructor(
    private readonly broker: AlpacaExecutor,
    private readonly kill: KillSwitch,
    private readonly circuit: CircuitBreaker = new CircuitBreaker(),
  ) {}

  /** Called from L2Book listener after refresh. */
  onObi(book: L2Book): void {
    const t = book.ticker;
    let f = this.flags.get(t) ?? 0;
    if (book.obi > CFG.obi.triggerLong) f |= F_OBI_LONG; else f &= ~F_OBI_LONG;
    if (book.obi < CFG.obi.triggerShort) f |= F_OBI_SHORT; else f &= ~F_OBI_SHORT;
    this.flags.set(t, f);
  }

  /** Called from TapeVelocity after each trade. */
  onTape(t: string, burst: boolean): void {
    let f = this.flags.get(t) ?? 0;
    if (burst) f |= F_TAPE_BURST; else f &= ~F_TAPE_BURST;
    this.flags.set(t, f);
  }

  hasExposure(ticker: string): boolean {
    const t = ticker.toUpperCase();
    return this.openPositions.has(t) || this.pending.has(t);
  }

  /** Mark-to-entry HFT inventory — used to sit out before the whole book is in. */
  hftInventoryUsd(): number {
    let s = 0;
    for (const p of this.openPositions.values()) s += p.qty * p.entryPx;
    return s;
  }

  /** After restart: adopt broker longs so we don't re-buy / bag the same names. */
  adoptBrokerLong(
    ticker: string,
    qty: number,
    entryPx: number,
    openedMs = Date.now(),
  ): void {
    const t = ticker.toUpperCase();
    if (!(qty > 0) || !(entryPx > 0)) return;
    if (this.openPositions.has(t)) return;
    this.openPositions.set(t, {
      ticker: t,
      side: "buy",
      entryPx,
      qty: Math.max(1, Math.floor(qty)),
      brokerId: "adopted",
      openedMs,
    });
  }

  /** Resting DAY buy on the book — block another FIRE until it fills or dies. */
  adoptWorkingBuy(ticker: string): void {
    const t = ticker.toUpperCase();
    if (!t || this.openPositions.has(t)) return;
    this.pending.add(t);
  }

  private async watchWorkingEntry(
    t: string,
    orderId: string,
    qty: number,
    fillPx: number,
    side: "buy" | "sell",
  ): Promise<void> {
    const pollMs = Number(process.env.HFT_ORDER_STATUS_POLL_MS ?? 400);
    const maxMs = Number(process.env.HFT_ENTRY_WORKING_TTL_MS ?? 180_000);
    const t0 = Date.now();
    try {
      while (Date.now() - t0 < maxMs) {
        const later = await resolveOrderFill(this.broker, orderId, qty, {
          timeoutMs: Math.min(15_000, Math.max(500, maxMs - (Date.now() - t0))),
          pollMs,
          cancelIfUnfilled: false,
        });
        if (later.filled && later.filledQty > 0) {
          const laterPx =
            later.filledAvgPrice && later.filledAvgPrice > 0 ? later.filledAvgPrice : fillPx;
          this.openPositions.set(t, {
            ticker: t,
            side,
            entryPx: laterPx,
            qty: filledShareQty(later.filledQty),
            brokerId: orderId,
            openedMs: Date.now(),
          });
          this.kill.lock(t, Date.now());
          return;
        }
        if (shouldReleasePending(later)) {
          if (later.canceled || filledShareQty(later.filledQty) <= 0) {
            void this.broker.cancelHftExits(t);
          }
          const missCd = Number(
            process.env.HFT_ENTRY_MISS_COOLDOWN_MS ??
              process.env.HFT_PER_TICKER_COOLDOWN_MS ??
              8_000,
          );
          this.kill.lock(t, Date.now() + Math.max(0, missCd - this.kill.cooldownMs));
          return;
        }
      }
      log("entry-working-hold", { ticker: t, orderId, heldMs: Date.now() - t0 });
      try {
        const snap = await this.broker.getOrder(orderId);
        if (snap && OPEN_ORDER_STATUSES.has(snap.status)) {
          const fq = filledShareQty(snap.filledQty);
          if (fq > 1e-8) {
            const laterPx =
              snap.filledAvgPrice && snap.filledAvgPrice > 0 ? snap.filledAvgPrice : fillPx;
            this.openPositions.set(t, {
              ticker: t,
              side,
              entryPx: laterPx,
              qty: fq,
              brokerId: orderId,
              openedMs: Date.now(),
            });
            this.kill.lock(t, Date.now());
          }
          if (shouldTtlCancelWorking()) {
            await this.broker.cancel(orderId);
            log("entry-working-ttl-cancel", { ticker: t, orderId, filledQty: fq });
          } else {
            log("entry-working-ttl-rest", { ticker: t, orderId, filledQty: fq });
          }
        }
      } catch {
        /* leave the ticket if status is unknown */
      }
    } finally {
      if (this.openPositions.has(t)) {
        this.pending.delete(t);
        return;
      }
      try {
        const snap = await this.broker.getOrder(orderId);
        const working = Boolean(snap && OPEN_ORDER_STATUSES.has(snap.status));
        if (!working) this.pending.delete(t);
      } catch {
        /* keep pending on status errors — fail closed vs duplicate FIRE */
      }
    }
  }

  /** Returns true if a fire was attempted (regardless of broker result). */
  maybeFire(
    book: L2Book,
    tape: TapeVelocity,
    processStartNs: bigint,
    onWs = false,
  ): boolean {
    if (process.env.HFT_OBI_ENABLED === "false" || process.env.HFT_JP_CANDLE_ONLY === "true") {
      return false;
    }
    if (this.circuit.isTripped()) return false;
    const t = book.ticker;
    const f = this.flags.get(t) ?? 0;

    const longOnly = process.env.HFT_LONG_ONLY !== "false";
    const mode = resolveSignalMode();
    const microOk =
      process.env.HFT_MICRO_PRICE_GATE === "false" || microPriceSupportsLong(book);
    const { long: wantLong, short: wantShort } = wantsDirection(
      mode,
      longOnly,
      {
        obiLong: (f & F_OBI_LONG) !== 0,
        obiShort: (f & F_OBI_SHORT) !== 0,
        tapeBurst: (f & F_TAPE_BURST) !== 0,
      },
      { microOk, sellToxic: process.env.HFT_VPIN_GATE !== "false" && flowIsSellToxic(book, tape) },
    );
    let long = wantLong;
    let short = wantShort;
    // IEX top-of-book is often 1×1 → OBI=0, so OFI/OR never trip. Pace-fill
    // spends leftover same-day BP up to the 200/min Alpaca cap on unheld names.
    const paceFill = process.env.HFT_PACE_FILL === "true";
    if (!long && !short && paceFill && longOnly) {
      long = book.bestBid > 0 && book.bestAsk > 0 && book.bestAsk >= book.bestBid;
    }
    if (!long && !short) return false;
    // Day-loss halt (shared with fortress): no new longs; shorts already gated by longOnly.
    if (long && dayTradeBuysHalted()) return false;

    const skipBudget = process.env.HFT_SKIP_LATENCY_BUDGET === "true";
    // Local proc is ~8–15ms; raw OBI_BUDGET_LATENCY_MS=8 false-missed every fire.
    // effectiveBudgetMs folds measured Alpaca RTT so WiFi/VPN isn't a skip-all.
    const budgetMs = effectiveBudgetMs(Number(process.env.OBI_BUDGET_LATENCY_MS ?? CFG.obi.budgetMs));
    if (!skipBudget) {
      const procMs = nsToMs(nowNs() - processStartNs);
      if (procMs > budgetMs) {
        fileLogger.emit("obi_budget_miss", { ticker: t, procMs, budgetMs });
        return false;
      }
    }

    const nowMs = Date.now();
    if (this.kill.isLocked(t, nowMs)) return false;
    if (long && process.env.HFT_BLOCK_ADD_TO_BROKER_LONG !== "false") {
      if (!this.broker.positionsReady()) return false;
      const live = issuerCachedLongQty((s) => this.broker.cachedLongQty(s), t);
      const maxQty = Number(process.env.HFT_MAX_BROKER_QTY_PER_SYMBOL ?? 0);
      if (skipBuyAlreadyLong(live, maxQty)) {
        this.kill.lock(t, nowMs);
        return false;
      }
    }
    if (this.inFlightOrders >= this.maxInFlight) return false;

    if (long && !tradeNewsAllowsLong(t)) {
      logTradeNewsBlock(t);
      return false;
    }

    const side: "buy" | "sell" = long ? "buy" : "sell";
    if (!ordersAllowed(side)) return false;
    if (this.openPositions.has(t) || this.pending.has(t)) return false;
    if (!bookSpreadOk(book)) return false;
    if (book.syntheticNbbo && process.env.HFT_ALLOW_SYNTHETIC_NBBO !== "true") {
      fileLogger.emit("obi_synth_skip", { ticker: t, bid: book.bestBid, ask: book.bestAsk });
      return false;
    }

    const obiStrength = Math.min(1, Math.abs(book.obi));
    const burstStrength = Math.min(1, tape.lastBurstRatio / (2 * CFG.obi.velocityMult));
    const microStrength = Math.min(1, Math.max(0, microPriceDriftBps(book) / 8));
    const strictDual = mode === "dual" && process.env.HFT_STRICT_DUAL_SIGNAL !== "false";
    const minDual = Number(process.env.HFT_MIN_DUAL_STRENGTH ?? 0.55);
    if (strictDual && (obiStrength < minDual || burstStrength < minDual)) return false;
    let conf = signalConfidence(mode, obiStrength, burstStrength, microStrength, strictDual);
    if (paceFill) conf = Math.max(conf, effectiveConfidenceFloor());
    const minObi = Number(process.env.HFT_MIN_OBI_STRENGTH ?? 0);
    if (minObi > 0 && obiStrength < minObi) return false;
    const sizeMult = confidenceNotionalMult(conf);
    if (sizeMult <= 0) return false;

    const newsTilt = tradeNewsSizingTilt(t);
    if (newsTilt <= 0) {
      logTradeNewsBlock(t);
      return false;
    }

    const tick = Number(process.env.HFT_TICK_SIZE ?? 0.01);
    const tpTicks = Number(process.env.HFT_TAKE_PROFIT_TICKS ?? 4);
    const mid = book.mid > 0 ? book.mid : (book.bestBid + book.bestAsk) / 2;
    if (!(mid > 0)) return false;
    const edgeBps = ((tpTicks * tick) / mid) * 10_000;
    const sBps = chargedSpreadBps(book);
    const feeBps = Number(process.env.HFT_FEE_BPS ?? 1) + execDelayFeeBps();
    const required = sBps + feeBps;
    // Edge vs cost: TP ticks vs charged spread (capped) + fee. Full IEX/REST
    // width double-counted sanitized books and skipped every name except pennies.
    if (process.env.HFT_OBI_EDGE_COST_GATE !== "false") {
      if (!(edgeBps >= required)) {
        fileLogger.emit("obi_edge_skip", { ticker: t, edgeBps, spreadBps: sBps, required, feeBps });
        return false;
      }
    }

    const pUp =
      mode === "ofi"
        ? fuseObiMicro(book.obi, microPriceDriftBps(book))
        : fuseObiTape(book.obi, tape.lastBurstRatio, CFG.obi.velocityMult);
    const minEv = Number(process.env.HFT_MIN_EV_BPS ?? 0.4);
    const minP = Number(process.env.HFT_EV_MIN_P ?? 0.52);
    const evGate = shouldEnterEv(pUp, edgeBps, required, minEv, minP);
    if (process.env.HFT_EV_GATE !== "false" && !evGate.ok) {
      fileLogger.emit("obi_ev_skip", {
        ticker: t,
        pUp: evGate.p,
        evBps: evGate.evBps,
        minEv,
        costBps: required,
        tpBps: edgeBps,
      });
      return false;
    }

    const refPx = side === "buy" ? book.bestAsk : book.bestBid;
    if (!(refPx > 0)) return false;
    const ageMs = Math.max(0, Date.now() - (book.lastUpdateMs || Date.now()));
    const eq =
      marginSnapshot()?.equity ?? Number(process.env.HFT_EQUITY_FALLBACK_USD ?? 70_000);
    const clip = sizeHftClip({
      baseUsd: resolveHftNotionalUsd(CFG.obi.notional) * sizeMult * newsTilt,
      quoteAgeMs: ageMs,
      hftInventoryUsd: this.hftInventoryUsd(),
      equityUsd: eq,
    });
    if (clip.sitOut || !(clip.notional > 0)) {
      fileLogger.emit("obi_lag_sitout", {
        ticker: t,
        haircut: clip.haircut,
        lag: clip.lag,
        inv: clip.inv,
        ageMs,
        notional: clip.notional,
      });
      return false;
    }
    const notional = clip.notional;
    if (side === "buy") {
      const marginOk = canEnterBuy(notional);
      if (!marginOk.ok) {
        logMarginSkip(t, marginOk.reason || "bp");
        return false;
      }
    }
    const qty = Math.floor(notional / Math.max(refPx, 1));
    if (!(qty >= 1)) {
      fileLogger.emit("obi_qty_skip", { ticker: t, notional, refPx });
      return false;
    }

    const extended = hftExtendedHoursFlag();
    const useMarket = process.env.HFT_USE_MARKET_ORDERS === "true";
    const limitPx = useMarket ? undefined : entryLimitPx(side, book) ?? undefined;
    if (!useMarket && limitPx == null) return false;
    book.entryRef = book.mid;

    // Reserve the 60s budget only after every quality gate — failed dual/spread
    // used to burn 24 slots/min and starve real fires.
    if (!this.kill.reserveOrderSlot(nowMs)) return false;

    this.pending.add(t);
    log("FIRE", {
      ticker: t,
      side,
      px: refPx,
      qty,
      obi: book.obi,
      burst: tape.lastBurstRatio,
      conf,
      pUp: evGate.p,
      evBps: evGate.evBps,
      notional,
      haircut: clip.haircut,
      lag: clip.lag,
      inv: clip.inv,
      mode,
      orderType: useMarket ? "market" : "limit-ext",
      limitPx,
    });

    const decisionNs = nowNs();
    this.inFlightOrders++;
    void this.placeEntry(
      t,
      side,
      qty,
      limitPx,
      useMarket,
      extended,
      nowMs,
      refPx,
      {
        obi: book.obi,
        burst: tape.lastBurstRatio,
        conf,
        notional,
      },
      processStartNs,
      decisionNs,
      book,
    );
    return true;
  }

  private async placeEntry(
    t: string,
    side: "buy" | "sell",
    qty: number,
    limitPx: number | undefined,
    useMarket: boolean,
    extended: boolean,
    nowMs: number,
    refPx: number,
    meta: { obi: number; burst: number; conf: number; notional: number },
    packetNs: bigint,
    decisionNs: bigint,
    book: L2Book,
  ): Promise<void> {
    const orderId = nextClientOrderId();
    const entryFillMs = Number(process.env.HFT_ENTRY_FILL_MS ?? 6000);
    const cancelEntry = process.env.HFT_CANCEL_ENTRY_UNFILLED === "true";
    let keepPending = false;
    try {
      // Never add to an existing broker long — restart bagging was the bleed
      // (local map empty → more buys on AAPL/AMZN while inventory sat red).
      if (side === "buy" && process.env.HFT_BLOCK_ADD_TO_BROKER_LONG !== "false") {
        const live = issuerCachedLongQty((s) => this.broker.cachedLongQty(s), t);
        const maxQty = Number(process.env.HFT_MAX_BROKER_QTY_PER_SYMBOL ?? 0);
        if (skipBuyAlreadyLong(live, maxQty)) {
          fileLogger.emit("obi_skip_already_long", { ticker: t, liveQty: live, issuer: true });
          this.kill.lock(t, Date.now());
          return;
        }
      }
      this.broker.registerNbbo(t, book.bestBid, book.bestAsk);
      const orderNs = nowNs();
      const resp = await this.broker.place({
        symbol: t,
        side,
        qty,
        type: useMarket ? "market" : "limit",
        time_in_force: hftLimitTif(),
        limit_price: limitPx,
        extended_hours: extended,
        client_order_id: orderId,
      });

      if (!resp.ok || !resp.id) {
        log("place-reject", {
          ticker: t,
          status: resp.status,
          reason: resp.reject_reason?.slice(0, 120),
        });
        // Alpaca 429 — lock ticker longer so we don't stampede the rate limit.
        const st = Number(resp.status);
        if (st === 429 || String(resp.reject_reason || "").includes("429")) {
          const backoff = Number(process.env.HFT_RATE_LIMIT_BACKOFF_MS ?? 20_000);
          // lock() sets unlockAt = nowMs + cooldownMs — shift nowMs so total wait ≈ backoff.
          this.kill.lock(t, Date.now() + Math.max(0, backoff - this.kill.cooldownMs));
        } else {
          const missCd = Number(
            process.env.HFT_ENTRY_MISS_COOLDOWN_MS ??
              process.env.HFT_PER_TICKER_COOLDOWN_MS ??
              8_000,
          );
          this.kill.lock(t, Date.now() + Math.max(0, missCd - this.kill.cooldownMs));
        }
        return;
      }

      let filled = false;
      let fillPx = refPx;
      let fillQty = 0;

      const resolved = await resolveOrderFill(this.broker, resp.id, qty, {
        timeoutMs: entryFillMs,
        cancelIfUnfilled: cancelEntry,
      });
      filled = resolved.filled && resolved.filledQty > 0;
      fillQty = filledShareQty(resolved.filledQty);
      if (resolved.filledAvgPrice && resolved.filledAvgPrice > 0) {
        fillPx = resolved.filledAvgPrice;
      }
      if (!filled && resolved.working) {
        log("entry-working", { ticker: t, status: resolved.status, crossesMinute: true });
        keepPending = true;
        void this.watchWorkingEntry(t, resp.id, qty, fillPx, side);
      } else if (!filled) {
        log("entry-expired", {
          ticker: t,
          status: resolved.status,
          canceled: resolved.canceled,
        });
        if (resolved.canceled || fillQty <= 0) void this.broker.cancelHftExits(t);
        // Lock on ANY miss (IOC expire, cancel, timeout). 250ms retry of the
        // same name was the cancel→same-trade loop.
        const missCd = Number(
          process.env.HFT_ENTRY_MISS_COOLDOWN_MS ??
            process.env.HFT_PER_TICKER_COOLDOWN_MS ??
            8_000,
        );
        this.kill.lock(t, Date.now() + Math.max(0, missCd - this.kill.cooldownMs));
      }

      const procMs = Number((orderNs - packetNs) / 1_000_000n);
      const decisionMs = Number((decisionNs - packetNs) / 1_000_000n);
      const orderMs = Number((nowNs() - orderNs) / 1_000_000n);
      fileLogger.emit("obi_fire", {
        ticker: t,
        side,
        px: refPx,
        qty: fillQty,
        ...meta,
        ok: resp.ok,
        status: resp.status,
        orderStatus: resp.orderStatus,
        filled,
        brokerId: resp.id,
        wireUs: resp.latencyUs,
        packetNs: packetNs.toString(),
        decisionNs: decisionNs.toString(),
        orderNs: orderNs.toString(),
        exchangeTsMs: book.lastExchangeTsMs,
        procMs,
        decisionMs,
        orderMs,
        simFill: resp.simulated ?? false,
        expectedFillPx: resp.expectedFillPx,
        slippageBps: resp.slippageBps,
      });

      if (filled) {
        this.openPositions.set(t, {
          ticker: t,
          side,
          entryPx: fillPx,
          qty: fillQty,
          brokerId: resp.id,
          // Hold clock starts at fill confirm — not signal time (signal→fill wait
          // was eating max-hold and causing instant flats).
          openedMs: Date.now(),
        });
        this.kill.lock(t, Date.now());
      }
    } catch (err) {
      log("place-error", err instanceof Error ? err.message : err);
    } finally {
      if (!keepPending) this.pending.delete(t);
      this.inFlightOrders = Math.max(0, this.inFlightOrders - 1);
    }
  }
}
