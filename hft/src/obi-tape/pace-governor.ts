/**
 * Rolling 60s submit budget. Target sits just under Alpaca's 200/min soft cap.
 * Underfill is logged — we never invent tape to pad the count.
 */
export function tpmTarget(): number {
  const n = Number(process.env.HFT_MAX_ORDERS_PER_MIN ?? 200);
  return Number.isFinite(n) && n > 0 ? n : 200;
}

export function rollingCount(nowMs: number, stamps: readonly number[], windowMs = 60_000): number {
  return stamps.filter((t) => nowMs - t < windowMs).length;
}

export function underTarget(nowMs: number, stamps: readonly number[], target = tpmTarget()): boolean {
  return rollingCount(nowMs, stamps) < target;
}

/** Names × 60/cooldown × 2 (buy+flatten) must clear 0.95 * target when dual-signal is dense. */
export function plumbingHitsTarget(
  nNames: number,
  cooldownMs: number,
  target = tpmTarget(),
  ordersPerRt = 2,
): boolean {
  const cd = Math.max(1, cooldownMs) / 1000;
  const orders = nNames * (60 / cd) * ordersPerRt;
  return orders >= target * 0.95;
}
