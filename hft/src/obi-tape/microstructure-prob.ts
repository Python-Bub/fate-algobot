/**
 * Microstructure probability — upward/downward move likelihood from live book,
 * tape, momentum, JP candles, spread, pair/news, and optional exec-delay tilt.
 *
 * Source of truth (Python mirror): analytics/sleeve_weights.py HFT_PCT
 * NEVER read RANK_W_CRAMER / RANK_W_MACRO / RANK_W_VALUE / buy-hold — those are LT sleeves.
 */
import type { L2Book } from "./l2-book.js";
import type { TapeVelocity } from "./tape-velocity.js";
import { bestLevelObi, microPriceDriftBps } from "./micro-price.js";
import { spreadBps } from "./order-pricing.js";
import { loadExecDelayMs } from "./exec-delay.js";

export type MicroInputs = {
  book: L2Book;
  tape: TapeVelocity;
  trend: number;
  vwap: number;
  lastClose: number;
  pairZ?: number;
  newsSentiment?: number;
  /** JP candle patternBias: +1 bullish, -1 bearish, 0 none/doji. */
  jpBias?: -1 | 0 | 1;
  /** Optional stat-arb / residual z (negative = buy underpriced). */
  statArbZ?: number;
  /** Optional 4-chart stack score [-1,1] (candles+line+HLOC+PnF). */
  chartScore?: number;
  /** How many of the four chart representations agree (0-4). */
  chartAgree?: number;
  /** True when bar-geometry (candle/HLOC) agrees with close-path (line/PnF). */
  chartCrossFamily?: boolean;
  /** Optional index-tape tilt [-1,1] from SPY/QQQ (0 = unknown). */
  indexTilt?: number;
};

function clamp01(x: number): number {
  return Math.max(0, Math.min(1, x));
}

/** Log-odds fuse (Jaynes). Linear p-mix understates agreeing microstructure. */
function logit(p: number): number {
  const x = Math.min(1 - 1e-9, Math.max(1e-9, p));
  return Math.log(x / (1 - x));
}

function sigmoid(z: number): number {
  const zz = Math.max(-20, Math.min(20, z));
  return 0.5 * (1 + Math.tanh(0.5 * zz));
}

function logitBlend(pairs: Array<[number, number]>): number {
  let wSum = 0;
  let acc = 0;
  for (const [w, p] of pairs) {
    const ww = Math.max(0, w);
    if (!(ww > 0) || !Number.isFinite(p)) continue;
    wSum += ww;
    acc += ww * logit(p);
  }
  if (!(wSum > 0)) return 0.5;
  return sigmoid(acc / wSum);
}

function obiProb(book: L2Book): number {
  const depth = clamp01((book.obi + 1) / 2);
  const top = clamp01((bestLevelObi(book) + 1) / 2);
  return clamp01(depth * 0.55 + top * 0.45);
}

function microPriceProb(book: L2Book): number {
  const bps = microPriceDriftBps(book);
  return clamp01(0.5 + bps / 20);
}

function spreadProb(book: L2Book): number {
  const bps = spreadBps(book);
  const tight = Number(process.env.HFT_TIGHT_SPREAD_BPS ?? 25);
  if (!Number.isFinite(bps)) return 0.5;
  if (bps <= tight) return 0.62;
  if (bps <= tight * 2) return 0.52;
  return 0.38;
}

function tapeProb(tape: TapeVelocity, burst: boolean): number {
  if (burst) return 0.68;
  const ratio = tape.lastBurstRatio > 0 ? tape.lastBurstRatio : 1;
  return clamp01(0.45 + Math.min(0.25, (ratio - 1) * 0.08));
}

function momentumProb(vwap: number, lastClose: number, trend: number): number {
  if (!(vwap > 0 && lastClose > 0)) return 0.5;
  const vsVwap = (lastClose - vwap) / vwap;
  const trendP = clamp01(0.5 + trend * 0.15);
  const vwapP = clamp01(0.5 + vsVwap * 80);
  return clamp01(trendP * 0.55 + vwapP * 0.45);
}

function pairProb(pairZ: number | undefined): number {
  if (pairZ == null || !Number.isFinite(pairZ)) return 0.5;
  if (pairZ < -1.5) return 0.62;
  if (pairZ < -0.5) return 0.56;
  if (pairZ > 1.5) return 0.38;
  if (pairZ > 0.5) return 0.44;
  return 0.5;
}

function newsProb(sentiment: number | undefined): number {
  if (sentiment == null || !Number.isFinite(sentiment)) return 0.5;
  return clamp01(0.5 + sentiment * 0.35);
}

function jpCandleProb(bias: -1 | 0 | 1 | undefined): number {
  if (bias == null) return 0.5;
  if (bias > 0) return 0.66;
  if (bias < 0) return 0.34;
  return 0.5;
}

function statArbProb(z: number | undefined): number {
  if (z == null || !Number.isFinite(z)) return 0.5;
  // Mean-revert: negative residual → buy.
  return clamp01(0.5 - z * 0.12);
}

function chartProb(
  score: number | undefined,
  agree: number | undefined,
  crossFamily?: boolean,
): number {
  if (score == null || !Number.isFinite(score)) return 0.5;
  if (crossFamily === false) return 0.5;
  const n = agree ?? 0;
  // Lone chart folklore stays near fair. Cross-family agreement is the edge.
  if (n < 2) return 0.5;
  const scale = n >= 3 ? 0.38 : 0.28;
  return clamp01(0.5 + score * scale);
}

function indexEtfProb(tilt: number | undefined): number {
  if (tilt == null || !Number.isFinite(tilt)) return 0.5;
  return clamp01(0.5 + tilt * 0.15);
}

/**
 * Composite upward probability [0,1] from full HFT technique stack.
 * Weights from env (sleeve export) — normalized so they always sum to 1.
 */
export function upwardProbability(inp: MicroInputs, tapeBurst = false): number {
  const raw: Array<[number, number]> = [
    [Number(process.env.HFT_W_OBI_PROB ?? 0.26), obiProb(inp.book)],
    [Number(process.env.HFT_W_TAPE_PROB ?? 0.23), tapeProb(inp.tape, tapeBurst)],
    [Number(process.env.HFT_W_MOMENTUM_PROB ?? 0.15), momentumProb(inp.vwap, inp.lastClose, inp.trend)],
    [Number(process.env.HFT_W_MICRO_PRICE_PROB ?? 0.12), microPriceProb(inp.book)],
    [Number(process.env.HFT_W_SPREAD_PROB ?? 0.1), spreadProb(inp.book)],
    [Number(process.env.HFT_W_PAIR_PROB ?? 0.04), pairProb(inp.pairZ)],
    [Number(process.env.HFT_W_NEWS_PROB ?? 0), newsProb(inp.newsSentiment)],
    [Number(process.env.HFT_W_JP_CANDLE_PROB ?? 0.04), jpCandleProb(inp.jpBias)],
    [Number(process.env.HFT_W_CHART_PROB ?? 0.03), chartProb(inp.chartScore, inp.chartAgree, inp.chartCrossFamily)],
    [Number(process.env.HFT_W_STAT_ARB_MICRO ?? 0.02), statArbProb(inp.statArbZ)],
    [Number(process.env.HFT_W_INDEX_ETF ?? 0.01), indexEtfProb(inp.indexTilt)],
  ];
  let wSum = 0;
  for (const [w] of raw) wSum += Math.max(0, w);
  if (!(wSum > 0)) return 0.5;
  let p =
    process.env.HFT_MICRO_FUSE === "linear"
      ? raw.reduce((s, [w, score]) => s + (Math.max(0, w) / wSum) * score, 0)
      : logitBlend(raw);

  // Exec delay penalty: remote WiFi/VPN → require slightly stronger edge.
  const delayMs = loadExecDelayMs();
  const budget = Number(process.env.OBI_BUDGET_LATENCY_MS ?? 25);
  if (delayMs > budget && process.env.HFT_EXEC_DELAY_PENALTY !== "false") {
    const over = Math.min(1, (delayMs - budget) / Math.max(budget, 1));
    p -= over * Number(process.env.HFT_EXEC_DELAY_PENALTY_MAX ?? 0.04);
  }
  return clamp01(p);
}

export function shouldEnterLong(inp: MicroInputs, tapeBurst = false): boolean {
  const minP = Number(process.env.HFT_MICRO_MIN_UP_PROB ?? 0.52);
  return upwardProbability(inp, tapeBurst) >= minP;
}

export function shouldEnterShort(inp: MicroInputs, tapeBurst = false): boolean {
  const minP = Number(process.env.HFT_MICRO_MIN_DOWN_PROB ?? 0.52);
  return upwardProbability(inp, tapeBurst) <= 1 - minP;
}
