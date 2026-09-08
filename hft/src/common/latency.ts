/**
 * Microsecond / nanosecond clocks for measuring hot-path latency.
 *
 * `process.hrtime.bigint()` returns nanoseconds since an arbitrary process-start
 * epoch — monotonic and unaffected by system clock changes. We use it for *all*
 * intra-process latency measurements (ingest → eval → wire).
 *
 * `Date.now()` is reserved for absolute exchange-timestamp comparisons.
 */
const NS_PER_MS = 1_000_000n;
const NS_PER_US = 1_000n;

export function nowNs(): bigint {
  return process.hrtime.bigint();
}

export function nsToMs(ns: bigint): number {
  return Number(ns / NS_PER_MS) + Number(ns % NS_PER_MS) / 1_000_000;
}

export function nsToUs(ns: bigint): number {
  return Number(ns / NS_PER_US) + Number(ns % NS_PER_US) / 1000;
}

/** Pre-allocated rolling latency histogram (no per-sample alloc). */
export class LatencyHistogram {
  private readonly buf: Float64Array;
  private idx = 0;
  private filled = 0;

  constructor(public readonly capacity: number, public readonly label: string) {
    this.buf = new Float64Array(capacity);
  }

  recordNs(ns: bigint): void {
    this.buf[this.idx] = nsToUs(ns);
    this.idx = (this.idx + 1) % this.capacity;
    if (this.filled < this.capacity) this.filled++;
  }

  snapshot(): { p50: number; p95: number; p99: number; max: number; n: number } {
    if (this.filled === 0) return { p50: 0, p95: 0, p99: 0, max: 0, n: 0 };
    const view = this.buf.subarray(0, this.filled);
    const sorted = new Float64Array(view);
    sorted.sort();
    const q = (p: number): number => sorted[Math.min(sorted.length - 1, Math.floor(p * sorted.length))];
    return { p50: q(0.5), p95: q(0.95), p99: q(0.99), max: sorted[sorted.length - 1], n: this.filled };
  }
}
