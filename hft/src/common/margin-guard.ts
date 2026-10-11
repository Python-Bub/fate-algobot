/**
 * Block new HFT entries when margin / buying power is too tight.
 * Overnight cash is fortress's job (1.0×). HFT sizes from same-day DTBP.
 */
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { type AlpacaExecutor, type AccountSnapshot } from "./alpaca-exec.js";
import { stdoutTag } from "./logger.js";

const log = stdoutTag("[MARGIN]");

let cache: AccountSnapshot | null = null;
let lastFetchMs = 0;
let refreshTimer: ReturnType<typeof setInterval> | null = null;

function numEnv(name: string, fallback: number): number {
  const v = Number(process.env[name]);
  return Number.isFinite(v) ? v : fallback;
}

type BpPlan = {
  hft_day_budget?: number;
  hft_clip?: number;
  leftover_cash?: number;
  overnight_full?: boolean;
};

function loadPythonPlan(): BpPlan | null {
  for (const p of [
    resolve(process.cwd(), "data/ops/buying_power.json"),
    resolve(process.cwd(), "../data/ops/buying_power.json"),
  ]) {
    if (!existsSync(p)) continue;
    try {
      return JSON.parse(readFileSync(p, "utf8")) as BpPlan;
    } catch {
      return null;
    }
  }
  return null;
}

function hftPool(snap: AccountSnapshot): number {
  const plan = loadPythonPlan();
  if (plan && Number(plan.hft_day_budget) > 0) return Number(plan.hft_day_budget);
  const useDtbp = process.env.HFT_USE_DTBP !== "false";
  const day = useDtbp ? snap.daytradingBuyingPower || snap.buyingPower : snap.buyingPower;
  return Math.max(0, day * numEnv("HFT_BP_USE_FRAC", 0.85) - numEnv("HFT_BP_RESERVE_USD", 200));
}

export function startMarginGuard(broker: AlpacaExecutor): void {
  if (process.env.HFT_MARGIN_GUARD === "false") return;
  const refreshMs = numEnv("HFT_MARGIN_REFRESH_MS", 15_000);
  const refresh = async (): Promise<void> => {
    const acct = await broker.getAccount();
    if (acct) {
      cache = acct;
      lastFetchMs = Date.now();
    }
  };
  void refresh();
  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = setInterval(() => void refresh(), refreshMs);
  refreshTimer.unref();
}

export function marginSnapshot(): AccountSnapshot | null {
  return cache;
}

export function canEnterBuy(notionalUsd: number): { ok: boolean; reason?: string } {
  if (process.env.HFT_MARGIN_GUARD === "false") return { ok: true };
  if (!cache) {
    if (Date.now() - lastFetchMs > 30_000) {
      return { ok: false, reason: "no-account-snapshot" };
    }
    return { ok: true };
  }

  const minBp = numEnv("HFT_MIN_BUYING_POWER_USD", 2000);
  const minEquityMm = numEnv("HFT_MIN_EQUITY_TO_MM_RATIO", 1.15);
  const pool = hftPool(cache);
  if (notionalUsd > pool) {
    return {
      ok: false,
      reason: `bp-room ${pool.toFixed(0)} < notional ${notionalUsd.toFixed(0)}`,
    };
  }
  if (pool < minBp && cache.buyingPower < minBp && cache.daytradingBuyingPower < minBp) {
    return { ok: false, reason: `hft-pool ${pool.toFixed(0)} < min ${minBp}` };
  }
  if (cache.maintenanceMargin > 0) {
    const ratio = cache.equity / cache.maintenanceMargin;
    if (ratio < minEquityMm) {
      return {
        ok: false,
        reason: `equity/mm ${ratio.toFixed(2)} < ${minEquityMm}`,
      };
    }
  }
  return { ok: true };
}

export function logMarginSkip(ticker: string, reason: string): void {
  log("skip-entry", { ticker, reason, bp: cache?.buyingPower, equity: cache?.equity });
}

/**
 * Per-entry notional from buying power when HFT_USE_BP_SIZING=true (default).
 * Targets deploying HFT_BP_USE_FRAC of BP across HFT_MAX_CONCURRENT_SLOTS round-trips.
 */
export function resolveHftNotionalUsd(baseNotional: number): number {
  if (process.env.HFT_USE_BP_SIZING === "false") {
    return Math.max(100, baseNotional);
  }
  const floor = numEnv("HFT_MIN_ORDER_NOTIONAL", 200);
  const cap = numEnv("HFT_MAX_ORDER_NOTIONAL", 0) || numEnv("FORTRESS_GO_LIVE_MAX_NOTIONAL", 0);
  const plan = loadPythonPlan();
  if (plan && Number(plan.hft_clip) > 0) {
    const clip = Number(plan.hft_clip);
    const hi = cap > 0 ? Math.min(cap, clip) : clip;
    return Math.max(floor, hi);
  }
  const slots = Math.max(1, numEnv("HFT_MAX_CONCURRENT_SLOTS", 16));
  if (cache && (cache.daytradingBuyingPower > 0 || cache.buyingPower > 0)) {
    const deployable = hftPool(cache);
    const slot = deployable / slots;
    const hi = cap > 0 ? Math.min(cap, slot) : slot;
    return Math.max(floor, hi);
  }
  return Math.max(floor, Math.min(cap > 0 ? cap : 2_500, baseNotional));
}

/** Apply floor/cap AFTER confidence/news multipliers (resolveHftNotionalUsd clamps too early). */
export function clampHftNotionalUsd(notional: number): number {
  const floor = numEnv("HFT_MIN_ORDER_NOTIONAL", 200);
  const cap = numEnv("HFT_MAX_ORDER_NOTIONAL", 0) || numEnv("FORTRESS_GO_LIVE_MAX_NOTIONAL", 0);
  if (!(notional > 0) || !Number.isFinite(notional)) return floor;
  if (cap > 0) return Math.max(floor, Math.min(cap, notional));
  return Math.max(floor, notional);
}
