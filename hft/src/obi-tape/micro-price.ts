/**
 * Order-book microstructure metrics (OBI, micro-price, VPIN-lite).
 * Alloc-free helpers for the hot path — all inputs from L2Book / TapeVelocity.
 */
import type { L2Book } from "./l2-book.js";
import type { TapeVelocity } from "./tape-velocity.js";

/** Best-level OBI: (V_bid − V_ask) / (V_bid + V_ask) at top of book. */
export function bestLevelObi(book: L2Book): number {
  const vb = book.bestBidSz;
  const va = book.bestAskSz;
  const d = vb + va;
  if (d <= 0) return 0;
  return (vb - va) / d;
}

/**
 * Volume-weighted fair price (micro-price).
 * MicroPrice = (V_bid·P_ask + V_ask·P_bid) / (V_bid + V_ask)
 */
export function microPrice(book: L2Book): number {
  const vb = book.bestBidSz;
  const va = book.bestAskSz;
  const pb = book.bestBid;
  const pa = book.bestAsk;
  const d = vb + va;
  if (d <= 0 || !(pb > 0 && pa > 0)) return book.mid;
  return (vb * pa + va * pb) / d;
}

/** Micro-price drift above mid in bps — positive = upward pressure. */
export function microPriceDriftBps(book: L2Book): number {
  if (!(book.mid > 0)) return 0;
  const mp = microPrice(book);
  return ((mp - book.mid) / book.mid) * 10_000;
}

/**
 * VPIN-lite proxy: aggressive tape burst + micro-price drifting down.
 * Blocks new longs when institutions are likely dumping through the book.
 */
export function flowIsSellToxic(book: L2Book, tape: TapeVelocity): boolean {
  const burstMin = Number(process.env.TAPE_VELOCITY_MULTIPLIER ?? 2.5);
  if (tape.lastBurstRatio < burstMin) return false;
  const minDriftBps = Number(process.env.HFT_VPIN_MIN_DRIFT_BPS ?? 2);
  return microPriceDriftBps(book) <= -minDriftBps;
}

export function microPriceSupportsLong(book: L2Book): boolean {
  const minBps = Number(process.env.HFT_MICRO_PRICE_MIN_BPS ?? 0.5);
  const top = book.bestBidSz + book.bestAskSz;
  // Equal/unknown sizes: no micro-price edge. Defer to OBI (already gated).
  if (!(top > 0) || Math.abs(book.bestBidSz - book.bestAskSz) < 1e-9) {
    return book.obi > 0;
  }
  return microPriceDriftBps(book) >= minBps;
}
