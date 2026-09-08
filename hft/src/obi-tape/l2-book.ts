/**
 * ============================================================================
 * PHASE 1 — MICRO-L2 ORDER BOOK ENGINE
 * ============================================================================
 *
 *   • Per-ticker L2 state is a single contiguous `Float64Array(LVL*4)` —
 *     [bidPx0, bidSz0, askPx0, askSz0, bidPx1, …].  No pointer chasing, no
 *     hidden classes; layout is identical across processes.
 *   • Snapshot frames replace the array.  Delta frames mutate in place.
 *   • OBI is recomputed inline on every update using a tight loop over the
 *     pre-allocated buffer.
 *   • Exchange→local latency = (localReceiveMs - exchangeTsMs).  Recorded into
 *     a `LatencyHistogram` per ticker for tail-tracking.
 */
import { LatencyHistogram } from "../common/latency.js";

export const L2_LEVELS = 5;
const SLOT_SIZE = L2_LEVELS * 4; // px,sz,px,sz per level × 4 for bid+ask interleaved

export const O_BID_PX = 0;
export const O_BID_SZ = 1;
export const O_ASK_PX = 2;
export const O_ASK_SZ = 3;

export class L2Book {
  /** Flat Float64Array buffer; level k uses indices k*4..k*4+3. */
  readonly levels: Float64Array;
  /** Latest computed OBI in (-1, +1). */
  obi = 0;
  /** Latest mid (best bid + best ask) / 2. */
  mid = 0;
  /** Best bid/ask px for fast O(1) read. */
  bestBid = 0;
  bestAsk = 0;
  bestBidSz = 0;
  bestAskSz = 0;
  /** Volume-weighted micro-price (best level). */
  microPrice = 0;
  /** OBI at best bid/ask only. */
  bestObi = 0;
  /** Last update wall-clock (ms). */
  lastUpdateMs = 0;
  /** Exchange timestamp from the last frame (ms), when provided. */
  lastExchangeTsMs = 0;
  /** Local→exchange clock skew histogram (µs). */
  readonly lagHist: LatencyHistogram;
  /** Best-bid-snapshot for micro-stop monitoring. */
  entryRef = 0;
  /** True when bid or ask was inferred (IEX one-sided). Do not take that price. */
  syntheticNbbo = false;

  constructor(public readonly ticker: string) {
    this.levels = new Float64Array(SLOT_SIZE);
    this.lagHist = new LatencyHistogram(2048, `l2.lag.${ticker}`);
  }

  applySnapshot(bids: readonly [number, number][], asks: readonly [number, number][], exchangeTsMs: number): void {
    // Wipe then set the top-5 levels.
    this.levels.fill(0);
    const nB = Math.min(bids.length, L2_LEVELS);
    const nA = Math.min(asks.length, L2_LEVELS);
    for (let i = 0; i < nB; i++) {
      const off = i * 4;
      this.levels[off + O_BID_PX] = bids[i][0];
      this.levels[off + O_BID_SZ] = bids[i][1];
    }
    for (let i = 0; i < nA; i++) {
      const off = i * 4;
      this.levels[off + O_ASK_PX] = asks[i][0];
      this.levels[off + O_ASK_SZ] = asks[i][1];
    }
    this.refresh(exchangeTsMs);
  }

  /** Replace one level (px+sz on either side).  side: 0=bid, 1=ask. */
  applyDelta(level: number, side: 0 | 1, px: number, sz: number, exchangeTsMs: number): void {
    if (level < 0 || level >= L2_LEVELS) return;
    const off = level * 4;
    if (side === 0) {
      this.levels[off + O_BID_PX] = px;
      this.levels[off + O_BID_SZ] = sz;
    } else {
      this.levels[off + O_ASK_PX] = px;
      this.levels[off + O_ASK_SZ] = sz;
    }
    this.refresh(exchangeTsMs);
  }

  /**
   * Recompute derived metrics from the raw arrays.  Hot path — keep alloc-free.
   *   OBI = (Σbid_sz − Σask_sz) / (Σbid_sz + Σask_sz)
   */
  private refresh(exchangeTsMs: number): void {
    let bsum = 0;
    let asum = 0;
    for (let i = 0; i < L2_LEVELS; i++) {
      const off = i * 4;
      bsum += this.levels[off + O_BID_SZ];
      asum += this.levels[off + O_ASK_SZ];
    }
    const denom = bsum + asum;
    this.obi = denom === 0 ? 0 : (bsum - asum) / denom;
    this.bestBid = this.levels[O_BID_PX];
    this.bestAsk = this.levels[O_ASK_PX];
    this.bestBidSz = this.levels[O_BID_SZ];
    this.bestAskSz = this.levels[O_ASK_SZ];
    this.mid =
      this.bestBid > 0 && this.bestAsk > 0
        ? (this.bestBid + this.bestAsk) * 0.5
        : this.bestBid || this.bestAsk;
    const topVol = this.bestBidSz + this.bestAskSz;
    if (topVol > 0 && this.bestBid > 0 && this.bestAsk > 0) {
      this.bestObi = (this.bestBidSz - this.bestAskSz) / topVol;
      this.microPrice =
        (this.bestBidSz * this.bestAsk + this.bestAskSz * this.bestBid) / topVol;
    } else {
      this.bestObi = this.obi;
      this.microPrice = this.mid;
    }
    const nowMs = Date.now();
    this.lastUpdateMs = nowMs;
    if (exchangeTsMs > 0) {
      this.lastExchangeTsMs = exchangeTsMs;
      const lagUs = Math.max(0, (nowMs - exchangeTsMs) * 1000);
      this.lagHist.recordNs(BigInt(Math.round(lagUs * 1000)));
    }
  }
}
