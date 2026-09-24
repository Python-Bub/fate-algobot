/**
 * Expected-value gate for HFT entries.
 * p_up from OBI×tape logit fuse; EV = p*tp − (1−p)*stop − cost (bps).
 */
export function clipProb(p: number): number {
  if (!Number.isFinite(p)) return 0.5;
  return Math.min(1 - 1e-9, Math.max(1e-9, p));
}

export function logit(p: number): number {
  const x = clipProb(p);
  return Math.log(x / (1 - x));
}

export function sigmoid(z: number): number {
  const zz = Math.max(-40, Math.min(40, z));
  if (zz >= 0) {
    const e = Math.exp(-zz);
    return 1 / (1 + e);
  }
  const e = Math.exp(zz);
  return e / (1 + e);
}

/** Map OBI in [-1,1] and burst ratio onto (0,1) probabilities. */
export function fuseObiTape(obi: number, burstRatio: number, velocityMult: number): number {
  const obiP = clipProb(0.5 + 0.5 * Math.max(-1, Math.min(1, obi)));
  const burstP = clipProb(Math.min(1, burstRatio / Math.max(1e-6, 2 * velocityMult)));
  return sigmoid(0.58 * logit(obiP) + 0.42 * logit(burstP));
}

/** OFI path: OBI + micro-price drift. Tape is a veto, not a required fuse input. */
export function fuseObiMicro(obi: number, microDriftBps: number): number {
  const obiP = clipProb(0.5 + 0.5 * Math.max(-1, Math.min(1, obi)));
  const microP = clipProb(0.5 + 0.5 * Math.max(-1, Math.min(1, microDriftBps / 8)));
  return sigmoid(0.62 * logit(obiP) + 0.38 * logit(microP));
}

/**
 * Scalp target in bps. A fixed tick target (12 cents) is ~6 bps on a $200
 * name and loses to the real spread, so liquid books never fired.
 * HFT_TARGET_EDGE_BPS is price-independent. Ticks remain the fallback.
 */
export function targetEdgeBps(mid: number, tpTicks: number, tick = 0.01): number {
  const fromEnv = Number(process.env.HFT_TARGET_EDGE_BPS ?? 0);
  if (Number.isFinite(fromEnv) && fromEnv > 0) return fromEnv;
  if (!(mid > 0) || !(tpTicks > 0) || !(tick > 0)) return 0;
  return ((tpTicks * tick) / mid) * 10_000;
}

export function expectedBps(
  pUp: number,
  tpBps: number,
  costBps: number,
  stopBps?: number,
): number {
  const p = clipProb(pUp);
  const tp = Math.max(0, tpBps);
  if (stopBps == null) return p * tp - costBps;
  return p * tp - (1 - p) * Math.max(0, stopBps) - costBps;
}

export function shouldEnterEv(
  pUp: number,
  tpBps: number,
  costBps: number,
  minEvBps: number,
  minP = 0.52,
): { ok: boolean; evBps: number; p: number } {
  const p = clipProb(pUp);
  const evBps = expectedBps(p, tpBps, costBps);
  return { ok: p >= minP && evBps >= minEvBps, evBps, p };
}
