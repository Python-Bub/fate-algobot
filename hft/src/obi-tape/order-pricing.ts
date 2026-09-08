/**
 * Shared limit-price and spread guards for OBI/MR scalpers.
 * Prevents off-market limits and guaranteed-loss round trips.
 */
import { CFG } from "../common/config.js";
import { currentSession, type Session } from "../common/market-session.js";
import type { L2Book } from "./l2-book.js";

export function roundLimit(px: number): number {
  if (px >= 1) return Math.round(px * 100) / 100;
  if (px >= 0.1) return Math.round(px * 1000) / 1000;
  return Math.round(px * 10000) / 10_000;
}

export function spreadBps(book: L2Book): number {
  if (!(book.mid > 0 && book.bestAsk > book.bestBid)) return Number.POSITIVE_INFINITY;
  return ((book.bestAsk - book.bestBid) / book.mid) * 10_000;
}

/** Overnight REST quotes often pair stale bids with bad asks — tighten around mid. */
export function sanitizeRestQuote(
  bp: number,
  ap: number,
  maxBps = Number(process.env.HFT_REST_QUOTE_MAX_BPS ?? 60),
): { bp: number; ap: number; mid: number; rawBps: number } {
  if (!(bp > 0 && ap > 0)) return { bp, ap, mid: 0, rawBps: Number.POSITIVE_INFINITY };
  const mid = (bp + ap) / 2;
  const rawBps = ((ap - bp) / mid) * 10_000;
  if (rawBps <= maxBps) return { bp, ap, mid, rawBps };
  const half = (maxBps / 10_000) * mid * 0.5;
  return { bp: mid - half, ap: mid + half, mid, rawBps };
}

/**
 * IEX after-hours prints often have ask=0. Fill the missing side from last
 * sale so the book is internally consistent. `synthetic` means we invented a
 * side — do not IOC into that price (the firm is not there).
 */
export function completeNbbo(
  bp: number,
  ap: number,
  lastPx = 0,
  tick = CFG.tickSize,
): { bp: number; ap: number; synthetic: boolean } {
  const t = tick > 0 ? tick : 0.01;
  const bid = bp > 0 ? bp : 0;
  const ask = ap > 0 ? ap : 0;
  if (bid > 0 && ask > 0) {
    if (ask >= bid) return { bp: bid, ap: ask, synthetic: false };
    const px = lastPx > 0 ? lastPx : (bid + ask) / 2;
    return { bp: Math.min(bid, px), ap: Math.max(ask, px + t), synthetic: true };
  }
  if (bid > 0 && !(ask > 0)) {
    const a = lastPx > bid ? lastPx : bid + t;
    return { bp: bid, ap: a, synthetic: true };
  }
  if (ask > 0 && !(bid > 0)) {
    const b = lastPx > 0 && lastPx < ask ? lastPx : Math.max(t, ask - t);
    return { bp: b, ap: ask, synthetic: true };
  }
  if (lastPx > 0) {
    return { bp: Math.max(t, lastPx - t), ap: lastPx + t, synthetic: true };
  }
  return { bp: 0, ap: 0, synthetic: false };
}

export function spreadOk(book: L2Book): boolean {
  if (process.env.HFT_SKIP_SPREAD_CHECK === "true") return true;
  const maxBps = Number(process.env.HFT_MAX_SPREAD_BPS ?? 40);
  return spreadBps(book) <= maxBps;
}

/** REST/IEX extended quotes often show fake 5–15% spreads — looser cap overnight/pre. */
export function restSpreadOk(book: L2Book): boolean {
  if (process.env.HFT_SKIP_SPREAD_CHECK === "true") return true;
  const maxBps = Number(process.env.HFT_REST_MAX_SPREAD_BPS ?? 800);
  return spreadBps(book) <= maxBps;
}

export function spreadOkForSession(book: L2Book, sess: Session): boolean {
  if (sess === "regular") return spreadOk(book);
  return restSpreadOk(book);
}

export function bookSpreadOk(book: L2Book): boolean {
  return spreadOkForSession(book, currentSession());
}

/** Cap charged spread so sanitized REST books (~30–120 bps) don't auto-fail TP edge. */
export function chargedSpreadBps(book: L2Book): number {
  const raw = spreadBps(book);
  const cap = Number(process.env.HFT_EDGE_SPREAD_CAP_BPS ?? 12);
  if (!(Number.isFinite(cap) && cap > 0)) return raw;
  return Math.min(raw, cap);
}

/** Don't flatten on garbage IEX/REST NBBOs (was MAX-HOLD at ask $168 / bid $160). */
export function flattenQuoteOk(book: L2Book): boolean {
  const maxBps = Number(
    process.env.HFT_FLATTEN_MAX_SPREAD_BPS ?? process.env.HFT_MAX_SPREAD_BPS ?? 40,
  );
  return spreadBps(book) <= maxBps;
}

export function flattenDebounceMs(): number {
  const n = Number(process.env.HFT_FLATTEN_DEBOUNCE_MS ?? 15_000);
  return Number.isFinite(n) && n > 0 ? n : 15_000;
}

/**
 * Entry limits — MR default is buy LOW / sell HIGH (bid-anchored entries).
 * Set HFT_AGGRESSIVE_ENTRY=true to chase ask/bid for guaranteed IOC fills.
 */
export function entryLimitPx(side: "buy" | "sell", book: L2Book): number | null {
  const slipBps = Number(process.env.HFT_LIMIT_SLIP_BPS ?? 8) / 10_000;
  const tick = CFG.tickSize;
  const buyLow = (process.env.HFT_BUY_LOW ?? "true").toLowerCase() === "true";
  const aggressive = process.env.HFT_AGGRESSIVE_ENTRY === "true" && !buyLow;
  const wide = spreadBps(book) > Number(process.env.HFT_TIGHT_SPREAD_BPS ?? 25);
  if (side === "buy") {
    if (!(book.bestAsk > 0 && book.bestBid > 0)) return null;
    const bidLow = book.bestBid + tick;
    const midCap = book.mid > 0 ? book.mid - tick : bidLow;
    if (!aggressive) {
      // Buy the dip: limit at bid (+1 tick), never above mid, never cross the ask.
      const px = wide ? Math.min(bidLow + tick, midCap) : Math.min(bidLow + tick * 2, midCap);
      const capped = Math.min(Math.max(tick, px), book.bestAsk - tick);
      return roundLimit(Math.max(tick, capped));
    }
    const askPx = book.bestAsk * (1 + slipBps) + tick;
    const midPx = book.mid > 0 ? book.mid * (1 + slipBps) : askPx;
    const bidAnchored = book.bestBid + tick * 2;
    const px = wide ? Math.min(midPx, bidAnchored, askPx) : Math.min(askPx, midPx);
    return roundLimit(px);
  }
  if (!(book.bestBid > 0 && book.bestAsk > 0)) return null;
  if (!aggressive) {
    const askHigh = book.bestAsk - tick;
    const midFloor = book.mid > 0 ? book.mid + tick : askHigh;
    const px = wide ? Math.max(askHigh - tick, midFloor) : Math.max(askHigh, midFloor);
    // Never cross the bid on a passive short entry.
    const capped = Math.max(px, book.bestBid + tick);
    return roundLimit(capped);
  }
  const bidPx = Math.max(tick, book.bestBid * (1 - slipBps) - tick);
  const midPx = book.mid > 0 ? book.mid * (1 - slipBps) : bidPx;
  const askAnchored = book.bestAsk - tick * 2;
  const px = wide ? Math.max(midPx, askAnchored, bidPx) : Math.max(bidPx, midPx);
  return roundLimit(px);
}

/**
 * Exit limits — sell HIGH (at/above entry+edge), buy back shorts LOW.
 * forcedLoss=true only on max-hold emergency (cross at bid).
 */
export function exitLimitPx(
  flatSide: "buy" | "sell",
  book: L2Book,
  entryPx: number,
  forcedLoss = false,
): number {
  const slipBps = Number(process.env.HFT_FLATTEN_SLIP_BPS ?? 4) / 10_000;
  const tick = CFG.tickSize;
  const minBps = Number(process.env.HFT_MIN_EXIT_PROFIT_BPS ?? 3) / 10_000;
  if (flatSide === "sell") {
    const minPx = entryPx > 0 ? entryPx * (1 + minBps) : 0;
    if (forcedLoss) {
      const ref = book.bestBid > 0 ? book.bestBid : entryPx;
      // Even forced: never realize more than max force slip vs entry when set.
      const maxForce = Number(process.env.HFT_MAX_FORCE_EXIT_SLIP_PCT ?? 0.02);
      const floor = entryPx > 0 ? entryPx * (1 - maxForce) : 0;
      return roundLimit(Math.max(tick, floor, ref - tick));
    }
    // Sell high: floor at entry+edge even if that sits above the ask.
    // Capping at the ask while red sold TSLA below the fill.
    const askPx = book.bestAsk > 0 ? book.bestAsk - tick : entryPx;
    const touch = Math.max(askPx, book.bestBid > 0 ? book.bestBid + tick : askPx);
    const px = minPx > 0 ? Math.max(touch, minPx) : touch;
    return roundLimit(Math.max(tick, px));
  }
  const maxPx = entryPx > 0 ? entryPx * (1 - minBps) : Number.POSITIVE_INFINITY;
  if (forcedLoss) {
    const ref = book.bestAsk > 0 ? book.bestAsk : entryPx;
    return roundLimit(ref * (1 + slipBps) + tick);
  }
  const bidPx = book.bestBid > 0 ? book.bestBid + tick : entryPx;
  return roundLimit(Math.min(maxPx, bidPx));
}

/** True when a resting sell cannot trade at the current NBBO. */
export function sellLimitUnfillable(limitPx: number, bid: number, ask: number): boolean {
  if (!(limitPx > 0 && bid > 0 && ask > 0 && ask >= bid)) return false;
  const slackBps = Number(process.env.HFT_SELL_REPRICE_ABOVE_ASK_BPS ?? 8);
  const mid = (bid + ask) / 2;
  const maxSpread = Number(process.env.HFT_FLATTEN_MAX_SPREAD_BPS ?? process.env.HFT_MAX_SPREAD_BPS ?? 40);
  const spreadBpsNow = mid > 0 ? ((ask - bid) / mid) * 10_000 : Number.POSITIVE_INFINITY;
  if (spreadBpsNow <= maxSpread) {
    return limitPx > ask * (1 + slackBps / 10_000);
  }
  if (limitPx > ask) return true;
  const wideAboveMid = Number(process.env.HFT_SELL_REPRICE_WIDE_ABOVE_MID_BPS ?? 40);
  return mid > 0 && limitPx > mid * (1 + wideAboveMid / 10_000);
}

export function requireExitProfit(): boolean {
  if (process.env.HFT_EXIT_ON_GREEN === "true") return false;
  if (process.env.HFT_JP_ULTRA === "true") return false;
  if (process.env.HFT_REQUIRE_EXIT_PROFIT === "false") return false;
  const minBps = Number(process.env.HFT_MIN_EXIT_PROFIT_BPS ?? 5);
  return minBps > 0;
}

/** Hold losers until bid/ask crosses into profit (sub-second default). */
export function waitForGreenExit(): boolean {
  if (process.env.HFT_EXIT_ON_GREEN === "false") return false;
  if (process.env.HFT_EXIT_ON_GREEN === "true") return true;
  return process.env.HFT_INSTANT_GREEN_EXIT !== "false";
}

/** True when the position is in the green (bid/ask past entry + optional buffer). */
export function isInGreen(
  posSide: "buy" | "sell",
  entryPx: number,
  book: L2Book,
): boolean {
  const minBps = Number(process.env.HFT_MIN_EXIT_PROFIT_BPS ?? 0);
  const buffer = minBps / 10_000;
  const minTicks = Number(process.env.HFT_GREEN_EXIT_MIN_TICKS ?? 0);
  const tickEdge = minTicks > 0 ? minTicks * CFG.tickSize : 0;
  if (posSide === "buy") {
    if (!(book.bestBid > 0 && entryPx > 0)) return false;
    const thresh = entryPx * (1 + buffer) + tickEdge;
    return book.bestBid > thresh;
  }
  if (!(book.bestAsk > 0 && entryPx > 0)) return false;
  const thresh = entryPx * (1 - buffer) - tickEdge;
  return book.bestAsk < thresh;
}

/** Quote-only wrapper for broker close paths without a live L2Book. */
export function exitLimitFromQuote(
  flatSide: "buy" | "sell",
  bid: number,
  ask: number,
  entryPx: number,
  forced = false,
): number {
  const book = {
    bestBid: bid,
    bestAsk: ask,
    mid: bid > 0 && ask > 0 ? (bid + ask) / 2 : 0,
  } as L2Book;
  return exitLimitPx(flatSide, book, entryPx, forced);
}

/** True when bid covers entry + minimum edge (fees/slip buffer). */
export function exitProfitable(
  posSide: "buy" | "sell",
  entryPx: number,
  book: L2Book,
): boolean {
  return isInGreen(posSide, entryPx, book);
}
