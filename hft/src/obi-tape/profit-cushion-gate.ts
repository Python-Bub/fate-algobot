/**
 * Read fortress "earned" legs from data/intel/profit_cushion_gate.json.
 * HFT mean-reversion only fires on symbols that already have a green cushion.
 */
import fs from "node:fs";
import path from "node:path";

interface GateFile {
  earned?: Record<string, number>;
  min_pct?: number;
  require_cushion?: boolean;
  hft_boost?: boolean;
  updated_ms?: number;
}

let cache: { mtimeMs: number; data: GateFile } | null = null;

function gatePath(): string {
  return (
    process.env.PROFIT_CUSHION_GATE_PATH ??
    path.join(process.cwd(), "..", "data", "intel", "profit_cushion_gate.json")
  );
}

function loadGate(): GateFile {
  const p = gatePath();
  try {
    const st = fs.statSync(p);
    if (cache && cache.mtimeMs === st.mtimeMs) return cache.data;
    const data = JSON.parse(fs.readFileSync(p, "utf8")) as GateFile;
    cache = { mtimeMs: st.mtimeMs, data };
    return data;
  } catch {
    return {};
  }
}

export function requireProfitCushion(): boolean {
  if (process.env.HFT_JP_ULTRA === "true") return false;
  if (process.env.HFT_REQUIRE_PROFIT_CUSHION === "false") return false;
  const g = loadGate();
  if (g.require_cushion === false) return false;
  return true;
}

export function isEarnedSymbol(ticker: string): boolean {
  if (!requireProfitCushion()) return true;
  const earned = loadGate().earned ?? {};
  return Object.prototype.hasOwnProperty.call(earned, ticker.toUpperCase());
}

export function earnedGainFrac(ticker: string): number | null {
  const earned = loadGate().earned ?? {};
  const g = earned[ticker.toUpperCase()];
  return typeof g === "number" ? g : null;
}

/** Faster MR cadence once fortress leg is in the green. */
export function mrTimingFor(ticker: string, baseExitMs: number, baseDebounceMs: number): {
  exitMs: number;
  debounceMs: number;
} {
  if (!isEarnedSymbol(ticker)) {
    return { exitMs: baseExitMs, debounceMs: baseDebounceMs };
  }
  const exitMs = Number(process.env.HFT_EARNED_EXIT_MS ?? Math.max(2500, baseExitMs * 0.55));
  const debounceMs = Number(process.env.HFT_EARNED_DEBOUNCE_MS ?? Math.max(2000, baseDebounceMs * 0.45));
  return { exitMs, debounceMs };
}
