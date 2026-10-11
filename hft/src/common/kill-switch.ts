/**
 * Per-ticker lockdown + process + GLOBAL (cross-process) order rate budget.
 *
 * OBI and earnings each instantiate KillSwitch; both honor
 * HFT_GLOBAL_MAX_ORDERS_PER_MIN via a shared JSON counter under data/ops/
 * so coexist never exceeds the Alpaca-friendly global ceiling (default 200/min,
 * rolling 60s — fills that cross a clock minute still count as one submit).
 */
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";

function fateRoot(): string {
  return process.env.FATE_ROOT?.trim() || process.cwd().replace(/\/hft$/, "");
}

function budgetPath(): string {
  return join(fateRoot(), "data", "ops", "hft_order_budget.json");
}

/** Honor Python day_trade_risk halt — block new buys, allow exits/covers. */
let _dayHaltCache: { checkedAt: number; halted: boolean } = { checkedAt: 0, halted: false };

export function dayTradeBuysHalted(): boolean {
  if (process.env.HFT_RESPECT_DAY_HALT === "false") return false;
  const now = Date.now();
  if (now - _dayHaltCache.checkedAt < 2000) return _dayHaltCache.halted;
  _dayHaltCache.checkedAt = now;
  const today = new Date().toLocaleDateString("en-CA", { timeZone: "America/New_York" });
  let halted = false;
  try {
    const path = join(fateRoot(), "data", "intel", "day_trade_session.json");
    if (existsSync(path)) {
      const st = JSON.parse(readFileSync(path, "utf8")) as {
        date?: string;
        halted?: boolean;
      };
      halted = Boolean(st.halted) && st.date === today;
    }
  } catch {
    halted = false;
  }
  if (!halted) {
    try {
      const path = join(fateRoot(), "data", "ops", "hft_day_pnl.json");
      if (existsSync(path)) {
        const st = JSON.parse(readFileSync(path, "utf8")) as {
          date?: string;
          halted?: boolean;
        };
        halted = Boolean(st.halted) && st.date === today;
      }
    } catch {
      /* HFT day file optional */
    }
  }
  _dayHaltCache.halted = halted;
  return halted;
}

function tryReserveGlobal(nowMs: number): boolean {
  const globalMax = Number(process.env.HFT_GLOBAL_MAX_ORDERS_PER_MIN ?? 200);
  if (!(globalMax > 0)) return true;
  const path = budgetPath();
  try {
    mkdirSync(dirname(path), { recursive: true });
  } catch {
    /* ignore */
  }
  let submits: number[] = [];
  try {
    if (existsSync(path)) {
      const raw = JSON.parse(readFileSync(path, "utf8")) as {
        minute?: number;
        count?: number;
        submits?: number[];
      };
      if (Array.isArray(raw.submits)) submits = raw.submits;
    }
  } catch {
    submits = [];
  }
  // Rolling 60s — a fill that crosses a clock minute still counts as one submit.
  submits = submits.filter((t) => nowMs - t < 60_000);
  if (submits.length >= globalMax) return false;
  submits.push(nowMs);
  const tmp = `${path}.tmp.${process.pid}`;
  try {
    writeFileSync(tmp, JSON.stringify({ submits }));
    renameSync(tmp, path);
  } catch {
    // Best-effort — still allow local limit to gate.
  }
  return true;
}

export class KillSwitch {
  private readonly bits: Uint8Array;
  private readonly unlockAt: Float64Array;
  private readonly tickerToIdx = new Map<string, number>();
  private globalKill = false;
  private orderTs: number[] = [];

  constructor(
    tickers: readonly string[],
    public readonly cooldownMs: number,
    public readonly maxOrdersPerMin: number,
  ) {
    this.bits = new Uint8Array(Math.ceil(tickers.length / 8));
    this.unlockAt = new Float64Array(tickers.length);
    tickers.forEach((t, i) => this.tickerToIdx.set(t.toUpperCase(), i));
  }

  setGlobal(killed: boolean): void {
    this.globalKill = killed;
  }

  isLocked(ticker: string, nowMs: number): boolean {
    if (this.globalKill) return true;
    const idx = this.tickerToIdx.get(ticker.toUpperCase());
    if (idx === undefined) return true;
    const byte = idx >>> 3;
    const mask = 1 << (idx & 7);
    if ((this.bits[byte] & mask) !== 0) {
      if (nowMs >= this.unlockAt[idx]) {
        this.bits[byte] &= ~mask;
        return false;
      }
      return true;
    }
    return false;
  }

  lock(ticker: string, nowMs: number): void {
    const idx = this.tickerToIdx.get(ticker.toUpperCase());
    if (idx === undefined) return;
    const byte = idx >>> 3;
    const mask = 1 << (idx & 7);
    this.bits[byte] |= mask;
    this.unlockAt[idx] = nowMs + this.cooldownMs;
  }

  /** Returns true if you may submit an order (local + shared global budget). Rolling 60s. */
  reserveOrderSlot(nowMs: number): boolean {
    this.orderTs = this.orderTs.filter((t) => nowMs - t < 60_000);
    if (this.orderTs.length >= this.maxOrdersPerMin) return false;
    const maxPerSec = Number(process.env.HFT_MAX_ORDERS_PER_SEC ?? 8);
    if (maxPerSec > 0) {
      const inSec = this.orderTs.filter((t) => nowMs - t < 1000).length;
      if (inSec >= maxPerSec) return false;
      // Same-tick WS/REST bursts used to pass 8 POSTs in one ms and 429 Alpaca.
      const last = this.orderTs.length ? this.orderTs[this.orderTs.length - 1] : undefined;
      const minGap = Math.max(1, Math.floor(1000 / maxPerSec));
      if (last != null && nowMs - last < minGap) return false;
    }
    if (!tryReserveGlobal(nowMs)) return false;
    this.orderTs.push(nowMs);
    return true;
  }
}
