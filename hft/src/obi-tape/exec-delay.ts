/**
 * Exec-delay calibration — reads probe output so WiFi/VPN RTT is factored into
 * pick gates and decision budgets. Probe: tools/hft_exec_delay_probe.py
 */
import fs from "node:fs";
import path from "node:path";

export type ExecDelayDoc = {
  updated_ms?: number;
  rtt_ms_p50?: number;
  rtt_ms_p95?: number;
  rtt_ms_mean?: number;
  recommended_budget_ms?: number;
  path?: string;
  samples?: number;
};

let cache: { mtimeMs: number; doc: ExecDelayDoc } | null = null;

function delayPath(): string {
  const root = process.env.FATE_ROOT || path.join(process.cwd(), "..");
  return (
    process.env.HFT_EXEC_DELAY_PATH ||
    path.join(root, "data", "ops", "hft_exec_delay.json")
  );
}

function loadDoc(): ExecDelayDoc {
  const p = delayPath();
  try {
    const st = fs.statSync(p);
    if (cache && cache.mtimeMs === st.mtimeMs) return cache.doc;
    const doc = JSON.parse(fs.readFileSync(p, "utf8")) as ExecDelayDoc;
    cache = { mtimeMs: st.mtimeMs, doc };
    return doc;
  } catch {
    return {};
  }
}

/** Best estimate of round-trip wire delay to Alpaca (ms), capped for gates. */
export function loadExecDelayMs(): number {
  const env = Number(process.env.HFT_EXEC_DELAY_MS ?? 0);
  const cap = Number(process.env.HFT_EXEC_DELAY_CAP_MS ?? 250);
  let raw = 0;
  if (env > 0) {
    raw = env;
  } else {
    const doc = loadDoc();
    const maxAgeMs = Number(process.env.HFT_EXEC_DELAY_MAX_AGE_MS ?? 3_600_000);
    if (doc.updated_ms && maxAgeMs > 0 && Date.now() - doc.updated_ms > maxAgeMs) {
      return 0;
    }
    // Prefer recommended_budget (already capped) over raw pathological HTTP p50.
    raw = Number(
      doc.recommended_budget_ms ?? doc.rtt_ms_p50 ?? doc.rtt_ms_mean ?? 0,
    ) || 0;
  }
  if (cap > 0) return Math.min(raw, cap);
  return raw;
}

/** Decision budget = base + measured RTT cushion (so remote links don't false-miss). */
export function effectiveBudgetMs(baseMs: number): number {
  if (process.env.HFT_SKIP_LATENCY_BUDGET === "true") return Number.POSITIVE_INFINITY;
  const delay = loadExecDelayMs();
  const mult = Number(process.env.HFT_EXEC_DELAY_BUDGET_MULT ?? 1.25);
  return Math.max(baseMs, delay * mult + Number(process.env.HFT_EXEC_DELAY_BUDGET_PAD_MS ?? 5));
}

/** Extra fee-bps proxy for edge gates when RTT is high (slippage risk). Capped. */
export function execDelayFeeBps(): number {
  const delay = loadExecDelayMs();
  if (!(delay > 0)) return 0;
  const excess = Math.max(0, delay - Number(process.env.HFT_EXEC_DELAY_BASELINE_MS ?? 20));
  const raw = (excess / 10) * Number(process.env.HFT_EXEC_DELAY_BPS_PER_10MS ?? 0.5);
  const maxBps = Number(process.env.HFT_EXEC_DELAY_MAX_FEE_BPS ?? 8);
  return Math.min(maxBps, raw);
}
