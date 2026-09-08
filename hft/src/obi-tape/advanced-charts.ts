/**
 * Advanced HFT chart stack — four representations of the same tape:
 *
 *   1. Candlesticks  — body + wicks, green/red (open/close vs high/low)
 *   2. Line chart    — close-to-close path (slope, curvature, SMA break)
 *   3. Bar / HLOC    — high-low shaft with open/close ticks (inside/outside/key reversal)
 *   4. Point & Figure — X/O columns, time-less, box + 3-box reversal
 *
 * Votes are EVENT-driven (pattern just formed), not a standing SMA regime.
 * Hidden / live bias require CROSS-FAMILY agreement: bar geometry
 * (candle or HLOC) AND close-path (line or PnF). Lone folklore candles
 * stay near 0.5. Confirmation of OBI/tape, not a replacement.
 */
import type { CandleBuilder } from "./jp-candles.js";
import { patternBias } from "./jp-candles.js";

export type ChartVote = {
  candle: number;
  line: number;
  hloc: number;
  pnf: number;
  hidden: number;
  score: number;
  nAgree: number;
  crossFamily: boolean;
  bias: -1 | 0 | 1;
};

const EMPTY: ChartVote = {
  candle: 0,
  line: 0,
  hloc: 0,
  pnf: 0,
  hidden: 0,
  score: 0,
  nAgree: 0,
  crossFamily: false,
  bias: 0,
};

function clamp(x: number, lo = -1, hi = 1): number {
  return Math.max(lo, Math.min(hi, x));
}

function sign3(x: number, eps = 0.08): -1 | 0 | 1 {
  if (x > eps) return 1;
  if (x < -eps) return -1;
  return 0;
}

function smaAt(c: Float64Array, end: number, win: number): number {
  const w = Math.min(win, end + 1);
  if (w <= 0) return 0;
  let s = 0;
  for (let k = 0; k < w; k++) s += c[end - k];
  return s / w;
}

/** Body color: green if close>=open else red. Wick geometry for extra patterns. */
export function candleVote(
  o: Float64Array,
  h: Float64Array,
  l: Float64Array,
  c: Float64Array,
  n: number,
  jpBias: -1 | 0 | 1,
): number {
  if (n < 2) return 0;
  const i = n - 1;
  const i0 = n - 2;
  const o1 = o[i], h1 = h[i], l1 = l[i], c1 = c[i];
  const o0 = o[i0], h0 = h[i0], l0 = l[i0], c0 = c[i0];
  const rng = h1 - l1;
  if (!(rng > 0) || !(c1 > 0)) return jpBias !== 0 ? jpBias * 0.55 : 0;
  const body = Math.abs(c1 - o1);
  const upper = h1 - Math.max(o1, c1);
  const lower = Math.min(o1, c1) - l1;
  const green = c1 >= o1;
  let v = 0;
  // JP classifier already tagged a named pattern on this close.
  if (jpBias !== 0) v += jpBias * 0.55;
  // Marubozu — almost no wicks, strong conviction in body color.
  if (body / rng > 0.85 && upper / rng < 0.08 && lower / rng < 0.08) {
    v += green ? 0.45 : -0.45;
  }
  // Hammer / shooting star (wick geometry, independent of JP names).
  if (lower / rng > 0.6 && body / rng < 0.35 && upper / rng < 0.15) v += 0.4;
  if (upper / rng > 0.6 && body / rng < 0.35 && lower / rng < 0.15) v -= 0.4;
  // Engulfing.
  const body0 = Math.abs(c0 - o0);
  if (c0 < o0 && c1 > o1 && o1 <= c0 && c1 >= o0 && body > body0) v += 0.42;
  if (c0 > o0 && c1 < o1 && o1 >= c0 && c1 <= o0 && body > body0) v -= 0.42;
  // Piercing / dark cloud (HLOC-aware two-bar).
  const mid0 = (o0 + c0) / 2;
  if (c0 < o0 && c1 > o1 && o1 < c0 && c1 > mid0) v += 0.32;
  if (c0 > o0 && c1 < o1 && o1 > c0 && c1 < mid0) v -= 0.32;
  // Tweezer bottom / top (shared wick extreme).
  if (c1 > 0 && Math.abs(l1 - l0) / c1 < 0.0015 && c0 < o0 && green) v += 0.22;
  if (c1 > 0 && Math.abs(h1 - h0) / c1 < 0.0015 && c0 > o0 && !green) v -= 0.22;
  // Harami: small body inside prior body → indecision, cancel weak events.
  if (
    body0 > 0 &&
    body < 0.5 * body0 &&
    Math.max(o1, c1) < Math.max(o0, c0) &&
    Math.min(o1, c1) > Math.min(o0, c0)
  ) {
    v *= 0.35;
  }
  // Three white soldiers / three black crows.
  if (n >= 3) {
    const i2 = n - 3;
    const g2 = c[i2] > o[i2], g1 = c0 > o0, g0 = green;
    if (g2 && g1 && g0 && c1 > c0 && c0 > c[i2]) v += 0.35;
    if (!g2 && !g1 && !g0 && c1 < c0 && c0 < c[i2]) v -= 0.35;
    // Morning / evening star.
    const o2 = o[i2], c2 = c[i2];
    const body2 = Math.abs(c2 - o2);
    const rng2 = h[i2] - l[i2];
    const small1 = Math.abs(c0 - o0) < 0.35 * Math.max(body2, rng2 * 0.4);
    if (c2 < o2 && small1 && green && c1 > (o2 + c2) / 2) v += 0.38;
    if (c2 > o2 && small1 && !green && c1 < (o2 + c2) / 2) v -= 0.38;
  }
  return clamp(v);
}

/** Close-only line: SMA cross, first break of N-bar high/low, pullback reclaim. */
export function lineVote(c: Float64Array, n: number): number {
  if (n < 10) return 0;
  const last = c[n - 1];
  const prev = c[n - 2];
  if (!(last > 0) || !(prev > 0)) return 0;
  let v = 0;
  const s8 = smaAt(c, n - 1, 8);
  const s21 = smaAt(c, n - 1, 21);
  const p8 = smaAt(c, n - 2, 8);
  const p21 = smaAt(c, n - 2, 21);
  if (p8 <= p21 && s8 > s21) v += 0.42; // golden-style cross on the close path
  if (p8 >= p21 && s8 < s21) v -= 0.42;
  // First close beyond the prior 20-bar extreme (not every new high in a trend).
  const lb = Math.min(20, n - 2);
  if (lb >= 8) {
    let hi = -Infinity, lo = Infinity;
    for (let k = 1; k <= lb; k++) {
      const x = c[n - 1 - k];
      if (x > hi) hi = x;
      if (x < lo) lo = x;
    }
    if (last > hi && prev < hi) v += 0.45;
    if (last < lo && prev > lo) v -= 0.45;
  }
  // Pullback reclaim: was below SMA8, now back above while SMA8 > SMA21.
  if (n >= 22 && s8 > s21 && prev < p8 && last > s8) v += 0.28;
  if (n >= 22 && s8 < s21 && prev > p8 && last < s8) v -= 0.28;
  return clamp(v);
}

/** HLOC bars: inside-break, outside, key reversal, NR7. No standing close-vs-open tilt. */
export function hlocVote(
  o: Float64Array,
  h: Float64Array,
  l: Float64Array,
  c: Float64Array,
  n: number,
): number {
  if (n < 3) return 0;
  const i = n - 1;
  const p = n - 2;
  const o1 = o[i], h1 = h[i], l1 = l[i], c1 = c[i];
  const h0 = h[p], l0 = l[p], c0 = c[p], o0 = o[p];
  const rng = h1 - l1;
  if (!(rng > 0)) return 0;
  let v = 0;
  const inside = h1 < h0 && l1 > l0;
  const outside = h1 > h0 && l1 < l0;
  // Key reversal: sell-off then close back through prior high (or inverse).
  if (c0 < o0 && c1 > h0) v += 0.5;
  if (c0 > o0 && c1 < l0) v -= 0.5;
  if (outside) v += c1 > o1 ? 0.32 : -0.32;
  // Inside-bar BREAK of the mother (this bar is the child expansion).
  if (n >= 4) {
    const m = n - 3;
    const motherH = h[m + 1], motherL = l[m + 1];
    const wasInside = h0 < motherH && l0 > motherL;
    if (wasInside && c1 > motherH) v += 0.4;
    if (wasInside && c1 < motherL) v -= 0.4;
  }
  if (inside) {
    // Coil only — not a directional event.
    v *= 0.15;
  }
  // NR7 — narrowest range of last 7 → breakout energy with close vs open tick.
  if (n >= 8) {
    const r1 = rng;
    let narrow = true;
    for (let k = 1; k <= 7; k++) {
      const rr = h[n - 1 - k] - l[n - 1 - k];
      if (rr > 0 && r1 >= rr) {
        narrow = false;
        break;
      }
    }
    if (narrow) v += c1 > o1 ? 0.28 : -0.28;
  }
  return clamp(v);
}

export class PointAndFigure {
  dir = 0;
  colHigh = 0;
  colLow = 0;
  lastPx = 0;
  private xHighs: number[] = [];
  private oLows: number[] = [];
  boxPct: number;
  reversal: number;

  constructor(boxPct = 0.002, reversal = 3) {
    this.boxPct = boxPct;
    this.reversal = Math.max(1, reversal | 0);
  }

  reset(): void {
    this.dir = 0;
    this.colHigh = 0;
    this.colLow = 0;
    this.lastPx = 0;
    this.xHighs = [];
    this.oLows = [];
  }

  private box(px: number): number {
    return Math.max(px * this.boxPct, 0.01);
  }

  /** Event vote only: column start, 3-box reversal, or X/O breakout this close. */
  onClose(px: number): number {
    if (!(px > 0)) return 0;
    const box = this.box(px);
    const prevDir = this.dir;
    const prevHigh = this.colHigh;
    const prevLow = this.colLow;
    if (this.dir === 0) {
      if (this.lastPx > 0) {
        if (px >= this.lastPx + box) {
          this.dir = 1;
          this.colHigh = px;
          this.colLow = this.lastPx;
        } else if (px <= this.lastPx - box) {
          this.dir = -1;
          this.colLow = px;
          this.colHigh = this.lastPx;
        }
      }
      this.lastPx = px;
      return this.dir !== 0 ? this.dir * 0.4 : 0;
    }
    const rev = this.reversal * box;
    let reversed = false;
    if (this.dir > 0) {
      if (px > this.colHigh) this.colHigh = px;
      else if (px <= this.colHigh - rev) {
        this.xHighs.push(this.colHigh);
        if (this.xHighs.length > 6) this.xHighs.shift();
        this.dir = -1;
        this.colLow = px;
        reversed = true;
      }
    } else {
      if (px < this.colLow || this.colLow === 0) this.colLow = px;
      else if (px >= this.colLow + rev) {
        this.oLows.push(this.colLow);
        if (this.oLows.length > 6) this.oLows.shift();
        this.dir = 1;
        this.colHigh = px;
        reversed = true;
      }
    }
    this.lastPx = px;
    let v = 0;
    if (reversed) v += this.dir * 0.7;
    // Breakout: X column makes a new high vs prior X highs — first print only.
    if (this.dir > 0 && this.xHighs.length) {
      const prior = Math.max(...this.xHighs);
      if (this.colHigh > prior && prevHigh <= prior) v += 0.45;
    }
    if (this.dir < 0 && this.oLows.length) {
      const prior = Math.min(...this.oLows);
      if (this.colLow < prior && (prevLow >= prior || prevDir >= 0)) v -= 0.45;
    }
    // Triple-top style: two similar X highs then this X breaks them.
    if (this.dir > 0 && this.xHighs.length >= 2) {
      const a = this.xHighs[this.xHighs.length - 1];
      const b = this.xHighs[this.xHighs.length - 2];
      if (a > 0 && Math.abs(a - b) / a < 0.004 && this.colHigh > Math.max(a, b) && prevHigh <= Math.max(a, b)) {
        v += 0.25;
      }
    }
    return clamp(v);
  }
}

export function hiddenVote(candle: number, line: number, hloc: number, pnf: number): { hidden: number; nAgree: number } {
  const signs = [sign3(candle), sign3(line), sign3(hloc), sign3(pnf)];
  let up = 0, down = 0;
  for (const s of signs) {
    if (s > 0) up++;
    else if (s < 0) down++;
  }
  const nAgree = Math.max(up, down);
  const dir = up > down ? 1 : down > up ? -1 : 0;
  if (nAgree < 2 || dir === 0) return { hidden: 0, nAgree };
  const amp = nAgree >= 4 ? 0.85 : nAgree >= 3 ? 0.55 : 0.28;
  let hidden = dir * amp;
  if (sign3(candle) !== 0 && sign3(pnf) !== 0 && sign3(candle) !== sign3(pnf)) {
    hidden *= 0.25;
  }
  return { hidden, nAgree };
}

export function crossFamilyAgree(candle: number, line: number, hloc: number, pnf: number): boolean {
  const barUp = sign3(candle) > 0 || sign3(hloc) > 0;
  const barDn = sign3(candle) < 0 || sign3(hloc) < 0;
  const pathUp = sign3(line) > 0 || sign3(pnf) > 0;
  const pathDn = sign3(line) < 0 || sign3(pnf) < 0;
  const barDir = barUp && !barDn ? 1 : barDn && !barUp ? -1 : 0;
  const pathDir = pathUp && !pathDn ? 1 : pathDn && !pathUp ? -1 : 0;
  return barDir !== 0 && barDir === pathDir;
}

export function fuseVotes(candle: number, line: number, hloc: number, pnf: number): ChartVote {
  const { hidden, nAgree } = hiddenVote(candle, line, hloc, pnf);
  const crossFamily = crossFamilyAgree(candle, line, hloc, pnf);
  const raw = 0.22 * candle + 0.22 * line + 0.22 * hloc + 0.22 * pnf + 0.12 * hidden;
  const score = crossFamily ? clamp(raw) : clamp(raw * 0.2);
  return {
    candle,
    line,
    hloc,
    pnf,
    hidden,
    score,
    nAgree,
    crossFamily,
    bias: crossFamily ? sign3(score, 0.12) : 0,
  };
}

/**
 * Live tape adapter. Call `onCandleClose(builder)` when a 1s (or N-ms) bar rolls.
 */
export class AdvancedChartEngine {
  readonly pnf: PointAndFigure;
  private readonly o: Float64Array;
  private readonly h: Float64Array;
  private readonly l: Float64Array;
  private readonly c: Float64Array;
  private n = 0;
  last: ChartVote = EMPTY;

  constructor(capacity = 96, boxPct = Number(process.env.HFT_PNF_BOX_PCT ?? 0.002)) {
    this.pnf = new PointAndFigure(boxPct, Number(process.env.HFT_PNF_REVERSAL ?? 3));
    this.o = new Float64Array(capacity);
    this.h = new Float64Array(capacity);
    this.l = new Float64Array(capacity);
    this.c = new Float64Array(capacity);
  }

  onFinishedOHLC(open: number, high: number, low: number, close: number, jpBias: -1 | 0 | 1 = 0): ChartVote {
    if (!(close > 0)) return this.last;
    const cap = this.o.length;
    if (this.n < cap) {
      const i = this.n;
      this.o[i] = open;
      this.h[i] = high;
      this.l[i] = low;
      this.c[i] = close;
      this.n++;
    } else {
      this.o.copyWithin(0, 1);
      this.h.copyWithin(0, 1);
      this.l.copyWithin(0, 1);
      this.c.copyWithin(0, 1);
      this.o[cap - 1] = open;
      this.h[cap - 1] = high;
      this.l[cap - 1] = low;
      this.c[cap - 1] = close;
    }
    const candle = candleVote(this.o, this.h, this.l, this.c, this.n, jpBias);
    const line = lineVote(this.c, this.n);
    const hloc = hlocVote(this.o, this.h, this.l, this.c, this.n);
    const pnf = this.pnf.onClose(close);
    this.last = fuseVotes(candle, line, hloc, pnf);
    return this.last;
  }

  onCandleClose(cb: CandleBuilder): ChartVote {
    const bar = cb.barAgo(0);
    if (!bar) return this.last;
    return this.onFinishedOHLC(bar.o, bar.h, bar.l, bar.c, patternBias(cb.lastPattern));
  }
}

export function chartProb(vote: ChartVote | undefined | null): number {
  if (!vote) return 0.5;
  if (!vote.crossFamily) return 0.5;
  const scale = vote.nAgree >= 3 ? 0.38 : 0.28;
  return Math.max(0, Math.min(1, 0.5 + vote.score * scale));
}
