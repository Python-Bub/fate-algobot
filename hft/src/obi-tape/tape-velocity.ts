/**
 * ============================================================================
 * PHASE 2 — TAPE VELOCITY & MICRO-VWAP
 * ============================================================================
 *
 *   • `TimeWindowCounter` counts prints inside a rolling `tapeWindowMs`.
 *   • A second counter sees the same prints over `baselineWindowMs` for a
 *     5x-burst comparison.
 *   • Micro-VWAP via `VwapRing(windowMs)` produces a continuously-updating
 *     volume-weighted price for fair-value reference.
 *   • Zero allocations on hot path; all buffers are sized at construction.
 */
import { TimeWindowCounter, VwapRing } from "../common/buffers.js";

export class TapeVelocity {
  readonly counterFast: TimeWindowCounter;
  readonly counterBaseline: TimeWindowCounter;
  readonly vwap: VwapRing;
  lastVelocity = 0;
  lastBaselineRate = 0;
  lastBurstRatio = 0;
  lastPx = 0;

  constructor(
    public readonly ticker: string,
    public readonly tapeWindowMs: number,
    public readonly baselineWindowMs: number,
    capacity = 4096,
  ) {
    this.counterFast = new TimeWindowCounter(capacity, tapeWindowMs);
    this.counterBaseline = new TimeWindowCounter(capacity, baselineWindowMs);
    this.vwap = new VwapRing(capacity, baselineWindowMs);
  }

  onTrade(nowMs: number, px: number, sz: number): void {
    this.counterFast.bump(nowMs);
    this.counterBaseline.bump(nowMs);
    if (px > 0 && sz > 0) this.vwap.add(nowMs, px, sz);
    if (px > 0) this.lastPx = px;
    const fastCount = this.counterFast.count(nowMs);
    const baseCount = this.counterBaseline.count(nowMs);
    // Convert to trades-per-100ms (the unit of `tapeWindowMs` by default).
    this.lastVelocity = fastCount; // count per tapeWindowMs
    this.lastBaselineRate =
      baseCount === 0
        ? 0
        : (baseCount / this.baselineWindowMs) * this.tapeWindowMs; // expected count per fast-window
    // Quiet IEX/REST tape: one print vs an empty 5s baseline looks like 50x.
    // Require a real baseline and a real fast cluster before we call it a burst.
    const minBase = Number(process.env.HFT_TAPE_MIN_BASELINE ?? 10);
    const minFast = Number(process.env.HFT_TAPE_MIN_FAST ?? 2);
    const cap = Number(process.env.HFT_TAPE_BURST_CAP ?? 8);
    if (baseCount < minBase || fastCount < minFast || this.lastBaselineRate <= 0) {
      this.lastBurstRatio = 0;
      return;
    }
    const raw = this.lastVelocity / this.lastBaselineRate;
    this.lastBurstRatio = cap > 0 ? Math.min(raw, cap) : raw;
  }

  /** Velocity * window equivalent — useful for logs. */
  tradesPerSecond(): number {
    return (this.lastVelocity / this.tapeWindowMs) * 1000;
  }
}
