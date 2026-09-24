/**
 * Same lesson as analytics/loss_memory.py: a name that just lost is a smaller clip.
 * A win clears it. The name stays tradable.
 */
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

type Trade = { ret?: number };

function fateRoot(): string {
  return process.env.FATE_ROOT?.trim() || process.cwd().replace(/\/hft$/, "");
}

export function lossSizeMult(symbol: string): number {
  const sym = symbol.trim().toUpperCase();
  if (!sym) return 1;
  const path = process.env.LOSS_MEMORY_PATH?.trim() || join(fateRoot(), "data", "intel", "loss_memory.json");
  if (!existsSync(path)) return 1;
  try {
    const doc = JSON.parse(readFileSync(path, "utf8")) as {
      symbols?: Record<string, { trades?: Trade[] }>;
    };
    const rows = doc.symbols?.[sym]?.trades ?? [];
    if (!rows.length) return 1;
    const last = Number(rows[rows.length - 1]?.ret ?? 0);
    if (!(last < 0)) return 1;
    const recent = rows.slice(-5);
    const losses = recent.filter((r) => Number(r.ret ?? 0) < 0).length;
    return losses >= 2 ? 0.25 : 0.45;
  } catch {
    return 1;
  }
}
