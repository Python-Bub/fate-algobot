/**
 * Block new HFT entries when margin / buying power is too tight.
 */
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

export function __setMarginCacheForTest(snap: AccountSnapshot | null): void {
  cache = snap;
  lastFetchMs = snap ? Date.now() : 0;
}

export function canEnterBuy(notionalUsd: number): { ok: boolean; reason?: string } {
  if (process.env.HFT_MARGIN_GUARD === "false") return { ok: true };
  if (!cache) {
    if (Date.now() - lastFetchMs > 30_000) {
      return { ok: false, reason: "no-account-snapshot" };
    }
    return { ok: true };
  }

  const minCash = numEnv("HFT_MIN_CASH_TO_BUY", 250);
  if (!(cache.cash >= minCash)) {
    return { ok: false, reason: `cash ${cache.cash.toFixed(0)} < min ${minCash}` };
  }

  const maxGross = numEnv("HFT_MAX_GROSS_FRAC", numEnv("MAX_GROSS_LEVERAGE", 1.0));
  if (cache.equity > 0 && cache.longMarketValue > cache.equity * maxGross + 1) {
    return {
      ok: false,
      reason: `over-gross ${cache.longMarketValue.toFixed(0)} > equity ${cache.equity.toFixed(0)} * ${maxGross}`,
    };
  }

  const minBp = numEnv("HFT_MIN_BUYING_POWER_USD", 5000);
  const bpFrac = numEnv("HFT_BP_USE_FRAC", 0.35);
  const sizeFromCash = process.env.HFT_SIZE_FROM_CASH !== "false";
  const reserve = sizeFromCash
    ? numEnv("HFT_CASH_RESERVE_USD", 500)
    : numEnv("HFT_BP_RESERVE_USD", 10_000);
  const minEquityMm = numEnv("HFT_MIN_EQUITY_TO_MM_RATIO", 1.15);

  const pool = sizeFromCash ? Math.max(0, cache.cash) : cache.buyingPower;
  const bpRoom = Math.max(0, pool * bpFrac - reserve);
  if (notionalUsd > bpRoom) {
    return {
      ok: false,
      reason: `bp-room ${bpRoom.toFixed(0)} < notional ${notionalUsd.toFixed(0)}`,
    };
  }
  if (!sizeFromCash && cache.buyingPower < minBp) {
    return { ok: false, reason: `buying_power ${cache.buyingPower.toFixed(0)} < min ${minBp}` };
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
  const cap = numEnv("HFT_MAX_ORDER_NOTIONAL", numEnv("FORTRESS_GO_LIVE_MAX_NOTIONAL", 2_500));
  const slots = Math.max(1, numEnv("HFT_MAX_CONCURRENT_SLOTS", 12));
  const bpFrac = numEnv("HFT_BP_USE_FRAC", 0.8);
  const sizeFromCash = process.env.HFT_SIZE_FROM_CASH !== "false";
  const reserve = sizeFromCash
    ? numEnv("HFT_CASH_RESERVE_USD", 500)
    : numEnv("HFT_BP_RESERVE_USD", 2000);

  if (cache) {
    const pool = sizeFromCash ? Math.max(0, cache.cash) : Math.max(0, cache.buyingPower);
    const deployable = Math.max(0, pool * bpFrac - reserve);
    if (!(deployable > 0)) return 0;
    const slot = deployable / slots;
    return Math.max(floor, Math.min(cap, slot));
  }
  // Before first account snapshot, use configured base (not hardcoded $1k default).
  return Math.max(floor, Math.min(cap, baseNotional));
}

/** Apply floor/cap AFTER confidence/news multipliers (resolveHftNotionalUsd clamps too early). */
export function clampHftNotionalUsd(notional: number): number {
  const floor = numEnv("HFT_MIN_ORDER_NOTIONAL", 200);
  const cap = numEnv("HFT_MAX_ORDER_NOTIONAL", numEnv("FORTRESS_GO_LIVE_MAX_NOTIONAL", 2_500));
  if (!(notional > 0) || !Number.isFinite(notional)) return floor;
  return Math.max(floor, Math.min(cap, notional));
}
