/**
 * Pick the IEX websocket set from a liquid pool, excluding names we already
 * hold (fortress). Adding into those longs was a silent 200/min skip-all.
 */
export function pickWsTickers(
  pool: readonly string[],
  held: ReadonlySet<string>,
  maxN: number,
): string[] {
  const cap = Math.max(1, Math.floor(maxN));
  const seen = new Set<string>();
  const free: string[] = [];
  for (const raw of pool) {
    const t = String(raw || "").trim().toUpperCase();
    if (!t || seen.has(t)) continue;
    seen.add(t);
    if (held.has(t)) continue;
    free.push(t);
    if (free.length >= cap) break;
  }
  return free;
}
