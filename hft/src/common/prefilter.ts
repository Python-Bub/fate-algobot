/**
 * Zero-regex, byte-level ticker prefilter.
 *
 * Each incoming WebSocket frame is delivered to us as a raw Buffer.  Before we
 * pay the cost of `JSON.parse()`, we run `Buffer.indexOf(needle)` for every
 * watched ticker — `Buffer.indexOf` is a native libuv/V8 boyer-moore-ish scan
 * and runs in low microseconds even on multi-KB frames.  Only if at least one
 * ticker token matches do we deserialise.
 *
 * Tickers are surrounded with quote bytes (0x22) so we don't match the inside
 * of unrelated words (e.g. "SPY" inside "OSPREY").
 */
export class TickerPrefilter {
  private readonly needles: Buffer[];
  private readonly tickers: string[];

  constructor(tickers: readonly string[]) {
    this.tickers = tickers.map((t) => t.toUpperCase());
    this.needles = this.tickers.map((t) => Buffer.from(`"${t}"`));
  }

  /** Return the first matching ticker (uppercased) or null. */
  match(payload: Buffer): string | null {
    for (let i = 0; i < this.needles.length; i++) {
      if (payload.indexOf(this.needles[i]) !== -1) return this.tickers[i];
    }
    return null;
  }

  /** All matching tickers in this payload (rare path). */
  matchAll(payload: Buffer): string[] {
    const hits: string[] = [];
    for (let i = 0; i < this.needles.length; i++) {
      if (payload.indexOf(this.needles[i]) !== -1) hits.push(this.tickers[i]);
    }
    return hits;
  }

  tickerCount(): number {
    return this.tickers.length;
  }
}
