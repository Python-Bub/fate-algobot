/**
 * Dual-class / same-issuer listings. GOOG and GOOGL are one Alphabet bet.
 */
const ISSUER_CANON: Record<string, string> = {
  GOOG: "GOOGL",
  GOOGL: "GOOGL",
  "BRK-A": "BRK-B",
  "BRK.A": "BRK-B",
  BRKA: "BRK-B",
  "BRK-B": "BRK-B",
  "BRK.B": "BRK-B",
  BRKB: "BRK-B",
  FOX: "FOXA",
  FOXA: "FOXA",
  NWS: "NWSA",
  NWSA: "NWSA",
};

export function issuerGroup(symbol: string): string {
  const s = symbol.toUpperCase();
  return ISSUER_CANON[s] ?? s;
}

export function issuerSiblings(symbol: string): string[] {
  const g = issuerGroup(symbol);
  const out = new Set<string>([symbol.toUpperCase(), g]);
  for (const [k, v] of Object.entries(ISSUER_CANON)) {
    if (v === g) out.add(k);
  }
  return [...out];
}

export async function issuerLongQty(
  getQty: (sym: string) => Promise<number>,
  symbol: string,
): Promise<number> {
  let tot = 0;
  let anyFinite = false;
  for (const sib of issuerSiblings(symbol)) {
    const q = await getQty(sib);
    if (Number.isFinite(q)) {
      anyFinite = true;
      tot += Math.max(0, q);
    }
  }
  return anyFinite ? tot : Number.NaN;
}

/** Sync peek of issuer longs. NaN = cache not ready (fail closed). */
export function issuerCachedLongQty(
  getQty: (sym: string) => number,
  symbol: string,
): number {
  let tot = 0;
  let anyFinite = false;
  for (const sib of issuerSiblings(symbol)) {
    const q = getQty(sib);
    if (Number.isFinite(q)) {
      anyFinite = true;
      tot += Math.max(0, q);
    }
  }
  return anyFinite ? tot : Number.NaN;
}

/** Unknown book or existing long → do not add. maxQty<=0 means any long blocks. */
export function skipBuyAlreadyLong(live: number, maxQty = 0): boolean {
  if (!Number.isFinite(live)) return true;
  if (!(live > 1e-8)) return false;
  return maxQty <= 0 || live >= maxQty;
}
