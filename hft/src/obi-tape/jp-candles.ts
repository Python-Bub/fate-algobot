/**
 * Japanese candlestick pattern detector for the sub-second tape.
 *
 * Builds 1-second OHLC candles from the raw trade stream (zero allocation —
 * Float64Array slots) and tags the most-recent few candles with a small set of
 * reliable single-bar and two-bar patterns:
 *
 *   - HAMMER       (single-bar bullish reversal)
 *   - INV_HAMMER   (single-bar bullish reversal)
 *   - SHOOTING_STAR (single-bar bearish reversal)
 *   - HANGING_MAN   (single-bar bearish reversal)
 *   - DOJI          (indecision; combined with OBI for context)
 *   - BULLISH_ENGULF (two-bar bullish reversal)
 *   - BEARISH_ENGULF (two-bar bearish reversal)
 *
 * The HFT signals engine reads `lastPattern` after each trade and combines it
 * with OBI / tape-velocity / micro-mean-reversion logic.  All bar boundaries
 * align on `floor(ts / candleMs) * candleMs` so candles roll predictably.
 */

import { CircularF64 } from "../common/buffers.js";

export const PAT_NONE = 0;
export const PAT_HAMMER = 1;
export const PAT_INV_HAMMER = 2;
export const PAT_SHOOTING_STAR = 3;
export const PAT_HANGING_MAN = 4;
export const PAT_DOJI = 5;
export const PAT_BULLISH_ENGULF = 6;
export const PAT_BEARISH_ENGULF = 7;

export function patternName(p: number): string {
  switch (p) {
    case PAT_HAMMER: return "HAMMER";
    case PAT_INV_HAMMER: return "INV_HAMMER";
    case PAT_SHOOTING_STAR: return "SHOOTING_STAR";
    case PAT_HANGING_MAN: return "HANGING_MAN";
    case PAT_DOJI: return "DOJI";
    case PAT_BULLISH_ENGULF: return "BULLISH_ENGULF";
    case PAT_BEARISH_ENGULF: return "BEARISH_ENGULF";
    default: return "NONE";
  }
}

/** Bullish patterns (+1), bearish (-1), indecision (0). */
export function patternBias(p: number): -1 | 0 | 1 {
  if (p === PAT_HAMMER || p === PAT_INV_HAMMER || p === PAT_BULLISH_ENGULF) return 1;
  if (p === PAT_SHOOTING_STAR || p === PAT_HANGING_MAN || p === PAT_BEARISH_ENGULF) return -1;
  return 0;
}

/**
 * Compact per-ticker candle builder.  Keeps the last `capacity` finished
 * candles plus the in-progress one.  Memory: 5 × Float64Array(capacity).
 */
export class CandleBuilder {
  readonly open: Float64Array;
  readonly high: Float64Array;
  readonly low: Float64Array;
  readonly close: Float64Array;
  readonly start: Float64Array;
  /** Recent N closes — used for trend context in mean-reversion logic. */
  readonly recentCloses: CircularF64;
  private head = 0;
  private filled = 0;
  private curStart = 0;

  /** Most recent detected pattern (PAT_*). */
  lastPattern = PAT_NONE;
  /** Per-trade hook fires the live-candle close so consumers can react inside the bar. */
  liveClose = 0;
  liveOpen = 0;
  liveHigh = 0;
  liveLow = 0;
  private started = false;

  constructor(
    public readonly ticker: string,
    public readonly candleMs: number = 1000,
    public readonly capacity: number = 60,
  ) {
    this.open = new Float64Array(capacity);
    this.high = new Float64Array(capacity);
    this.low = new Float64Array(capacity);
    this.close = new Float64Array(capacity);
    this.start = new Float64Array(capacity);
    this.recentCloses = new CircularF64(64);
  }

  /** Number of finished candles in the ring. */
  get nFilled(): number {
    return this.filled;
  }

  /** Finished bar `k` ago (0 = latest finished). */
  barAgo(k: number): { o: number; h: number; l: number; c: number } | null {
    const i = this.ago(k);
    if (i < 0) return null;
    return { o: this.open[i], h: this.high[i], l: this.low[i], c: this.close[i] };
  }

  /** Index of the most-recent finished candle, or -1 if none yet. */
  private lastIdx(): number {
    if (this.filled === 0) return -1;
    return (this.head - 1 + this.capacity) % this.capacity;
  }

  /** Index `k` candles back from the latest, or -1 if out of range. */
  ago(k: number): number {
    if (k < 0 || k >= this.filled) return -1;
    return (this.head - 1 - k + this.capacity) % this.capacity;
  }

  /** Ingest a single trade. Returns true if a candle just closed. */
  onTrade(tsMs: number, px: number, _sz: number): boolean {
    if (!(px > 0)) return false;
    const bucket = Math.floor(tsMs / this.candleMs) * this.candleMs;
    if (!this.started) {
      this.started = true;
      this.curStart = bucket;
      this.liveOpen = px;
      this.liveHigh = px;
      this.liveLow = px;
      this.liveClose = px;
      return false;
    }
    if (bucket === this.curStart) {
      // Same bar: update HLC.
      if (px > this.liveHigh) this.liveHigh = px;
      if (px < this.liveLow) this.liveLow = px;
      this.liveClose = px;
      return false;
    }
    // New bar — finish the previous one.
    this.open[this.head] = this.liveOpen;
    this.high[this.head] = this.liveHigh;
    this.low[this.head] = this.liveLow;
    this.close[this.head] = this.liveClose;
    this.start[this.head] = this.curStart;
    this.recentCloses.push(this.liveClose);
    this.head = (this.head + 1) % this.capacity;
    if (this.filled < this.capacity) this.filled++;
    this.curStart = bucket;
    this.liveOpen = px;
    this.liveHigh = px;
    this.liveLow = px;
    this.liveClose = px;
    this.lastPattern = this.classifyLatest();
    return true;
  }

  /**
   * Pattern detection on the two most recent **finished** candles. All checks
   * use proportional thresholds (no fixed-tick assumptions) so they work for
   * SPY (~$500) as well as small-caps (~$5).
   */
  classifyLatest(): number {
    const i1 = this.lastIdx();
    if (i1 < 0) return PAT_NONE;
    const o1 = this.open[i1], h1 = this.high[i1], l1 = this.low[i1], c1 = this.close[i1];
    const range1 = h1 - l1;
    if (!(range1 > 0) || !(c1 > 0)) return PAT_NONE;
    // A one-tick wiggle is not a hammer. The bar has to move in real bps.
    const rangeBps = (range1 / c1) * 10_000;
    if (rangeBps < 4) return PAT_NONE;
    const body1 = Math.abs(c1 - o1);
    const upperShadow1 = h1 - Math.max(o1, c1);
    const lowerShadow1 = Math.min(o1, c1) - l1;

    // HAMMER / HANGING MAN — small upper, long lower (≥2× body).  Tested first
    // because their body is also small, so the DOJI rule below would otherwise
    // swallow them.
    if (lowerShadow1 >= 2 * body1 && upperShadow1 <= 0.3 * range1 && body1 / range1 < 0.40 && body1 > 0) {
      const trend = this.recentTrend();
      return trend < 0 ? PAT_HAMMER : PAT_HANGING_MAN;
    }
    // INV HAMMER / SHOOTING STAR — long upper shadow.
    if (upperShadow1 >= 2 * body1 && lowerShadow1 <= 0.3 * range1 && body1 / range1 < 0.40 && body1 > 0) {
      const trend = this.recentTrend();
      return trend < 0 ? PAT_INV_HAMMER : PAT_SHOOTING_STAR;
    }

    // Two-bar engulfings — tested before DOJI so the wider body wins.
    const i2 = this.ago(1);
    if (i2 >= 0) {
      const o2 = this.open[i2], c2 = this.close[i2];
      const body2 = Math.abs(c2 - o2);
      const bullish1 = c1 > o1;
      const bearish1 = c1 < o1;
      const bullish2 = c2 > o2;
      const bearish2 = c2 < o2;
      if (bullish1 && bearish2 && c1 > o2 && o1 < c2 && body1 > body2 * 1.15) return PAT_BULLISH_ENGULF;
      if (bearish1 && bullish2 && c1 < o2 && o1 > c2 && body1 > body2 * 1.15) return PAT_BEARISH_ENGULF;
    }

    // DOJI — very small body relative to range (fallback after specific patterns).
    if (body1 / range1 < 0.10) return PAT_DOJI;

    return PAT_NONE;
  }

  /** Sign of (close[-1] - close[-N]) for context — defaults to 5-candle look-back. */
  recentTrend(lookback: number = 5): number {
    if (this.filled < lookback + 1) return 0;
    const recent = this.close[this.lastIdx()];
    const past = this.close[this.ago(lookback)];
    if (!(recent > 0 && past > 0)) return 0;
    if (recent > past) return 1;
    if (recent < past) return -1;
    return 0;
  }
}
