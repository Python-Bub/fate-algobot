/**
 * Entry regime. Default `ofi` is Cont/de Larrard / OFI: quote-revision
 * imbalance is the signal; tape is a VPIN toxicity veto, not a required AND.
 * `dual` keeps the old OBI∧tape burst. `or` is the spray (keep off).
 */
export type HftSignalMode = "ofi" | "dual" | "or";

export function resolveSignalMode(): HftSignalMode {
  if (process.env.HFT_OR_SIGNAL === "true") return "or";
  const raw = (process.env.HFT_SIGNAL_MODE ?? "ofi").trim().toLowerCase();
  if (raw === "dual" || raw === "and") return "dual";
  if (raw === "or") return "or";
  return "ofi";
}

export function wantsDirection(
  mode: HftSignalMode,
  longOnly: boolean,
  bits: { obiLong: boolean; obiShort: boolean; tapeBurst: boolean },
  ofi: { microOk: boolean; sellToxic: boolean },
): { long: boolean; short: boolean } {
  let long = false;
  let short = false;
  if (mode === "ofi") {
    long = bits.obiLong && ofi.microOk && !ofi.sellToxic;
    short = !longOnly && bits.obiShort;
  } else if (mode === "or") {
    long = bits.obiLong || bits.tapeBurst;
    short = !longOnly && (bits.obiShort || bits.tapeBurst);
  } else {
    long = bits.obiLong && bits.tapeBurst;
    short = !longOnly && bits.obiShort && bits.tapeBurst;
  }
  return { long, short };
}

export function signalConfidence(
  mode: HftSignalMode,
  obiStrength: number,
  burstStrength: number,
  microStrength: number,
  strictDual: boolean,
): number {
  if (mode === "ofi") {
    return Math.max(obiStrength, 0.62 * obiStrength + 0.38 * microStrength);
  }
  if (mode === "or") {
    return Math.max(
      obiStrength,
      burstStrength,
      0.55 * obiStrength + 0.45 * burstStrength,
    );
  }
  if (strictDual) {
    return Math.min(obiStrength, burstStrength) * 0.7 + 0.3 * (0.5 * obiStrength + 0.5 * burstStrength);
  }
  return 0.5 * obiStrength + 0.5 * burstStrength;
}
