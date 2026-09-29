/**
 * Same lesson as analytics/loss_memory.py: a name that just lost is a smaller clip.
 * A win clears it. The name stays tradable.
 */
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";

type Trade = { ret?: number; ts?: string; source?: string };

function memoryPath(): string {
  return process.env.LOSS_MEMORY_PATH?.trim() || join(fateRoot(), "data", "intel", "loss_memory.json");
}

/** Append one filled round-trip so the next fire on this name is smaller the same day. */
export function rememberRealized(symbol: string, realizedReturn: number, source = "hft"): void {
  const sym = symbol.trim().toUpperCase();
  if (!sym || !Number.isFinite(realizedReturn)) return;
  const path = memoryPath();
  try {
    let doc: { symbols?: Record<string, { trades?: Trade[] }> } = { symbols: {} };
    if (existsSync(path)) {
      doc = JSON.parse(readFileSync(path, "utf8")) as typeof doc;
    }
    if (!doc.symbols) doc.symbols = {};
    const rows = Array.isArray(doc.symbols[sym]?.trades) ? doc.symbols[sym]!.trades! : [];
    rows.push({ ret: realizedReturn, ts: new Date().toISOString(), source });
    doc.symbols[sym] = { trades: rows.slice(-12) };
    mkdirSync(dirname(path), { recursive: true });
    const tmp = `${path}.tmp`;
    writeFileSync(tmp, JSON.stringify(doc, null, 2));
    renameSync(tmp, path);
  } catch {
    /* best-effort; a missed lesson is smaller than a crashed flatten */
  }
}

function fateRoot(): string {
  return process.env.FATE_ROOT?.trim() || process.cwd().replace(/\/hft$/, "");
}

export function lossSizeMult(symbol: string): number {
  const sym = symbol.trim().toUpperCase();
  if (!sym) return 1;
  const path = memoryPath();
  if (!existsSync(path)) return 1;
  try {
    const doc = JSON.parse(readFileSync(path, "utf8")) as {
      symbols?: Record<string, { trades?: Trade[] }>;
    };
    const rows = doc.symbols?.[sym]?.trades ?? [];
    if (!rows.length) return 1;
    const lastRow = rows[rows.length - 1];
    const last = Number(lastRow?.ret ?? 0);
    if (!(last < 0)) return 1;
    const closedMs = Date.parse(String((lastRow as { ts?: string }).ts ?? ""));
    if (Number.isFinite(closedMs)) {
      const et = (ms: number) =>
        new Date(ms).toLocaleDateString("en-CA", { timeZone: "America/New_York" });
      if (et(closedMs) === et(Date.now())) return 0;
    }
    const recent = rows.slice(-5);
    const losses = recent.filter((r) => Number(r.ret ?? 0) < 0).length;
    return losses >= 2 ? 0.25 : 0.45;
  } catch {
    return 1;
  }
}
