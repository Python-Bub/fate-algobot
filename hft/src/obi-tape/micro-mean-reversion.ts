/**
 * Micro-mean-reversion scalper — buy tiny dips, SELL back out (HFT = round trip).
 */

import { AlpacaExecutor, type OrderResponse, type TimeInForce } from "../common/alpaca-exec.js";
import { CFG, confidenceNotionalMult } from "../common/config.js";
import { CircuitBreaker } from "../common/circuit-breaker.js";
import { dayTradeBuysHalted, KillSwitch } from "../common/kill-switch.js";
import { currentSession, hftExtendedHoursFlag, hftExitTif, hftLimitTif, ordersAllowed, shouldTtlCancelWorking } from "../common/market-session.js";
import { nowNs, nsToMs } from "../common/latency.js";
import { fileLogger, stdoutTag } from "../common/logger.js";
import {
  OPEN_ORDER_STATUSES,
  entryFilledQty,
  filledShareQty,
  isHftExitClientId,
  resolveOrderFill,
  shouldReleasePending,
} from "../common/order-lifecycle.js";
import { issuerCachedLongQty, skipBuyAlreadyLong } from "../common/issuer-siblings.js";

import {
  CandleBuilder,
  PAT_HAMMER,
  PAT_BULLISH_ENGULF,
  PAT_INV_HAMMER,
  PAT_SHOOTING_STAR,
  PAT_BEARISH_ENGULF,
  PAT_HANGING_MAN,
  patternBias,
  patternName,
} from "./jp-candles.js";
import { L2Book } from "./l2-book.js";
import {
  entryLimitPx,
  exitLimitPx,
  flattenDebounceMs,
  flattenQuoteOk,
  isInGreen,
  chargedSpreadBps,
  sellLimitUnfillable,
  spreadBps,
  bookSpreadOk,
} from "./order-pricing.js";
import { canEnterBuy, logMarginSkip, marginSnapshot, resolveHftNotionalUsd } from "../common/margin-guard.js";
import { isEarnedSymbol, mrTimingFor } from "./profit-cushion-gate.js";
import {
  logTradeNewsBlock,
  tradeNewsAllowsLong,
  tradeNewsHeadline,
  tradeNewsLogFields,
  tradeNewsSentiment,
  tradeNewsSizingTilt,
} from "./trade-news.js";
import { flowIsSellToxic, microPriceSupportsLong } from "./micro-price.js";
import { upwardProbability, shouldEnterLong } from "./microstructure-prob.js";
import { execDelayFeeBps, effectiveBudgetMs } from "./exec-delay.js";
import { TapeVelocity } from "./tape-velocity.js";
import { sizeHftClip } from "./firm-risk.js";

const log = stdoutTag("[OBI/MR]");

let counter = 0;
function nextId(): string {
  counter = (counter + 1) | 0;
  return `mr-${Date.now().toString(36)}-${counter}`;
}

interface MeanRevPosition {
  ticker: string;
  side: "buy" | "sell";
  entryPx: number;
  qty: number;
  brokerId: string;
  openedMs: number;
  patternName: string;
}

export class MicroMeanReversion {
  private readonly open = new Map<string, MeanRevPosition>();
  private readonly pending = new Set<string>();
  private readonly flattening = new Set<string>();
  private readonly nextFireOkMs = new Map<string, number>();
  private readonly lastFlattenAttemptMs = new Map<string, number>();

  public readonly mrExitMs: number = Number(process.env.HFT_MR_EXIT_MS ?? 5000);
  public readonly dipPctTrigger: number = Number(process.env.HFT_MR_DIP_PCT ?? 0.0015);
  public readonly mrDebounceMs: number = Number(process.env.HFT_MR_DEBOUNCE_MS ?? 8000);

  constructor(
    private readonly broker: AlpacaExecutor,
    private readonly kill: KillSwitch,
    private readonly getBook: (ticker: string) => L2Book | undefined,
    private readonly circuit: CircuitBreaker = new CircuitBreaker(),
  ) {}

  hasExposure(ticker: string): boolean {
    const t = ticker.toUpperCase();
    return this.open.has(t) || this.pending.has(t) || this.flattening.has(t);
  }

  /** Resting DAY buy on the book — block another FIRE until it fills or dies. */
  adoptWorkingBuy(ticker: string): void {
    const t = ticker.toUpperCase();
    if (!t || this.open.has(t)) return;
    this.pending.add(t);
  }

  private async watchWorkingEntry(
    t: string,
    orderId: string,
    qty: number,
    px: number,
    side: "buy" | "sell",
    meta: { pattern: string; conf: number; dipDist: number; spreadBps: number },
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
          const fillPx =
            later.filledAvgPrice && later.filledAvgPrice > 0 ? later.filledAvgPrice : px;
          this.open.set(t, {
            ticker: t,
            side,
            entryPx: fillPx,
            qty: filledShareQty(later.filledQty),
            brokerId: orderId,
            openedMs: Date.now(),
            patternName: meta.pattern,
          });
          this.kill.lock(t, Date.now());
          return;
        }
        if (shouldReleasePending(later)) {
          if (later.canceled || filledShareQty(later.filledQty) <= 0) {
            void this.broker.cancelHftExits(t);
          }
          const backoff = Number(
            process.env.HFT_ENTRY_MISS_COOLDOWN_MS ??
              process.env.HFT_ENTRY_BACKOFF_MS ??
              45_000,
          );
          this.nextFireOkMs.set(t, Date.now() + backoff);
          this.kill.lock(t, Date.now() + Math.max(0, backoff - this.kill.cooldownMs));
          return;
        }
      }
      log("entry-working-hold", { ticker: t, orderId, heldMs: Date.now() - t0 });
      try {
        const snap = await this.broker.getOrder(orderId);
        if (snap && OPEN_ORDER_STATUSES.has(snap.status)) {
          const fq = filledShareQty(snap.filledQty);
          if (fq > 1e-8) {
            const fillPx =
              snap.filledAvgPrice && snap.filledAvgPrice > 0 ? snap.filledAvgPrice : px;
            this.open.set(t, {
              ticker: t,
              side,
              entryPx: fillPx,
              qty: fq,
              brokerId: orderId,
              openedMs: Date.now(),
              patternName: meta.pattern,
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
      if (this.open.has(t)) {
        this.pending.delete(t);
        return;
      }
      try {
        const snap = await this.broker.getOrder(orderId);
        const working = Boolean(snap && OPEN_ORDER_STATUSES.has(snap.status));
        if (!working) this.pending.delete(t);
      } catch {
        /* keep pending on status errors */
      }
    }
  }

  /** Every book tick: fire exit the moment bid/ask crosses into profit. */
  monitor(book: L2Book): void {
    const t = book.ticker.toUpperCase();
    const pos = this.open.get(t);
    if (!pos || this.flattening.has(t)) return;
    if (!(book.bestBid > 0 && book.bestAsk > 0)) return;
    if (!flattenQuoteOk(book)) return;

    const { exitMs, debounceMs } = mrTimingFor(t, this.mrExitMs, this.mrDebounceMs);
    const maxHoldMs = Number(process.env.HFT_MR_MAX_HOLD_MS ?? 12_000);
    const stopPct = Number(process.env.HFT_MR_STOP_PCT ?? 0.0015);
    const heldMs = Date.now() - pos.openedMs;

    // 1) Hard stop-loss → forced exit (protect capital). Disabled when stop pct <= 0.
    if (stopPct > 0 && pos.entryPx > 0) {
      const adverse =
        pos.side === "buy"
          ? (pos.entryPx - book.bestBid) / pos.entryPx
          : (book.bestAsk - pos.entryPx) / pos.entryPx;
      // Require adverse move to clear the live spread so we don't stop inside it.
      const spreadFrac =
        book.bestAsk > book.bestBid && book.mid > 0
          ? (book.bestAsk - book.bestBid) / book.mid
          : 0;
      if (adverse >= Math.max(stopPct, spreadFrac + stopPct)) {
        void this.flatten(pos, debounceMs, exitMs, true);
        return;
      }
    }

    // 2) Max-hold — sell-high / wait-for-green, never bid-dump (same bleed as OBI).
    if ((maxHoldMs > 0 && heldMs >= maxHoldMs) || process.env.HFT_FORCE_FLATTEN === "true") {
      const force =
        process.env.HFT_FORCE_FLATTEN === "true" ||
        process.env.HFT_MR_FORCE_MAX_HOLD === "true";
      void this.flatten(pos, debounceMs, exitMs, force);
      return;
    }

    // 3) Profit target → passive sell-high limit at the ask. Honour a minimum
    //    hold so a 1-tick wiggle can't trigger an immediate flip-flop round
    //    trip (the dominant churn source). Stops + max-hold above still fire
    //    immediately. Reversible via HFT_MR_MIN_HOLD_MS=0.
    const minHoldMs = Number(process.env.HFT_MR_MIN_HOLD_MS ?? 4000);
    if (heldMs >= minHoldMs && isInGreen(pos.side, pos.entryPx, book)) {
      void this.flatten(pos, debounceMs, exitMs, false);
    }
  }

  maybeFire(
    candles: CandleBuilder,
    book: L2Book,
    tape: TapeVelocity,
    processStartNs: bigint,
    candleJustClosed = false,
    chartVote?: { score: number; nAgree: number; bias: -1 | 0 | 1; crossFamily?: boolean },
  ): boolean {
    const t = book.ticker.toUpperCase();
    if (this.circuit.isTripped()) return false;
    if (this.hasExposure(t)) return false;
    if (book.syntheticNbbo && process.env.HFT_ALLOW_SYNTHETIC_NBBO !== "true") return false;
    if (!isEarnedSymbol(t)) return false;

    const candleOnly = process.env.HFT_JP_CANDLE_ONLY === "true";
    const fireOnClose = process.env.HFT_JP_FIRE_ON_CLOSE !== "false";
    if ((candleOnly || fireOnClose) && !candleJustClosed) return false;

    const nowMs = Date.now();
    const { exitMs, debounceMs } = mrTimingFor(t, this.mrExitMs, this.mrDebounceMs);
    const lockUntil = this.nextFireOkMs.get(t) ?? 0;
    if (nowMs < lockUntil) return false;
    if (this.kill.isLocked(t, nowMs)) return false;
    if (!bookSpreadOk(book)) return false;

    const skipBudget = process.env.HFT_SKIP_LATENCY_BUDGET === "true";
    const procMs = nsToMs(nowNs() - processStartNs);
    if (!skipBudget && procMs > effectiveBudgetMs(CFG.obi.budgetMs)) return false;

    const trend = candles.recentTrend(5);
    const pattern = candles.lastPattern;
    const vwap = tape.vwap.vwap();
    const lastClose = candles.liveClose;
    if (!(vwap > 0 && lastClose > 0 && book.bestBid > 0 && book.bestAsk > 0)) return false;

    const bullishPattern =
      pattern === PAT_HAMMER || pattern === PAT_BULLISH_ENGULF || pattern === PAT_INV_HAMMER;
    const bearishPattern =
      pattern === PAT_SHOOTING_STAR || pattern === PAT_BEARISH_ENGULF || pattern === PAT_HANGING_MAN;
    const dipBelowVwap = (vwap - lastClose) / vwap > this.dipPctTrigger;
    const popAboveVwap = (lastClose - vwap) / vwap > this.dipPctTrigger;

    const minObiLong = Number(process.env.HFT_MR_MIN_OBI_LONG ?? 0.15);
    const minObiShort = Number(process.env.HFT_MR_MIN_OBI_SHORT ?? -0.15);
    const restExtended =
      process.env.HFT_MR_REST_EXTENDED !== "false" &&
      process.env.HFT_TRADE_SESSION === "extended" &&
      currentSession() !== "regular";
    const effMinObiLong = restExtended
      ? Number(process.env.HFT_MR_REST_MIN_OBI_LONG ?? -0.99)
      : minObiLong;
    const requirePattern = restExtended
      ? process.env.HFT_MR_REST_REQUIRE_PATTERN === "true"
      : process.env.HFT_MR_REQUIRE_PATTERN !== "false";
    const jpUltra = process.env.HFT_JP_ULTRA === "true";
    const longOnly = process.env.HFT_LONG_ONLY !== "false";
    const reversalTrend = process.env.HFT_JP_REVERSAL_TREND !== "false";
    // Hammer / engulf = buy the dip after downtrend (matches jp_candles.py).
    const trendOkLong = restExtended
      ? true
      : bullishPattern && reversalTrend
        ? trend < 0
        : jpUltra
          ? trend >= 0
          : trend > 0;
    const trendOkShort = restExtended
      ? true
      : bearishPattern && reversalTrend
        ? trend > 0
        : jpUltra
          ? trend <= 0
          : trend < 0;
    const dipScalp = process.env.HFT_DIP_SCALP !== "false";
    const patternOkLong = bullishPattern && (!candleOnly || bullishPattern);
    const patternOkShort = bearishPattern && (!candleOnly || bearishPattern);
    const useMicroProb = process.env.HFT_MICROSTRUCTURE_PROB !== "false";
    const tapeBurst = tape.lastBurstRatio >= Number(process.env.TAPE_VELOCITY_MULTIPLIER ?? 2.5);
    const microIn = {
      book,
      tape,
      trend,
      vwap,
      lastClose,
      newsSentiment: tradeNewsSentiment(t),
      jpBias: patternBias(candles.lastPattern),
      chartScore: chartVote?.score,
      chartAgree: chartVote?.nAgree,
      chartCrossFamily: chartVote?.crossFamily,
      indexTilt: (() => {
        const idx = this.getBook("SPY") ?? this.getBook("QQQ");
        return idx && Number.isFinite(idx.obi) ? idx.obi : undefined;
      })(),
    };
    let goLong =
      trendOkLong &&
      book.obi > effMinObiLong &&
      (patternOkLong || (dipScalp && dipBelowVwap) || (!requirePattern && !candleOnly && dipBelowVwap));
    let goShort =
      !longOnly &&
      trendOkShort &&
      book.obi < minObiShort &&
      (patternOkShort || (!requirePattern && !candleOnly && popAboveVwap));
    if (useMicroProb) {
      const upP = upwardProbability(microIn, tapeBurst);
      const minP = Number(process.env.HFT_MICRO_MIN_UP_PROB ?? 0.52);
      goLong = goLong && upP >= minP;
      goShort = goShort && upP <= 1 - minP;
      if (!goLong && !goShort && upP >= minP && trendOkLong && book.obi > effMinObiLong) {
        goLong = shouldEnterLong(microIn, tapeBurst);
      }
    }
    if (!goLong && !goShort) return false;
    if (goLong && dayTradeBuysHalted()) {
      if (!goShort) return false;
      goLong = false;
    }
    if (goLong && process.env.HFT_BLOCK_ADD_TO_BROKER_LONG !== "false") {
      if (!this.broker.positionsReady()) return false;
      const live = issuerCachedLongQty((s) => this.broker.cachedLongQty(s), t);
      if (skipBuyAlreadyLong(live, 0)) {
        this.kill.lock(t, Date.now());
        return false;
      }
    }

    // Hard-stop favorite index ETF churn (SPY/QQQ/IWM/…). Fortress already bans these;
    // HFT must too — otherwise rotator keeps rebuying soy-like favorites.
    if (goLong) {
      const banOn =
        process.env.HFT_BAN_INDEX_BUYS !== "false" &&
        process.env.FORTRESS_BAN_INDEX_BUYS !== "false";
      if (banOn) {
        const banRaw =
          process.env.HFT_BAN_INDEX_ETFS ||
          process.env.FORTRESS_BAN_INDEX_ETFS ||
          "SPY,QQQ,IWM,DIA,VOO,VTI,SOXX,XLK,XLF,XLE";
        const banned = new Set(
          banRaw
            .split(",")
            .map((s) => s.trim().toUpperCase())
            .filter(Boolean),
        );
        if (banned.has(t)) {
          fileLogger.emit("mr_ban_index", { ticker: t, reason: "banned_index_etf" });
          return false;
        }
      }
      const noRebuyRaw =
        process.env.FORTRESS_NO_REBUY_SYMBOLS || "SPY,QQQ,IWM,DIA,VOO,VTI,SOXX,XLK,XLF,XLE";
      const noRebuy = new Set(
        noRebuyRaw
          .split(",")
          .map((s) => s.trim().toUpperCase())
          .filter(Boolean),
      );
      if (noRebuy.has(t)) {
        // Skip if this HFT sleeve already has an open MR leg (broker-held check in placeEntry).
        if (this.open.has(t) || this.pending.has(t)) {
          fileLogger.emit("mr_no_rebuy", { ticker: t, reason: "index_already_held_open" });
          return false;
        }
      }
    }

    if (goLong && process.env.HFT_VPIN_GATE !== "false" && flowIsSellToxic(book, tape)) {
      return false;
    }
    if (goLong && process.env.HFT_MICRO_PRICE_GATE !== "false" && !microPriceSupportsLong(book)) {
      return false;
    }

    if (goLong && !tradeNewsAllowsLong(t)) {
      logTradeNewsBlock(t);
      return false;
    }

    const side: "buy" | "sell" = goLong ? "buy" : "sell";
    if (!ordersAllowed(side)) return false;

    // --- Edge-vs-cost gate ---------------------------------------------------
    // The dominant bleed was paying a full round-trip spread to capture a
    // smaller mean-reversion. Skip the trade when the expected edge (distance
    // back toward VWAP) does not clear the live spread + fees. Reversible via
    // HFT_MR_EDGE_COST_GATE=false; tunable via HFT_MR_EDGE_COST_MULT / HFT_FEE_BPS.
    if (process.env.HFT_MR_EDGE_COST_GATE !== "false") {
      const expEdgeBps =
        (goLong
          ? Math.max(0, (vwap - lastClose) / vwap)
          : Math.max(0, (lastClose - vwap) / vwap)) * 10_000;
      const sBps = chargedSpreadBps(book);
      const feeBps = Number(process.env.HFT_FEE_BPS ?? 0) + execDelayFeeBps();
      const costMult = Number(process.env.HFT_MR_EDGE_COST_MULT ?? 1.0);
      const requiredBps = sBps * costMult + feeBps;
      if (!(expEdgeBps >= requiredBps)) {
        fileLogger.emit("mr_edge_skip", {
          ticker: t,
          side,
          expEdgeBps,
          spreadBps: sBps,
          requiredBps,
        });
        return false;
      }
    }

    const px = entryLimitPx(side, book);
    if (px == null) return false;

    const dipDist = goLong
      ? Math.max(0, (vwap - lastClose) / vwap)
      : Math.max(0, (lastClose - vwap) / vwap);
    const dipStrength = Math.min(1, dipDist / (2 * this.dipPctTrigger));
    const patternStrength = bullishPattern || bearishPattern ? 1.0 : 0.5;
    const obiAlign = goLong
      ? Math.max(0, Math.min(1, (book.obi + 1) / 2))
      : Math.max(0, Math.min(1, (1 - book.obi) / 2));
    const conf = candleOnly || bullishPattern || bearishPattern
      ? 0.55 * patternStrength + 0.25 * dipStrength + 0.2 * obiAlign
      : 0.4 * patternStrength + 0.3 * dipStrength + 0.3 * obiAlign;
    const sizeMult = confidenceNotionalMult(conf);
    if (sizeMult <= 0) return false;

    const newsTilt = tradeNewsSizingTilt(t);
    if (newsTilt <= 0) {
      logTradeNewsBlock(t);
      return false;
    }
    let invUsd = 0;
    for (const p of this.open.values()) invUsd += p.qty * p.entryPx;
    const ageMs = Math.max(0, Date.now() - (book.lastUpdateMs || Date.now()));
    const eq =
      marginSnapshot()?.equity ?? Number(process.env.HFT_EQUITY_FALLBACK_USD ?? 70_000);
    const clip = sizeHftClip({
      baseUsd: resolveHftNotionalUsd(CFG.obi.notional) * sizeMult * newsTilt,
      quoteAgeMs: ageMs,
      hftInventoryUsd: invUsd,
      equityUsd: eq,
    });
    if (clip.sitOut || !(clip.notional > 0)) {
      fileLogger.emit("mr_lag_sitout", {
        ticker: t,
        haircut: clip.haircut,
        lag: clip.lag,
        inv: clip.inv,
        ageMs,
      });
      return false;
    }
    const notional = clip.notional;
    const marginOk = canEnterBuy(notional);
    if (!marginOk.ok) {
      logMarginSkip(t, marginOk.reason ?? "margin-block");
      return false;
    }
    let qty = Math.floor(notional / Math.max(px, 1));
    const maxQty = Number(process.env.HFT_MAX_SYMBOL_QTY ?? 0);
    if (maxQty > 0) qty = Math.min(qty, maxQty);
    if (!(qty >= 1)) {
      fileLogger.emit("mr_qty_skip", { ticker: t, notional, px });
      return false;
    }

    if (!this.kill.reserveOrderSlot(nowMs)) return false;
    this.pending.add(t);

    const orderId = nextId();
    const extended = hftExtendedHoursFlag();
    const hl = tradeNewsHeadline(t);
    log("FIRE", {
      ticker: t,
      side,
      px,
      qty,
      spreadBps: spreadBps(book),
      pattern: patternName(pattern),
      signal_conf: conf,
      news_tilt: newsTilt,
      dipPct: dipDist,
      haircut: clip.haircut,
      news: hl ? hl.slice(0, 80) : undefined,
      ...(tradeNewsLogFields(t) ?? {}),
    });

    void this.placeEntry(
      t,
      side,
      px,
      qty,
      orderId,
      extended,
      nowMs,
      exitMs,
      debounceMs,
      {
        pattern: patternName(pattern),
        conf,
        dipDist,
        spreadBps: spreadBps(book),
      },
      book,
    );
    return true;
  }

  private async placeEntry(
    t: string,
    side: "buy" | "sell",
    px: number,
    qty: number,
    orderId: string,
    extended: boolean,
    nowMs: number,
    exitMs: number,
    debounceMs: number,
    meta: { pattern: string; conf: number; dipDist: number; spreadBps: number },
    book: L2Book,
  ): Promise<void> {
    const entryFillMs = Number(process.env.HFT_ENTRY_FILL_MS ?? 6000);
    const cancelEntry = process.env.HFT_CANCEL_ENTRY_UNFILLED === "true";
    try {
      if (side === "buy" && process.env.HFT_BLOCK_ADD_TO_BROKER_LONG !== "false") {
        const live = issuerCachedLongQty((s) => this.broker.cachedLongQty(s), t);
        if (skipBuyAlreadyLong(live, 0)) {
          fileLogger.emit("mr_skip_already_long", { ticker: t, liveQty: live, issuer: true });
          this.pending.delete(t);
          return;
        }
      }
      const maxQty = Number(process.env.HFT_MAX_SYMBOL_QTY ?? 0);
      if (maxQty > 0 && side === "buy") {
        const held = issuerCachedLongQty((s) => this.broker.cachedLongQty(s), t);
        const liveHeld = Number.isFinite(held) ? held : 0;
        const room = Math.max(0, maxQty - liveHeld);
        if (room < 1) {
          this.pending.delete(t);
          return;
        }
        qty = Math.min(qty, room);
      }
      // Never ADD into mega index ETFs already on the book (fortress or prior HFT).
      if (side === "buy") {
        const noRebuyRaw =
          process.env.FORTRESS_NO_REBUY_SYMBOLS || "SPY,QQQ,IWM,DIA,VOO,VTI,SOXX,XLK,XLF,XLE";
        const noRebuy = new Set(
          noRebuyRaw
            .split(",")
            .map((s) => s.trim().toUpperCase())
            .filter(Boolean),
        );
        if (noRebuy.has(t.toUpperCase())) {
          const held = await this.broker.getPositionQty(t);
          if (held > 0) {
            fileLogger.emit("mr_no_rebuy", { ticker: t, held, reason: "broker_already_held" });
            log("SKIP", { ticker: t, reason: "no_rebuy_index_held", held });
            this.pending.delete(t);
            return;
          }
        }
        const banOn =
          process.env.HFT_BAN_INDEX_BUYS !== "false" &&
          process.env.FORTRESS_BAN_INDEX_BUYS !== "false";
        if (banOn) {
          const banRaw =
            process.env.HFT_BAN_INDEX_ETFS ||
            process.env.FORTRESS_BAN_INDEX_ETFS ||
            "SPY,QQQ,IWM,DIA,VOO,VTI,SOXX,XLK,XLF,XLE";
          const banned = new Set(
            banRaw
              .split(",")
              .map((s) => s.trim().toUpperCase())
              .filter(Boolean),
          );
          if (banned.has(t.toUpperCase())) {
            fileLogger.emit("mr_ban_index", { ticker: t, reason: "banned_index_etf_entry" });
            log("SKIP", { ticker: t, reason: "banned_index_etf" });
            this.pending.delete(t);
            return;
          }
        }
      }
      // Passive maker entry rests at the bid → must use DAY TIF (an IOC at the
      // bid cancels instantly). Aggressive (taker) entries cross the spread IOC.
      const aggressive = process.env.HFT_AGGRESSIVE_ENTRY === "true";
      // Passive bid rest must stay DAY (IOC at the bid cancels immediately).
      const entryTif = (aggressive ? hftLimitTif() : "day") as TimeInForce;
      this.broker.registerNbbo(t, book.bestBid, book.bestAsk);
      const resp: OrderResponse = await this.broker.place({
        symbol: t,
        side,
        qty,
        type: "limit",
        time_in_force: entryTif,
        limit_price: px,
        extended_hours: extended,
        client_order_id: orderId,
      });

      if (!(resp.ok && resp.id)) {
        this.pending.delete(t);
        return;
      }

      // Entry timeout: cancel an unfilled passive bid so we never get filled on
      // a downward knife after the signal has gone stale.
      const resolved = await resolveOrderFill(this.broker, resp.id, qty, {
        timeoutMs: entryFillMs,
        cancelIfUnfilled: cancelEntry,
      });

      fileLogger.emit("mr_fire", {
        ticker: t,
        side,
        px,
        qty,
        ...meta,
        ok: resp.ok,
        status: resp.status,
        brokerId: resp.id,
        orderStatus: resolved.status,
        filledQty: resolved.filledQty,
        filledAvgPx: resolved.filledAvgPrice,
        canceled: resolved.canceled,
        wireUs: resp.latencyUs,
      });

      if (!resolved.filled || resolved.filledQty <= 0) {
        if (resolved.working) {
          log("entry-working", { ticker: t, status: resolved.status, crossesMinute: true });
          void this.watchWorkingEntry(t, resp.id, qty, px, side, meta);
          return;
        }
        if (resolved.canceled) {
          log("entry-expired", { ticker: t, status: resolved.status, canceled: true });
          void this.broker.cancelHftExits(t);
        }
        this.pending.delete(t);
        const backoff = Number(
          process.env.HFT_ENTRY_MISS_COOLDOWN_MS ??
            process.env.HFT_ENTRY_BACKOFF_MS ??
            45_000,
        );
        this.nextFireOkMs.set(t, Date.now() + backoff);
        // Also arm kill-switch so OBI + MR don't double-spray the same name after a miss.
        this.kill.lock(t, Date.now() + Math.max(0, backoff - this.kill.cooldownMs));
        return;
      }

      const fillPx =
        resolved.filledAvgPrice && resolved.filledAvgPrice > 0
          ? resolved.filledAvgPrice
          : px;
      const pos: MeanRevPosition = {
        ticker: t,
        side,
        entryPx: fillPx,
        qty: filledShareQty(resolved.filledQty),
        brokerId: resp.id,
        openedMs: Date.now(),
        patternName: meta.pattern,
      };
      this.pending.delete(t);
      this.open.set(t, pos);
      this.kill.lock(t, nowMs);
      // Exit only via monitor() when bid/ask crosses green (or max-hold emergency).
    } catch (err) {
      this.pending.delete(t);
      log("place-error", err instanceof Error ? err.message : err);
    }
  }

  private async flatten(
    pos: MeanRevPosition,
    debounceMs: number,
    scheduledExitMs: number,
    forceExit = false,
  ): Promise<void> {
    const t = pos.ticker.toUpperCase();
    if (!this.open.has(t)) return;
    if (this.flattening.has(t)) return;

    const entryFill = await entryFilledQty(this.broker, pos.brokerId);
    if (!(entryFill > 1e-8)) {
      log("flatten-skip-no-entry-fill", { ticker: t, brokerId: pos.brokerId });
      await this.broker.cancelHftExits(t);
      this.open.delete(t);
      return;
    }

    const book = this.getBook(t);
    if (!book || !(book.bestBid > 0 && book.bestAsk > 0)) {
      setTimeout(() => void this.flatten(pos, debounceMs, scheduledExitMs, forceExit), 2_000);
      return;
    }

    if (!flattenQuoteOk(book)) {
      const wait = flattenDebounceMs();
      setTimeout(() => void this.flatten(pos, debounceMs, scheduledExitMs, forceExit), wait);
      return;
    }

    const now = Date.now();
    const last = this.lastFlattenAttemptMs.get(t) ?? 0;
    if (now - last < flattenDebounceMs()) return;
    this.lastFlattenAttemptMs.set(t, now);

    const flatSide = pos.side === "buy" ? "sell" : "buy";
    const maxHoldMs = Number(process.env.HFT_MR_MAX_HOLD_MS ?? 30_000);
    const heldMs = Date.now() - pos.openedMs;
    const timedOut = maxHoldMs > 0 && heldMs >= maxHoldMs;
    // forcedLoss pricing only on true stop / FORCE_FLATTEN — never on max-hold timeout.
    const forced =
      forceExit || process.env.HFT_FORCE_FLATTEN === "true";

    // Green TP, or max-hold sell-high, or hard forced exit.
    if (!forced && !timedOut && !isInGreen(pos.side, pos.entryPx, book)) {
      this.flattening.delete(t);
      return;
    }

    this.flattening.add(t);
    const flatSideCheck = pos.side === "buy" ? "sell" : "buy";
    if (!ordersAllowed(flatSideCheck)) {
      setTimeout(() => void this.flatten(pos, debounceMs, scheduledExitMs, forceExit), flattenDebounceMs());
      this.flattening.delete(t);
      return;
    }
    const extended = hftExtendedHoursFlag();
    const px = exitLimitPx(flatSide, book, pos.entryPx, forced);
    if (!forced && pos.entryPx > 0 && px + 1e-12 < pos.entryPx) {
      this.flattening.delete(t);
      return;
    }
    const orderId = nextId();
    const exitFillMs = Number(process.env.HFT_EXIT_FILL_MS ?? 8000);
    const cancelExit =
      process.env.HFT_CANCEL_EXIT_UNFILLED === "true" && !extended;

    const openExits = await this.broker.listOpenOrders(t);
    const workingSell = openExits.find(
      (o) =>
        (o.side || "").toLowerCase() === "sell" && isHftExitClientId(o.clientOrderId || ""),
    );
    if (workingSell) {
      const lim = Number(workingSell.limitPrice ?? 0);
      const fillable = lim > 0 && !sellLimitUnfillable(lim, book.bestBid, book.bestAsk);
      const limBelowCost = pos.entryPx > 0 && lim > 0 && lim + 1e-12 < pos.entryPx;
      if (fillable && !limBelowCost) {
        this.flattening.delete(t);
        setTimeout(() => void this.flatten(pos, debounceMs, scheduledExitMs, forceExit), flattenDebounceMs());
        return;
      }
      await this.broker.cancel(workingSell.id);
      log("flatten-reprice", { ticker: t, oldPx: lim, ask: book.bestAsk });
    }

    try {
      this.broker.registerNbbo(t, book.bestBid, book.bestAsk);
      let qty = Math.min(pos.qty, entryFill);
      if (pos.side === "buy" && process.env.HFT_LONG_ONLY !== "false") {
        const live = this.broker.cachedLongQty(t);
        if (Number.isFinite(live)) {
          if (!(live > 1e-8)) {
            await this.broker.cancelHftExits(t);
            this.open.delete(t);
            this.flattening.delete(t);
            return;
          }
          qty = Math.min(qty, live);
        }
      }
      if (!(qty > 0)) {
        this.open.delete(t);
        this.flattening.delete(t);
        return;
      }
      const resp = await this.broker.place({
        symbol: t,
        side: flatSide,
        qty,
        type: "limit",
        time_in_force: hftExitTif(),
        limit_price: px,
        extended_hours: extended,
        client_order_id: `flat-${orderId}`,
      });

      const st = Number(resp.status);
      if (st === 429 || String(resp.reject_reason || "").includes("429")) {
        log("flatten-429", { ticker: t });
        setTimeout(
          () => void this.flatten(pos, debounceMs, scheduledExitMs, forceExit),
          Number(process.env.HFT_RATE_LIMIT_BACKOFF_MS ?? 20_000),
        );
        return;
      }

      let ok = false;
      let filledAvgPx = 0;
      if (resp.ok && resp.id) {
        const resolved = await resolveOrderFill(this.broker, resp.id, qty, {
          timeoutMs: exitFillMs,
          cancelIfUnfilled: cancelExit,
        });
        ok = resolved.filled && resolved.filledQty > 0;
        if (resolved.filledAvgPrice && resolved.filledAvgPrice > 0) {
          filledAvgPx = resolved.filledAvgPrice;
        }
        if (!ok && resolved.canceled) {
          log("exit-unfilled", { ticker: t, status: resolved.status, canceled: true });
        }
      }

      if (!ok && forced && process.env.HFT_FLATTEN_CLOSE_POSITION === "true") {
        // Sleeve-scoped: only close THIS HFT leg qty — never fortress/LT shares.
        const closed = await this.broker.closePosition(t, pos.entryPx, forced, pos.qty);
        if (closed.ok) {
          filledAvgPx = flatSide === "sell" ? book.bestBid : book.bestAsk;
          log("FLATTEN-CLOSE", { ticker: t, qty: pos.qty });
          fileLogger.emit("mr_flatten_close", { ticker: t, qty: pos.qty, ok: true });
          ok = true;
        }
      }

      fileLogger.emit("mr_flatten", {
        ticker: t,
        flatSide,
        qty: pos.qty,
        entryPx: pos.entryPx,
        exitPx: px,
        exitBid: book.bestBid,
        exitAsk: book.bestAsk,
        spreadBps: spreadBps(book),
        pattern: pos.patternName,
        ok,
        status: resp.status,
        brokerId: resp.id,
        wireUs: resp.latencyUs,
        heldMs,
        forced,
      });
      log("FLATTEN", {
        ticker: t,
        side: flatSide,
        qty: pos.qty,
        entryPx: pos.entryPx,
        exitPx: px,
        bid: book.bestBid,
        ok,
        forced,
      });

      if (ok) {
        const exitPx = filledAvgPx > 0 ? filledAvgPx : px;
        const pnlPerShare =
          pos.side === "buy" ? exitPx - pos.entryPx : pos.entryPx - exitPx;
        this.circuit.recordRoundTripPnl(pnlPerShare * pos.qty);
        if (this.circuit.isTripped()) {
          this.kill.setGlobal(true);
          log("CIRCUIT-BREAKER", {
            netUsd: this.circuit.netPnl(),
            action: "global_kill",
          });
        }
        this.open.delete(t);
        // Per-symbol round-trip cooldown measured from the EXIT (not entry), so
        // a quick winner can't immediately re-arm and churn the same name. Floor
        // is the larger of the debounce and HFT_MR_ROUNDTRIP_COOLDOWN_MS.
        const roundTripCooldownMs = Number(process.env.HFT_MR_ROUNDTRIP_COOLDOWN_MS ?? 15_000);
        this.nextFireOkMs.set(t, Date.now() + Math.max(debounceMs, roundTripCooldownMs));
      } else if (!forced) {
        this.flattening.delete(t);
        setTimeout(() => void this.flatten(pos, debounceMs, scheduledExitMs, false), flattenDebounceMs());
      } else {
        setTimeout(() => void this.flatten(pos, debounceMs, scheduledExitMs, forced), flattenDebounceMs());
      }
    } catch (err) {
      log("flatten-error", err instanceof Error ? err.message : err);
      setTimeout(() => void this.flatten(pos, debounceMs, scheduledExitMs), flattenDebounceMs());
    } finally {
      this.flattening.delete(t);
    }
  }
}
