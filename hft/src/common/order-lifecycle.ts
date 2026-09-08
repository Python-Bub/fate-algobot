/**
 * Order fill polling. DAY/GTC stays on the book across minute boundaries
 * unless cancelIfUnfilled is explicitly true (IOC / hard-stop only).
 */
import { type AlpacaExecutor, type OrderResponse } from "./alpaca-exec.js";
import { mayCancelUnfilled } from "./market-session.js";

export const TERMINAL_ORDER_STATUSES = new Set([
  "filled",
  "canceled",
  "cancelled",
  "expired",
  "rejected",
  "done_for_day",
  "stopped",
  "suspended",
]);

export const OPEN_ORDER_STATUSES = new Set([
  "new",
  "accepted",
  "pending_new",
  "partially_filled",
  "pending_cancel",
  "pending_replace",
  "accepted_for_bidding",
  "calculated",
]);

export interface ResolvedFill {
  filled: boolean;
  filledQty: number;
  filledAvgPrice?: number;
  status: string;
  canceled: boolean;
  /** Still on the book — fill may land in a later minute. */
  working: boolean;
}

export type FillDecision =
  | { kind: "poll" }
  | {
      kind: "done";
      filled: boolean;
      filledQty: number;
      canceled: boolean;
      working: boolean;
      status: string;
    };

/**
 * Map one broker snapshot to fill / miss / keep-polling.
 * Never treat status=filled with filledQty=0 as a fill of the requested size —
 * that opened a local long and sold fortress shares after the buy cancelled.
 */
export function interpretFillSnapshot(
  snap: { status: string; filledQty: number },
  reqQty: number,
): FillDecision {
  const st = (snap.status || "").toLowerCase();
  const fq = filledShareQty(snap.filledQty);
  if (fq > 1e-8 && (fq >= reqQty || st === "filled")) {
    return { kind: "done", filled: true, filledQty: fq, canceled: false, working: false, status: st };
  }
  // Alpaca sometimes marks filled before filled_qty lands. Poll; do not invent size.
  if (st === "filled" && fq <= 1e-8) {
    return { kind: "poll" };
  }
  if (TERMINAL_ORDER_STATUSES.has(st) && fq <= 1e-8) {
    return {
      kind: "done",
      filled: false,
      filledQty: 0,
      canceled: st === "canceled" || st === "cancelled" || st === "expired" || st === "rejected",
      working: false,
      status: st,
    };
  }
  if (fq > 1e-8 && TERMINAL_ORDER_STATUSES.has(st)) {
    return { kind: "done", filled: true, filledQty: fq, canceled: false, working: false, status: st };
  }
  return { kind: "poll" };
}

export function orderFilledQty(resp: { orderStatus?: string; status?: string; filledQty?: number; qty?: number }): number {
  const fq = Number(resp.filledQty);
  if (Number.isFinite(fq) && fq > 1e-8) return fq;
  // Never invent requested qty from a "filled" status with no filled_qty —
  // that opened a local long and sold fortress shares after the buy cancelled.
  return 0;
}

/** Confirmed fill size. Do not round a miss up to 1 share. */
export function filledShareQty(filledQty: number): number {
  const q = Number(filledQty);
  if (!Number.isFinite(q) || q <= 1e-8) return 0;
  return q;
}

export function isHftEntryClientId(id: string): boolean {
  return /^(obi-|mr-|earn-)/i.test(id || "");
}

export function isHftExitClientId(id: string): boolean {
  return /^(flat-|close-)/i.test(id || "");
}

export interface OrderSnapshot {
  id: string;
  status: string;
  filledQty: number;
  qty: number;
  filledAvgPrice?: number;
  side: string;
  symbol: string;
}

export function snapshotFromPlace(resp: OrderResponse, reqQty: number): OrderSnapshot {
  const st = (resp.orderStatus ?? "").toLowerCase();
  const filledQty = orderFilledQty({ ...resp, qty: reqQty, status: st });
  return {
    id: resp.id ?? "",
    status: st,
    filledQty,
    qty: reqQty,
    filledAvgPrice: resp.filledAvgPrice,
    side: "",
    symbol: "",
  };
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

/** Poll until filled or terminal. Unfilled DAY/GTC stay on the book across minutes unless cancelIfUnfilled. */
export async function resolveOrderFill(
  broker: AlpacaExecutor,
  orderId: string,
  reqQty: number,
  opts?: { timeoutMs?: number; pollMs?: number; cancelIfUnfilled?: boolean },
): Promise<ResolvedFill> {
  const timeoutMs = opts?.timeoutMs ?? Number(process.env.HFT_ORDER_FILL_MS ?? 2500);
  const statusPollMs = opts?.pollMs ?? Number(process.env.HFT_ORDER_STATUS_POLL_MS ?? 150);
  const deadlineMs = Date.now() + timeoutMs;

  let last: OrderSnapshot | null = null;
  for (;;) {
    if (Date.now() >= deadlineMs) break;
    const snap = await broker.getOrder(orderId);
    if (snap) {
      last = snap;
      const decision = interpretFillSnapshot(snap, reqQty);
      if (decision.kind === "done") {
        return {
          filled: decision.filled,
          filledQty: decision.filledQty,
          filledAvgPrice: snap.filledAvgPrice,
          status: decision.status,
          canceled: decision.canceled,
          working: decision.working,
        };
      }
    }
    await sleep(statusPollMs);
  }

  let canceled = false;
  // Default: leave DAY/GTC working so fills can cross minute boundaries.
  // Fill-persist refuses cancel even if the caller passed cancelIfUnfilled.
  const cancelIfUnfilled = mayCancelUnfilled(opts?.cancelIfUnfilled === true);
  if (cancelIfUnfilled && last && OPEN_ORDER_STATUSES.has(last.status)) {
    const c = await broker.cancel(orderId);
    canceled = c.ok;
    await sleep(100);
    const after = await broker.getOrder(orderId);
    if (after && after.filledQty > 0) {
      return {
        filled: true,
        filledQty: after.filledQty,
        filledAvgPrice: after.filledAvgPrice,
        status: after.status,
        canceled: true,
        working: false,
      };
    }
  }

  const stillOpen = Boolean(last && OPEN_ORDER_STATUSES.has(last.status));
  return {
    filled: false,
    filledQty: last?.filledQty ?? 0,
    filledAvgPrice: last?.filledAvgPrice,
    status: last?.status ?? "timeout",
    canceled,
    working: stillOpen && !canceled,
  };
}

/** Drop local pending only when the ticket is gone — never while DAY/GTC is working. */
export function shouldReleasePending(resolved: Pick<ResolvedFill, "working">): boolean {
  return !resolved.working;
}

/** Shares actually filled on the entry ticket. 0 if cancelled / missing / adopted. */
export async function entryFilledQty(
  broker: AlpacaExecutor,
  orderId: string | undefined,
): Promise<number> {
  if (!orderId || orderId === "adopted") return 0;
  const snap = await broker.getOrder(orderId);
  if (!snap) return 0;
  return filledShareQty(snap.filledQty);
}

/** True if symbol already has a working order on the book (avoid duplicate FIRE → cancel loops). */
export async function hasOpenOrder(
  broker: AlpacaExecutor,
  symbol: string,
  side?: "buy" | "sell",
): Promise<boolean> {
  const open = await broker.listOpenOrders(symbol);
  for (const o of open) {
    if (!OPEN_ORDER_STATUSES.has(o.status) && o.status !== "") continue;
    if (side && (o.side ?? "").toLowerCase() !== side) continue;
    return true;
  }
  return false;
}

/** Cancel open orders for symbol older than maxAgeMs (orphan/stale protection). */
export async function cancelStaleOpenOrders(
  broker: AlpacaExecutor,
  symbol: string,
  maxAgeMs: number,
): Promise<number> {
  if (maxAgeMs <= 0) return 0;
  const open = await broker.listOpenOrders(symbol);
  const cutoff = Date.now() - maxAgeMs;
  let n = 0;
  for (const o of open) {
    if (o.createdMs > 0 && o.createdMs >= cutoff) continue;
    if (!OPEN_ORDER_STATUSES.has(o.status) && o.status !== "") continue;
    // Never cancel working sells (exits / hygiene / orphan flatten).
    if ((o.side ?? "").toLowerCase() === "sell") continue;
    const c = await broker.cancel(o.id);
    if (c.ok) n++;
  }
  return n;
}
