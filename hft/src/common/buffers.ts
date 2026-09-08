/**
 * Zero-allocation primitive circular buffers backed by typed arrays.
 * All hot-path math uses these to keep V8 in the "small fast" path and avoid
 * triggering generational GC during a market-data spike.
 */

/** Fixed-capacity ring of Float64 samples; oldest entry overwritten on push. */
export class CircularF64 {
  readonly buf: Float64Array;
  private head = 0;
  private filled = 0;
  private sumCached = 0;

  constructor(public readonly capacity: number) {
    this.buf = new Float64Array(capacity);
  }

  push(value: number): void {
    if (this.filled === this.capacity) {
      this.sumCached -= this.buf[this.head];
    }
    this.buf[this.head] = value;
    this.sumCached += value;
    this.head = (this.head + 1) % this.capacity;
    if (this.filled < this.capacity) this.filled++;
  }

  size(): number {
    return this.filled;
  }

  sum(): number {
    return this.sumCached;
  }

  mean(): number {
    return this.filled === 0 ? 0 : this.sumCached / this.filled;
  }

  clear(): void {
    this.head = 0;
    this.filled = 0;
    this.sumCached = 0;
  }
}

/** Time-bucketed counter — count events that fell in the last `windowMs` ms. */
export class TimeWindowCounter {
  private readonly times: Float64Array;
  private head = 0;
  private filled = 0;

  constructor(public readonly capacity: number, public readonly windowMs: number) {
    this.times = new Float64Array(capacity);
  }

  bump(nowMs: number): void {
    this.times[this.head] = nowMs;
    this.head = (this.head + 1) % this.capacity;
    if (this.filled < this.capacity) this.filled++;
  }

  /** Number of events whose timestamp is within [nowMs - windowMs, nowMs]. */
  count(nowMs: number): number {
    if (this.filled === 0) return 0;
    const cutoff = nowMs - this.windowMs;
    let n = 0;
    for (let i = 0; i < this.filled; i++) {
      if (this.times[i] >= cutoff) n++;
    }
    return n;
  }
}

/** Pair of Float64 ring buffers (price, volume) used for tick-level VWAP. */
export class VwapRing {
  readonly price: Float64Array;
  readonly volume: Float64Array;
  readonly time: Float64Array;
  private head = 0;
  private filled = 0;
  private pvSum = 0;
  private vSum = 0;

  constructor(public readonly capacity: number, public readonly windowMs: number) {
    this.price = new Float64Array(capacity);
    this.volume = new Float64Array(capacity);
    this.time = new Float64Array(capacity);
  }

  add(nowMs: number, px: number, vol: number): void {
    if (this.filled === this.capacity) {
      this.pvSum -= this.price[this.head] * this.volume[this.head];
      this.vSum -= this.volume[this.head];
    }
    this.price[this.head] = px;
    this.volume[this.head] = vol;
    this.time[this.head] = nowMs;
    this.pvSum += px * vol;
    this.vSum += vol;
    this.head = (this.head + 1) % this.capacity;
    if (this.filled < this.capacity) this.filled++;
    this.expire(nowMs);
  }

  /** Drop entries older than windowMs in-place. */
  expire(nowMs: number): void {
    const cutoff = nowMs - this.windowMs;
    // Walk from oldest to newest; entries are in insertion order modulo `capacity`.
    let oldest = (this.head - this.filled + this.capacity) % this.capacity;
    while (this.filled > 0 && this.time[oldest] < cutoff) {
      this.pvSum -= this.price[oldest] * this.volume[oldest];
      this.vSum -= this.volume[oldest];
      oldest = (oldest + 1) % this.capacity;
      this.filled--;
    }
  }

  vwap(): number {
    return this.vSum === 0 ? 0 : this.pvSum / this.vSum;
  }

  totalVolume(): number {
    return this.vSum;
  }
}
