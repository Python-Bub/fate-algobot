/**
 * PHASE 4 — RISK: micro-stop / take-profit / max-hold flatten with fill confirmation.
 */
import { AlpacaExecutor } from "../common/alpaca-exec.js";
import { hftExtendedHoursFlag, hftExitTif } from "../common/market-session.js";
import { CFG } from "../common/config.js";
import { entryFilledQty, isHftExitClientId, resolveOrderFill } from "../common/order-lifecycle.js";
import { fileLogger, stdoutTag } from "../common/logger.js";

import { L2Book } from "./l2-book.js";
import {
  exitLimitPx,
  flattenDebounceMs,
  flattenQuoteOk,
  isInGreen,
  requireExitProfit,
  sellLimitUnfillable,
  waitForGreenExit,
} from "./order-pricing.js";
import { CircuitBreaker } from "../common/circuit-breaker.js";
import { KillSwitch } from "../common/kill-switch.js";
import { type Position } from "./obi-tape-signals.js";

const log = stdoutTag("[OBI/RISK]");

let counter = 0;
function flatId(): string {
  counter = (counter + 1) | 0;
  return `flat-${Date.now().toString(36)}-${counter}`;
}

export class ObiTapeRiskManager {
  private readonly flattening = new Set<string>();
  private readonly lastFlattenAttemptMs = new Map<string, number>();
  private readonly flattenBackoffMs = new Map<string, number>();

  constructor(
    private readonly broker: AlpacaExecutor,
    private readonly positions: Map<string, Position>,
    private readonly circuit: CircuitBreaker = new CircuitBreaker(),
    private readonly kill: KillSwitch | null = null,
  ) {}

  private async flatten(book: L2Book, pos: Position, reason: "tp" | "sl" | "hold"): Promise<void> {
    const t = book.ticker.toUpperCase();
    if (!this.positions.has(t) || this.flattening.has(t)) return;
    if (!flattenQuoteOk(book)) return;

    const now = Date.now();
    const last = this.lastFlattenAttemptMs.get(t) ?? 0;
    const backoff = this.flattenBackoffMs.get(t) ?? flattenDebounceMs();
    if (now - last < backoff) return;

    const flatSide = pos.side === "buy" ? "sell" : "buy";
    const underwater =
      pos.side === "buy"
        ? book.bestBid > 0 && pos.entryPx > 0 && book.bestBid + 1e-12 < pos.entryPx
        : book.bestAsk > 0 && pos.entryPx > 0 && book.bestAsk > pos.entryPx + 1e-12;
    // Hard stop always crosses. Max-hold crosses only when last-wins recycle is on
    // (HFT_MAX_HOLD_FORCE_EXIT) — otherwise red HFT bags lock the 15 WS slots.
    const forceHoldExit = process.env.HFT_MAX_HOLD_FORCE_EXIT === "true";
    const forcedLoss = reason === "sl" || (reason === "hold" && forceHoldExit && underwater);
    const px = exitLimitPx(flatSide, book, pos.entryPx, forcedLoss);
    if (!(px > 0)) return;
    if (!forcedLoss && pos.entryPx > 0 && px + 1e-12 < pos.entryPx) {
      return;
    }

    if (
      reason === "tp" &&
      waitForGreenExit() &&
      !isInGreen(pos.side, pos.entryPx, book)
    ) {
      return;
    }
    // Max-hold: ALWAYS attempt a sell-high limit (ask). Do NOT require green —
    // that left HFT inventory stuck forever after green-only + no micro-stop.
    // Only skip if explicitly HFT_MAX_HOLD_REQUIRE_GREEN=true.
    if (reason === "hold") {
      const requireGreen = process.env.HFT_MAX_HOLD_REQUIRE_GREEN === "true";
      if (requireGreen && !isInGreen(pos.side, pos.entryPx, book)) {
        return;
      }
    }
    if (
      reason !== "sl" &&
      reason !== "hold" &&
      requireExitProfit() &&
      !isInGreen(pos.side, pos.entryPx, book)
    ) {
      return;
    }

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
        this.lastFlattenAttemptMs.set(t, now);
        this.flattenBackoffMs.set(t, flattenDebounceMs());
        return;
      }
      await this.broker.cancel(workingSell.id);
      log("flatten-reprice", {
        ticker: t,
        oldPx: lim,
        ask: book.bestAsk,
        bid: book.bestBid,
        reason,
      });
    }

    if (this.kill && !this.kill.reserveOrderSlot(now)) return;

    this.flattening.add(t);
    this.lastFlattenAttemptMs.set(t, now);
    const tag = reason === "sl" ? "MICRO-STOP" : reason === "hold" ? "MAX-HOLD" : "TAKE-PROFIT";
    log(tag, { ticker: t, side: pos.side, entry: pos.entryPx, bid: book.bestBid, ask: book.bestAsk, px });

    // Working DAY buys vs a flatten sell = Alpaca 403 wash storm.
    await this.broker.cancelHftEntries(t);

    const entryFill = await entryFilledQty(this.broker, pos.brokerId);
    if (!(entryFill > 1e-8)) {
      log("flatten-skip-no-entry-fill", { ticker: t, brokerId: pos.brokerId });
      await this.broker.cancelHftExits(t);
      this.positions.delete(t);
      this.flattening.delete(t);
      return;
    }

    const extended = hftExtendedHoursFlag();
    const exitFillMs = Number(process.env.HFT_EXIT_FILL_MS ?? 6000);
    let keepLock = false;

    try {
      let qty = Math.min(pos.qty, entryFill);
      if (pos.side === "buy" && process.env.HFT_LONG_ONLY !== "false") {
        const live = this.broker.cachedLongQty(t);
        if (Number.isFinite(live)) {
          if (!(live > 1e-8)) {
            await this.broker.cancelHftExits(t);
            this.positions.delete(t);
            return;
          }
          qty = Math.min(qty, live);
        }
      }
      if (!(qty > 0)) {
        this.positions.delete(t);
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
        client_order_id: flatId(),
      });

      const st = Number(resp.status);
      const why = String(resp.reject_reason || "");
      if (st === 429 || why.includes("429")) {
        const wait = Number(process.env.HFT_RATE_LIMIT_BACKOFF_MS ?? 20_000);
        this.flattenBackoffMs.set(t, Math.max(wait, flattenDebounceMs()));
        log("flatten-429", { ticker: t, backoffMs: this.flattenBackoffMs.get(t) });
        return;
      }
      if (st === 403 || st === 400 || /wash|insufficient|pdt|forbidden|not allowed/i.test(why)) {
        const prev = this.flattenBackoffMs.get(t) ?? flattenDebounceMs();
        const wait = Math.min(120_000, Math.max(8_000, prev * 2));
        this.flattenBackoffMs.set(t, wait);
        log("flatten-reject", { ticker: t, status: st, reason: why.slice(0, 160), backoffMs: wait });
        if (/insufficient|no_long|protected_other|capped_to_zero/i.test(why)) {
          await this.broker.cancelHftExits(t);
          this.positions.delete(t);
        }
        fileLogger.emit("obi_flatten", {
          ticker: t,
          flatSide,
          px,
          qty,
          reason,
          ok: false,
          status: st,
          reject: why.slice(0, 160),
          brokerId: resp.id,
          wireUs: resp.latencyUs,
        });
        return;
      }

      let ok = false;
      if (resp.ok && resp.id) {
        const resolved = await resolveOrderFill(this.broker, resp.id, qty, {
          timeoutMs: exitFillMs,
          // Max-hold / TP: leave resting sell-high if not filled (don't cancel).
          cancelIfUnfilled:
            reason === "sl"
              ? process.env.HFT_CANCEL_EXIT_UNFILLED === "true"
              : process.env.HFT_CANCEL_EXIT_UNFILLED === "true" && reason === "tp",
        });
        ok = resolved.filled && resolved.filledQty > 0;
        if (!ok && resolved.working) {
          // Leave the DAY sell; next debounce reprices if it goes unfillable.
          this.flattenBackoffMs.set(t, flattenDebounceMs());
        }
      }

      if (!ok && forcedLoss && process.env.HFT_FLATTEN_CLOSE_POSITION === "true") {
        const closed = await this.broker.closePosition(t, pos.entryPx, true, qty);
        ok = closed.ok;
        if (ok) log("FLATTEN-CLOSE", { ticker: t, qty, reason });
      }

      fileLogger.emit("obi_flatten", {
        ticker: t,
        flatSide,
        px,
        qty,
        reason,
        ok,
        status: resp.status,
        brokerId: resp.id,
        wireUs: resp.latencyUs,
      });

      if (ok) {
        this.positions.delete(t);
        this.flattenBackoffMs.delete(t);
        this.lastFlattenAttemptMs.delete(t);
        const pnl = pos.side === "buy" ? (px - pos.entryPx) * qty : (pos.entryPx - px) * qty;
        this.circuit.recordRoundTripPnl(pnl);
      } else if (!keepLock) {
        this.flattenBackoffMs.set(t, flattenDebounceMs());
      }
    } catch {
      this.flattenBackoffMs.set(t, flattenDebounceMs());
    } finally {
      if (!keepLock) this.flattening.delete(t);
    }
  }

  /** Called from the L2 update path *after* signals.maybeFire(). */
  monitor(book: L2Book): void {
    const pos = this.positions.get(book.ticker);
    if (!pos) return;
    if (!flattenQuoteOk(book)) return;
    const tick = CFG.tickSize;
    const stopTicks = CFG.obi.microStopTicks;
    const tpTicks = Number(process.env.HFT_TAKE_PROFIT_TICKS ?? 1);
    const maxHoldMs = Number(process.env.HFT_MAX_HOLD_MS ?? 800);
    const nowMs = Date.now();
    const heldMs = nowMs - pos.openedMs;
    if (maxHoldMs > 0 && heldMs >= maxHoldMs) {
      void this.flatten(book, pos, "hold");
      return;
    }
    const minHoldMs = Number(process.env.HFT_OBI_MIN_HOLD_MS ?? 2000);
    const minHoldOk = heldMs >= minHoldMs;
    if (minHoldOk && isInGreen(pos.side, pos.entryPx, book)) {
      void this.flatten(book, pos, "tp");
      return;
    }
    if (minHoldOk && !waitForGreenExit()) {
      const favorable =
        pos.side === "buy" ? book.bestBid - pos.entryPx : pos.entryPx - book.bestAsk;
      if (favorable >= tpTicks * tick) {
        void this.flatten(book, pos, "tp");
        return;
      }
    }
    // Soft TP only when truly green (entry + min bps/ticks) — 1-tick soft exits
    // were selling into noise and stacking losses with high RTT.
    if (minHoldOk && process.env.HFT_SOFT_GREEN_EXIT !== "false" && isInGreen(pos.side, pos.entryPx, book)) {
      void this.flatten(book, pos, "tp");
      return;
    }
    // Micro-stop: only if enabled; must clear full spread + stopTicks (no inside-spread dump).
    if (stopTicks > 0) {
      const adverseMove =
        pos.side === "buy" ? pos.entryPx - book.bestBid : book.bestAsk - pos.entryPx;
      const fullSpread =
        book.bestAsk > book.bestBid && book.bestAsk > 0
          ? book.bestAsk - book.bestBid
          : 0;
      const minStop = Math.max(stopTicks * tick, fullSpread + stopTicks * tick);
      if (adverseMove >= minStop) {
        void this.flatten(book, pos, "sl");
      }
    }
  }
}
