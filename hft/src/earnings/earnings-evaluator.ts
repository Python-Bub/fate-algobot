/**
 * ============================================================================
 * PHASE 2 — SUB-SECOND SIGNAL GENERATION & EVALUATION
 * ============================================================================
 *
 *   • In-memory zero-allocation state machine per ticker (`TickerState`).
 *     Pre-allocated `Float64Array(8)` slot — no per-update object creation.
 *   • Earnings surprise = (reported - consensus) / |consensus|. The reported
 *     numbers are pulled out of the raw frame with simple `indexOf` + numeric
 *     parsing — no regex, no schema validation.
 *   • Volatility filter: rolling micro-VWAP via `VwapRing(windowMs)`. Trades
 *     are skipped when last-trade price has drifted > `VWAP_BAND_FRAC` from
 *     VWAP (toxic / phantom liquidity guard).
 *   • Order sizing = min(notional / mid_px, available_top_of_book_qty).
 */
import { CFG, confidenceNotionalMult } from "../common/config.js";
import { VwapRing } from "../common/buffers.js";
import { stdoutTag } from "../common/logger.js";
import { type EarningsFrame } from "./earnings-ingestor.js";

const log = stdoutTag("[EVAL]");

/** Slots in the per-ticker Float64Array. */
const S_BID = 0;
const S_ASK = 1;
const S_BID_SZ = 2;
const S_ASK_SZ = 3;
const S_LAST_PX = 4;
const S_LAST_SZ = 5;
const S_LAST_TS_MS = 6;
const S_NUM_TRADES = 7;
const SLOT_COUNT = 8;

const VWAP_BAND_FRAC = 0.0075; // skip if last px is >0.75% from 10s VWAP

export type Side = "buy" | "sell";

export interface EarningsTrigger {
  ticker: string;
  side: Side;
  surprisePct: number;
  rationale: string;
  limitPx: number;
  qty: number;
  confidence: number;
  notionalUsd: number;
  receivedNs: bigint;
}

export class TickerState {
  readonly slot: Float64Array;
  readonly vwap: VwapRing;
  private triggered = false;

  constructor(public readonly ticker: string, vwapWindowMs: number) {
    this.slot = new Float64Array(SLOT_COUNT);
    this.vwap = new VwapRing(2048, vwapWindowMs);
  }

  updateQuote(bid: number, ask: number, bidSz: number, askSz: number): void {
    if (bid > 0) this.slot[S_BID] = bid;
    if (ask > 0) this.slot[S_ASK] = ask;
    if (bidSz > 0) this.slot[S_BID_SZ] = bidSz;
    if (askSz > 0) this.slot[S_ASK_SZ] = askSz;
  }

  updateTrade(px: number, sz: number, tsMs: number): void {
    if (px <= 0 || sz <= 0) return;
    this.slot[S_LAST_PX] = px;
    this.slot[S_LAST_SZ] = sz;
    this.slot[S_LAST_TS_MS] = tsMs;
    this.slot[S_NUM_TRADES]++;
    this.vwap.add(tsMs, px, sz);
  }

  mid(): number {
    const b = this.slot[S_BID];
    const a = this.slot[S_ASK];
    if (b > 0 && a > 0) return (a + b) * 0.5;
    return this.slot[S_LAST_PX];
  }

  bid(): number {
    return this.slot[S_BID];
  }
  ask(): number {
    return this.slot[S_ASK];
  }
  bidSz(): number {
    return this.slot[S_BID_SZ];
  }
  askSz(): number {
    return this.slot[S_ASK_SZ];
  }
  vwapNow(): number {
    return this.vwap.vwap();
  }
  markTriggered(): void {
    this.triggered = true;
  }
  hasTriggered(): boolean {
    return this.triggered;
  }
}

/**
 * Parse a single number after a key (`"key":NN.NN`).  Returns NaN if missing.
 * Zero-regex; uses `indexOf` + manual digit walk.
 */
function jsonNumberAfter(buf: string, key: string): number {
  const i = buf.indexOf(`"${key}"`);
  if (i === -1) return NaN;
  let p = i + key.length + 2;
  // skip whitespace, colon, whitespace, optional quote
  while (p < buf.length && (buf.charCodeAt(p) === 0x20 || buf.charCodeAt(p) === 0x3a)) p++;
  let sign = 1;
  if (buf.charCodeAt(p) === 0x22) p++; // quoted number
  if (buf.charCodeAt(p) === 0x2d) {
    sign = -1;
    p++;
  } else if (buf.charCodeAt(p) === 0x2b) {
    p++;
  }
  let n = 0;
  let frac = 0;
  let fracDiv = 1;
  let inFrac = false;
  while (p < buf.length) {
    const c = buf.charCodeAt(p);
    if (c === 0x2e) {
      inFrac = true;
      p++;
      continue;
    }
    if (c < 0x30 || c > 0x39) break;
    if (inFrac) {
      frac = frac * 10 + (c - 0x30);
      fracDiv *= 10;
    } else {
      n = n * 10 + (c - 0x30);
    }
    p++;
  }
  const val = sign * (n + frac / fracDiv);
  return p === i + key.length + 2 ? NaN : val;
}

/** Parse a known key/value pair like `"side":"buy"`. */
function jsonStringAfter(buf: string, key: string): string {
  const i = buf.indexOf(`"${key}"`);
  if (i === -1) return "";
  let p = i + key.length + 2;
  while (p < buf.length && (buf.charCodeAt(p) === 0x20 || buf.charCodeAt(p) === 0x3a)) p++;
  if (buf.charCodeAt(p) !== 0x22) return "";
  p++;
  const start = p;
  while (p < buf.length && buf.charCodeAt(p) !== 0x22) p++;
  return buf.slice(start, p);
}

export class EarningsEvaluator {
  private readonly states = new Map<string, TickerState>();

  constructor(tickers: readonly string[]) {
    for (const t of tickers) this.states.set(t.toUpperCase(), new TickerState(t.toUpperCase(), CFG.earn.vwapWindowMs));
  }

  /** Plug trades / quotes from a separate market-data stream into the same state. */
  ingestQuote(ticker: string, bid: number, ask: number, bidSz: number, askSz: number): void {
    const s = this.states.get(ticker.toUpperCase());
    if (s) s.updateQuote(bid, ask, bidSz, askSz);
  }
  ingestTrade(ticker: string, px: number, sz: number, tsMs: number): void {
    const s = this.states.get(ticker.toUpperCase());
    if (s) s.updateTrade(px, sz, tsMs);
  }

  /** Inspect an earnings frame for surprise + emit a trigger if it clears the bar. */
  evaluate(frame: EarningsFrame): EarningsTrigger | null {
    const state = this.states.get(frame.ticker);
    if (!state || state.hasTriggered()) return null;

    const text = frame.rawText;

    // Most news wires expose these keys; we look for the most useful set.  Any
    // missing key returns NaN and the evaluator gracefully bails.
    const epsReported = jsonNumberAfter(text, "eps_actual") || jsonNumberAfter(text, "eps");
    const epsConsensus = jsonNumberAfter(text, "eps_estimate") || jsonNumberAfter(text, "eps_consensus");
    const revReported = jsonNumberAfter(text, "revenue_actual") || jsonNumberAfter(text, "revenue");
    const revConsensus = jsonNumberAfter(text, "revenue_estimate") || jsonNumberAfter(text, "revenue_consensus");
    const guidance = jsonStringAfter(text, "guidance").toLowerCase();

    const epsSurprise = Number.isFinite(epsReported) && Number.isFinite(epsConsensus) && epsConsensus !== 0
      ? ((epsReported - epsConsensus) / Math.abs(epsConsensus)) * 100
      : NaN;
    const revSurprise = Number.isFinite(revReported) && Number.isFinite(revConsensus) && revConsensus !== 0
      ? ((revReported - revConsensus) / Math.abs(revConsensus)) * 100
      : NaN;

    // Pick the dominant signed surprise; tie-break favours the larger absolute.
    const candidates: { name: string; pct: number }[] = [];
    if (Number.isFinite(epsSurprise)) candidates.push({ name: "eps", pct: epsSurprise });
    if (Number.isFinite(revSurprise)) candidates.push({ name: "revenue", pct: revSurprise });
    if (guidance === "raised") candidates.push({ name: "guidance_raised", pct: +CFG.earn.triggerPct + 0.01 });
    if (guidance === "lowered" || guidance === "cut") candidates.push({ name: "guidance_cut", pct: -CFG.earn.triggerPct - 0.01 });
    if (candidates.length === 0) return null;
    candidates.sort((a, b) => Math.abs(b.pct) - Math.abs(a.pct));
    const winner = candidates[0];

    if (Math.abs(winner.pct) < CFG.earn.triggerPct) return null;

    // Confidence: 0 at trigger threshold, 1 at 2× threshold (saturating).
    // Floor `HFT_MIN_CONFIDENCE=0.65` → require |surprise| ≥ 1.65× threshold.
    const conf = Math.max(0, Math.min(1, Math.abs(winner.pct) / (2 * CFG.earn.triggerPct)));
    const sizeMult = confidenceNotionalMult(conf);
    if (sizeMult <= 0) {
      log("below-conf-floor", { ticker: frame.ticker, conf, pct: winner.pct });
      return null;
    }

    // Volatility filter: skip if last px far from rolling VWAP — toxic liquidity.
    const vw = state.vwapNow();
    const lastPx = state.slot[S_LAST_PX];
    if (vw > 0 && lastPx > 0 && Math.abs(lastPx - vw) / vw > VWAP_BAND_FRAC) {
      log("vwap-band-skip", { ticker: frame.ticker, lastPx, vwap: vw });
      return null;
    }

    const side: Side = winner.pct >= 0 ? "buy" : "sell";
    const ask = state.ask() || lastPx;
    const bid = state.bid() || lastPx;
    if (ask <= 0 || bid <= 0) {
      log("no-nbbo-skip", { ticker: frame.ticker });
      return null;
    }
    const topQty = side === "buy" ? state.askSz() : state.bidSz();
    const px = side === "buy" ? ask + CFG.tickSize * CFG.earn.tickOffset : bid - CFG.tickSize * CFG.earn.tickOffset;
    const notional = CFG.earn.notional * sizeMult;
    const desiredQty = Math.max(1, Math.floor(notional / Math.max(px, 1)));
    const qty = Math.max(1, Math.min(desiredQty, Math.max(1, Math.floor(topQty || desiredQty))));

    state.markTriggered();
    return {
      ticker: frame.ticker,
      side,
      surprisePct: winner.pct,
      rationale: winner.name,
      limitPx: Math.round(px * 100) / 100,
      qty,
      confidence: conf,
      notionalUsd: notional,
      receivedNs: frame.receivedNs,
    };
  }
}
