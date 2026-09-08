/**
 * Desk-style risk: Avellaneda–Stoikov inventory haircut + latency decay.
 *
 * When quote age + wire RTT approaches the OFI half-life, expected edge is
 * already in the price — size → 0 (sit out). Never deploy the whole book.
 */
import { loadExecDelayMs } from "./exec-delay.js";

export function lagHaircut(
  quoteAgeMs: number,
  rttMs = loadExecDelayMs(),
  halfLifeMs = Number(process.env.HFT_LAG_HALFLIFE_MS ?? 250),
): number {
  const tau = Math.max(1, halfLifeMs);
  const lag = Math.max(0, quoteAgeMs) + Math.max(0, rttMs);
  return Math.exp(-Math.LN2 * (lag / tau));
}

/** 1 when HFT inventory is empty; 0 at maxInvFrac of equity (A–S reservation). */
export function inventoryHaircut(
  hftInventoryUsd: number,
  equityUsd: number,
  maxInvFrac = Number(process.env.HFT_MAX_HFT_INVENTORY_FRAC ?? 0.08),
): number {
  const cap = Math.max(1, equityUsd) * Math.max(0.01, Math.min(0.5, maxInvFrac));
  const used = Math.max(0, hftInventoryUsd);
  return Math.max(0, 1 - used / cap);
}

export function combinedHaircut(
  quoteAgeMs: number,
  hftInventoryUsd: number,
  equityUsd: number,
  rttMs = loadExecDelayMs(),
): { haircut: number; lag: number; inv: number; sitOut: boolean } {
  const lag = lagHaircut(quoteAgeMs, rttMs);
  const inv = inventoryHaircut(hftInventoryUsd, equityUsd);
  const haircut = lag * inv;
  const minH = Number(process.env.HFT_MIN_HAIRCUT ?? 0.12);
  return { haircut, lag, inv, sitOut: haircut < minH };
}

export function clipNotional(baseUsd: number, haircut: number): number {
  const floor = Number(process.env.HFT_MIN_ORDER_NOTIONAL ?? 80);
  const cap = Number(process.env.HFT_MAX_ORDER_NOTIONAL ?? 350);
  const x = Math.max(0, baseUsd) * Math.max(0, Math.min(1, haircut));
  // Never round a haircut-thin clip UP to the floor — that re-levered lag.
  if (!(x >= floor) || !Number.isFinite(x)) return 0;
  return Math.min(cap, x);
}

export function sizeHftClip(opts: {
  baseUsd: number;
  quoteAgeMs: number;
  hftInventoryUsd: number;
  equityUsd: number;
  rttMs?: number;
}): { notional: number; sitOut: boolean; haircut: number; lag: number; inv: number } {
  const { haircut, sitOut, lag, inv } = combinedHaircut(
    opts.quoteAgeMs,
    opts.hftInventoryUsd,
    opts.equityUsd,
    opts.rttMs,
  );
  if (sitOut) return { notional: 0, sitOut: true, haircut, lag, inv };
  const notional = clipNotional(opts.baseUsd, haircut);
  return { notional, sitOut: !(notional > 0), haircut, lag, inv };
}
