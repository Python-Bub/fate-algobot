/**
 * Rolling PnL circuit breaker — kills new entries after loss budget in window.
 * Blueprint: "lose $X in 60s → cancel all, global kill."
 * Also persists session realized P&L so OBI and MR share a day halt.
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { stdoutTag } from "./logger.js";

const log = stdoutTag("[CB]");

type Fill = { pnlUsd: number; tsMs: number };

function fateRoot(): string {
  return process.env.FATE_ROOT?.trim() || process.cwd().replace(/\/hft$/, "");
}

function dayPath(): string {
  return join(fateRoot(), "data", "ops", "hft_day_pnl.json");
}

function todayEt(): string {
  return new Date().toLocaleDateString("en-CA", { timeZone: "America/New_York" });
}

type DayFile = { date?: string; realized_usd?: number; halted?: boolean; reason?: string };

function readDay(): DayFile {
  try {
    if (!existsSync(dayPath())) return {};
    return JSON.parse(readFileSync(dayPath(), "utf8")) as DayFile;
  } catch {
    return {};
  }
}

function writeDay(doc: DayFile): void {
  try {
    mkdirSync(dirname(dayPath()), { recursive: true });
    writeFileSync(dayPath(), JSON.stringify(doc, null, 2));
  } catch {
    /* best-effort */
  }
}

export class CircuitBreaker {
  private readonly fills: Fill[] = [];
  private tripped = false;
  private readonly windowMs: number;
  private readonly maxLossUsd: number;
  private readonly dayLossUsd: number;

  constructor() {
    this.windowMs = Number(process.env.HFT_CB_WINDOW_MS ?? 60_000);
    this.maxLossUsd = Number(process.env.HFT_CB_MAX_LOSS_USD ?? 150);
    this.dayLossUsd = Number(process.env.HFT_CB_DAY_LOSS_USD ?? 250);
    if (process.env.HFT_CB_PERSIST !== "false") {
      const st = readDay();
      if (st.date === todayEt() && st.halted) this.tripped = true;
    }
  }

  enabled(): boolean {
    return process.env.HFT_CIRCUIT_BREAKER !== "false" && this.maxLossUsd > 0;
  }

  isTripped(): boolean {
    if (this.tripped) return true;
    if (process.env.HFT_CB_PERSIST === "false") return false;
    const st = readDay();
    return st.date === todayEt() && Boolean(st.halted);
  }

  recordRoundTripPnl(pnlUsd: number, nowMs = Date.now()): void {
    if (!this.enabled()) return;
    this.fills.push({ pnlUsd, tsMs: nowMs });
    this.prune(nowMs);
    const net = this.netPnl(nowMs);
    const today = todayEt();
    const st = readDay();
    const realized =
      st.date === today ? Number(st.realized_usd || 0) + pnlUsd : pnlUsd;
    let halted = st.date === today && Boolean(st.halted);
    let reason = st.reason || "";
    if (net <= -this.maxLossUsd) {
      this.tripped = true;
      halted = true;
      reason = `rolling ${this.windowMs}ms loss ${net.toFixed(2)}`;
      log("TRIP", { netUsd: net, windowMs: this.windowMs, maxLossUsd: this.maxLossUsd });
    }
    if (this.dayLossUsd > 0 && realized <= -this.dayLossUsd) {
      this.tripped = true;
      halted = true;
      reason = `day realized ${realized.toFixed(2)}`;
      log("TRIP-DAY", { realizedUsd: realized, dayLossUsd: this.dayLossUsd });
    }
    if (this.dayLossUsd > 0 && process.env.HFT_CB_PERSIST !== "false") {
      writeDay({ date: today, realized_usd: realized, halted, reason });
    }
  }

  netPnl(nowMs = Date.now()): number {
    this.prune(nowMs);
    let s = 0;
    for (const f of this.fills) s += f.pnlUsd;
    return s;
  }

  reset(): void {
    this.tripped = false;
    this.fills.length = 0;
  }

  private prune(nowMs: number): void {
    const cut = nowMs - this.windowMs;
    while (this.fills.length > 0 && this.fills[0].tsMs < cut) {
      this.fills.shift();
    }
  }
}
