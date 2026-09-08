/**
 * ============================================================================
 * PHASE 4 — STATE MANAGEMENT, POST-TRADE LOGGING, AND SAFETY
 * ============================================================================
 *
 *   • Logging runs via `process.nextTick(...)` in `fileLogger` so disk writes
 *     never sit on the wire-path stack.
 *   • Tracks ingest-to-fire ms, broker wire ms, and slippage (vs the trigger
 *     limit) using a rolling Float64 ring per ticker.
 *   • The KillSwitch already enforces "one earnings trade per ticker" via the
 *     `cooldownMs` lockout. We back-stop that with an explicit
 *     `lockTickerForever` for true single-shot earnings days.
 */
import { KillSwitch } from "../common/kill-switch.js";
import { fileLogger, stdoutTag } from "../common/logger.js";
import { CircularF64 } from "../common/buffers.js";

const log = stdoutTag("[POST]");

interface SlippageStats {
  ingestToFire: CircularF64;
  wire: CircularF64;
  slippageCents: CircularF64;
  fees: CircularF64;
}

export class PostTradeAccountant {
  private readonly perTicker = new Map<string, SlippageStats>();

  constructor(private readonly kill: KillSwitch, private readonly lockForever: boolean) {}

  private getOrAlloc(ticker: string): SlippageStats {
    let s = this.perTicker.get(ticker);
    if (!s) {
      s = {
        ingestToFire: new CircularF64(64),
        wire: new CircularF64(64),
        slippageCents: new CircularF64(64),
        fees: new CircularF64(64),
      };
      this.perTicker.set(ticker, s);
    }
    return s;
  }

  recordFill(args: {
    ticker: string;
    side: "buy" | "sell";
    limitPx: number;
    fillPx: number;
    qty: number;
    ingestToFireMs: number;
    wireMs: number;
    feeUsd?: number;
  }): void {
    const stats = this.getOrAlloc(args.ticker);
    stats.ingestToFire.push(args.ingestToFireMs);
    stats.wire.push(args.wireMs);
    // Slippage is *unfavourable* movement: buys want lower px, sells want higher px.
    const slipCents = args.side === "buy"
      ? (args.fillPx - args.limitPx) * 100
      : (args.limitPx - args.fillPx) * 100;
    stats.slippageCents.push(slipCents);
    stats.fees.push(args.feeUsd ?? 0);

    log("FILL", { ...args, slipCents });
    fileLogger.emit("earn_fill", { ...args, slipCents });

    if (this.lockForever) {
      // Lock for ~1 trading day; calling lock with cooldownMs already applied.
      this.kill.lock(args.ticker, Date.now() + 24 * 3600 * 1000);
    }
  }

  snapshot(ticker: string): Record<string, number> | null {
    const s = this.perTicker.get(ticker);
    if (!s) return null;
    return {
      avg_ingest_to_fire_ms: s.ingestToFire.mean(),
      avg_wire_ms: s.wire.mean(),
      avg_slippage_cents: s.slippageCents.mean(),
      avg_fees_usd: s.fees.mean(),
      n: s.ingestToFire.size(),
    };
  }
}
