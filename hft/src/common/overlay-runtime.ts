/**
 * Live overlay knobs written by self_modify/code_evolver.py (Python).
 * Mtime-cached so HFT picks up new code without a full process restart.
 */
import { existsSync, readFileSync, statSync } from "node:fs";
import { resolve } from "node:path";

const SELF_IMPROVE_PATHS = [
  resolve(process.cwd(), "data/self_improve/hft_runtime.json"),
  resolve(process.cwd(), "../data/self_improve/hft_runtime.json"),
];
const CORTEX_PATHS = [
  resolve(process.cwd(), "data/cortex/cortex_runtime.json"),
  resolve(process.cwd(), "../data/cortex/cortex_runtime.json"),
];
const GAINZ_SIGNAL_PATHS = [
  resolve(process.cwd(), "data/intel/gainz_v2_signals.json"),
  resolve(process.cwd(), "../data/intel/gainz_v2_signals.json"),
];

let cachedMtime = 0;
let confidenceFloorDelta = 0;
let gainzBuys: string[] = [];

function readDelta(paths: string[], key: string): number {
  for (const p of paths) {
    if (!existsSync(p)) continue;
    try {
      const doc = JSON.parse(readFileSync(p, "utf8")) as Record<string, number>;
      const d = Number(doc[key]);
      if (Number.isFinite(d)) return d;
    } catch {
      /* try next */
    }
  }
  return 0;
}

function readJson(paths: string[]): Record<string, unknown> | null {
  for (const p of paths) {
    if (!existsSync(p)) continue;
    try {
      return JSON.parse(readFileSync(p, "utf8")) as Record<string, unknown>;
    } catch {
      /* try next */
    }
  }
  return null;
}

function readBuys(): string[] {
  const runtime = readJson(SELF_IMPROVE_PATHS);
  const fromRt = runtime?.gainz_buys;
  if (Array.isArray(fromRt) && fromRt.length) {
    return fromRt.map((s) => String(s).toUpperCase()).filter(Boolean);
  }
  const sig = readJson(GAINZ_SIGNAL_PATHS);
  const fromSig = sig?.buys;
  if (Array.isArray(fromSig) && fromSig.length) {
    return fromSig.map((s) => String(s).toUpperCase()).filter(Boolean);
  }
  return [];
}

function refresh(): void {
  let newest = cachedMtime;
  for (const paths of [SELF_IMPROVE_PATHS, CORTEX_PATHS, GAINZ_SIGNAL_PATHS]) {
    for (const p of paths) {
      if (!existsSync(p)) continue;
      try {
        newest = Math.max(newest, statSync(p).mtimeMs);
      } catch {
        /* skip */
      }
    }
  }
  if (newest <= cachedMtime) return;
  cachedMtime = newest;
  let overlay = readDelta(SELF_IMPROVE_PATHS, "confidence_floor_delta");
  const cortex = readDelta(CORTEX_PATHS, "hft_conf_delta");
  gainzBuys = readBuys();
  if (gainzBuys.length > 0 && overlay === 0) {
    overlay = -0.02;
  }
  confidenceFloorDelta = Math.max(-0.08, Math.min(0.08, overlay + cortex));
}

/** Negative delta eases HFT gates (more trades) when under-deployed or losing to SPY. */
export function hftConfidenceFloorDelta(): number {
  refresh();
  return confidenceFloorDelta;
}

/** Gainz 1m–1h BUY names from the rotating universe scan (empty if none). */
export function gainzBuyTickers(): string[] {
  refresh();
  return gainzBuys;
}
