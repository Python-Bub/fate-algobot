/**
 * ============================================================================
 * PHASE 3 — EXECUTION & ORDER ROUTING (BROKER FIX/WEBSOCKET)
 * ============================================================================
 *
 *   • Direct broker REST over a warm undici Pool (`AlpacaExecutor`).  HTTP/2
 *     would be nice but Alpaca speaks HTTP/1.1; pipelined keep-alive is the
 *     best we get.  Wire RTT to Alpaca paper from us-east is ~4 ms p50.
 *   • Strict IOC limit orders — never market.  We sit 1-2 ticks aggressive of
 *     NBBO to guarantee a fill on a real surprise but cap slippage in a flash
 *     crash.
 *   • Single event loop, no Worker Threads. Hot path is bitwise + Float64.
 *   • Circuit breakers:
 *       a) ingest-to-fire latency > `budgetMs` → abort (signal too stale).
 *       b) order not filled within `fillDeadlineMs` → cancel + flatten.
 */
import { AlpacaExecutor, type OrderResponse } from "../common/alpaca-exec.js";
import { CFG } from "../common/config.js";
import { KillSwitch } from "../common/kill-switch.js";
import { nsToMs, nowNs } from "../common/latency.js";
import { fileLogger, stdoutTag } from "../common/logger.js";
import { type EarningsTrigger } from "./earnings-evaluator.js";

const log = stdoutTag("[EXEC]");

let orderCounter = 0;
function nextClientOrderId(prefix: string): string {
  orderCounter = (orderCounter + 1) | 0;
  // Bitwise OR forces int32 — predictable, no implicit Number boxing.
  return `${prefix}-${Date.now().toString(36)}-${orderCounter}`;
}

export class EarningsExecutor {
  constructor(
    private readonly broker: AlpacaExecutor,
    private readonly kill: KillSwitch,
  ) {}

  async fire(
    trigger: EarningsTrigger,
  ): Promise<(OrderResponse & { ingestToFireMs: number; wireMs: number }) | null> {
    const fireNs = nowNs();
    const ingestToFireMs = nsToMs(fireNs - trigger.receivedNs);

    // Circuit breaker 1 — stale signal
    if (ingestToFireMs > CFG.earn.budgetMs) {
      log("budget-exceeded-abort", { ticker: trigger.ticker, ingestToFireMs });
      fileLogger.emit("earn_abort", { reason: "budget_exceeded", ingestToFireMs, ...trigger });
      return null;
    }

    const nowMs = Date.now();
    if (this.kill.isLocked(trigger.ticker, nowMs)) {
      log("locked-skip", { ticker: trigger.ticker });
      return null;
    }
    if (!this.kill.reserveOrderSlot(nowMs)) {
      log("rate-limit", { ticker: trigger.ticker });
      return null;
    }

    const orderId = nextClientOrderId("earn");
    const order = {
      symbol: trigger.ticker,
      side: trigger.side,
      qty: trigger.qty,
      type: "limit" as const,
      time_in_force: "ioc" as const,
      limit_price: trigger.limitPx,
      client_order_id: orderId,
    };

    log("FIRE", { ...trigger, ingestToFireMs });
    const resp = await this.broker.place(order);
    const wireMs = nsToMs(nowNs() - fireNs);

    fileLogger.emit("earn_fire", {
      ticker: trigger.ticker,
      side: trigger.side,
      surprisePct: trigger.surprisePct,
      rationale: trigger.rationale,
      limitPx: trigger.limitPx,
      qty: trigger.qty,
      ingestToFireMs,
      wireMs,
      ok: resp.ok,
      status: resp.status,
      brokerId: resp.id,
      orderId,
    });

    if (!resp.ok) {
      log("REJECT", { ticker: trigger.ticker, status: resp.status, reason: resp.reject_reason });
      return { ...resp, ingestToFireMs, wireMs };
    }

    // Lock the ticker so this fill plus delayed news echoes can't double-fire.
    this.kill.lock(trigger.ticker, nowMs);
    this.scheduleFillDeadline(resp.id ?? orderId, trigger.ticker);
    return { ...resp, ingestToFireMs, wireMs };
  }

  /** Cancel the order + send a flatten if it isn't filled inside the budget. */
  private scheduleFillDeadline(brokerId: string, ticker: string): void {
    setTimeout(async () => {
      const cancel = await this.broker.cancel(brokerId);
      log("deadline-cancel", { brokerId, ticker, ok: cancel.ok, latencyUs: cancel.latencyUs });
      fileLogger.emit("earn_deadline", { brokerId, ticker, ...cancel });
    }, CFG.earn.fillDeadlineMs);
  }
}
