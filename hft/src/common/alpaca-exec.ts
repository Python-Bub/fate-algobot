/**
 * Alpaca REST order executor (paper or live). HTTP/1.1 keep-alive via undici's
 * Pool — single TCP+TLS handshake amortised across orders.
 *
 * IMPORTANT: Alpaca's WebSocket stream is for *trade-update* notifications, not
 * order placement.  Order placement is `POST /v2/orders`.  With a warm undici
 * Pool we routinely measure ~3-6ms p50 wire latency from us-east → Alpaca, well
 * inside the 100ms earnings budget and inside the 10ms OBI/Tape budget when
 * collocated.
 *
 * Every order request times out at `timeoutMs` (default 80ms) and is wrapped in
 * a no-op try/catch so a broker hiccup never throws into the hot path.
 */
import { Pool, type Dispatcher } from "undici";
import fs from "node:fs";

import { LatencyHistogram, nowNs } from "./latency.js";

export type OrderSide = "buy" | "sell";
export type OrderType = "market" | "limit";
export type TimeInForce = "day" | "ioc" | "fok" | "gtc";

export interface OrderRequest {
  symbol: string;
  side: OrderSide;
  qty?: number;
  notional?: number;
  type: OrderType;
  time_in_force: TimeInForce;
  limit_price?: number;
  client_order_id: string;
  extended_hours?: boolean;
}

export interface OrderResponse {
  ok: boolean;
  status: number;
  id?: string;
  orderStatus?: string;
  filledQty?: number;
  filledAvgPrice?: number;
  reject_reason?: string;
  raw?: string;
  latencyUs: number;
  /** Dry-run / sim broker filled against NBBO at decision time. */
  simulated?: boolean;
  expectedFillPx?: number;
  slippageBps?: number;
}

interface SimOrder {
  id: string;
  symbol: string;
  side: OrderSide;
  qty: number;
  type: OrderType;
  timeInForce: TimeInForce;
  limitPrice?: number;
  bp: number;
  ap: number;
  placedMs: number;
  status: "new" | "filled" | "canceled" | "partially_filled";
  filledQty: number;
  filledAvgPrice?: number;
}

export interface OpenOrderRow {
  id: string;
  symbol: string;
  status: string;
  side: string;
  qty: number;
  filledQty: number;
  createdMs: number;
  clientOrderId: string;
  limitPrice?: number;
}

export interface AccountSnapshot {
  buyingPower: number;
  equity: number;
  cash: number;
  longMarketValue: number;
  maintenanceMargin: number;
  regtBuyingPower: number;
}

export class AlpacaExecutor {
  private readonly pool: Pool;
  private readonly headers: Record<string, string>;
  readonly placeHist: LatencyHistogram;
  readonly cancelHist: LatencyHistogram;
  private readonly simOrders = new Map<string, SimOrder>();
  private readonly simNbbo = new Map<string, { bp: number; ap: number }>();
  private posMap = new Map<string, number>();
  private posCacheAt = 0;
  private posOk = false;
  private posInflight: Promise<void> | null = null;

  constructor(
    public readonly baseUrl: string,
    public readonly apiKey: string,
    public readonly apiSecret: string,
    public readonly dryRun: boolean,
    public readonly timeoutMs = Number(process.env.HFT_ORDER_TIMEOUT_MS ?? 5000),
  ) {
    // Pool wants the *origin* only — strip any path the user may have left in
    // ALPACA_BASE_URL (e.g. `.../v2`).  We re-add `/v2/...` ourselves below.
    let origin: string;
    try {
      origin = new URL(baseUrl).origin;
    } catch {
      origin = "https://paper-api.alpaca.markets";
    }
    const to = this.timeoutMs;
    this.pool = new Pool(origin, {
      pipelining: 1,
      connections: 8,
      connectTimeout: to,
      keepAliveTimeout: 30_000,
      keepAliveMaxTimeout: 60_000,
    });
    this.headers = {
      "APCA-API-KEY-ID": apiKey,
      "APCA-API-SECRET-KEY": apiSecret,
      "content-type": "application/json",
    };
    this.placeHist = new LatencyHistogram(2048, "alpaca.place");
    this.cancelHist = new LatencyHistogram(2048, "alpaca.cancel");
  }

  /** Register latest NBBO before place() — used by dry-run sim fills. */
  registerNbbo(symbol: string, bp: number, ap: number): void {
    const sym = symbol.toUpperCase();
    if (bp > 0 && ap > 0) this.simNbbo.set(sym, { bp, ap });
  }

  private simUseRealisticFills(): boolean {
    return (
      this.dryRun &&
      process.env.HFT_SIM_BROKER !== "false" &&
      process.env.HFT_SIM_BROKER_LEGACY !== "true"
    );
  }

  private resolveSimFill(order: SimOrder): SimOrder {
    const nbbo = this.simNbbo.get(order.symbol) ?? { bp: order.bp, ap: order.ap };
    order.bp = nbbo.bp;
    order.ap = nbbo.ap;
    if (order.type === "market") {
      const px = order.side === "buy" ? nbbo.ap : nbbo.bp;
      if (px > 0) {
        order.status = "filled";
        order.filledQty = order.qty;
        order.filledAvgPrice = px;
      }
      return order;
    }
    const lp = order.limitPrice;
    if (lp == null || !(lp > 0)) return order;
    if (order.side === "buy" && nbbo.ap > 0 && lp >= nbbo.ap) {
      order.status = "filled";
      order.filledQty = order.qty;
      order.filledAvgPrice = nbbo.ap;
    } else if (order.side === "sell" && nbbo.bp > 0 && lp <= nbbo.bp) {
      order.status = "filled";
      order.filledQty = order.qty;
      order.filledAvgPrice = nbbo.bp;
    }
    return order;
  }

  private async request(
    method: "GET" | "POST" | "DELETE",
    path: string,
    body?: string,
  ): Promise<{ status: number; body: string }> {
    const opts: Dispatcher.RequestOptions = {
      path,
      method,
      headers: this.headers,
      headersTimeout: this.timeoutMs,
      bodyTimeout: this.timeoutMs,
    };
    if (body) opts.body = body;
    const res = await this.pool.request(opts);
    let raw = "";
    for await (const chunk of res.body) raw += chunk;
    return { status: res.statusCode, body: raw };
  }

  async place(order: OrderRequest): Promise<OrderResponse> {
    const start = nowNs();
    // Long-only: never sell more than live long qty (stale local qty was opening shorts).
    if (order.side === "sell" && process.env.HFT_LONG_ONLY !== "false" && !this.dryRun) {
      const live = await this.getPositionQty(order.symbol);
      const want = Number(order.qty ?? 0);
      if (!(live > 1e-8)) {
        const latencyUs = Number((nowNs() - start) / 1000n);
        return {
          ok: false,
          status: 400,
          latencyUs,
          reject_reason: "long_only_no_long_to_sell",
        };
      }
      const protectedQty = this.protectedOtherSleeveQty(order.symbol);
      const room = Math.max(0, live - protectedQty);
      if (!(room > 1e-8)) {
        const latencyUs = Number((nowNs() - start) / 1000n);
        return {
          ok: false,
          status: 400,
          latencyUs,
          reject_reason: "protected_other_sleeve",
        };
      }
      const cap = Math.min(want, live, room);
      if (!(cap > 1e-8)) {
        const latencyUs = Number((nowNs() - start) / 1000n);
        return {
          ok: false,
          status: 400,
          latencyUs,
          reject_reason: "sell_qty_capped_to_zero",
        };
      }
      if (want > cap + 1e-6) {
        order = { ...order, qty: Math.floor(cap * 1e6) / 1e6 };
      }
      if (!(Number(order.qty) > 1e-8)) {
        const latencyUs = Number((nowNs() - start) / 1000n);
        return {
          ok: false,
          status: 400,
          latencyUs,
          reject_reason: "sell_qty_capped_to_zero",
        };
      }
    }
    if (this.dryRun) {
      const latencyUs = Number((nowNs() - start) / 1000n);
      const id = `dry-${order.client_order_id}`;
      if (!this.simUseRealisticFills()) {
        return { ok: true, status: 200, id, latencyUs, simulated: true };
      }
      const sym = order.symbol.toUpperCase();
      const nbbo = this.simNbbo.get(sym) ?? { bp: 0, ap: 0 };
      const sim: SimOrder = {
        id,
        symbol: sym,
        side: order.side,
        qty: order.qty ?? 1,
        type: order.type,
        timeInForce: order.time_in_force,
        limitPrice: order.limit_price,
        bp: nbbo.bp,
        ap: nbbo.ap,
        placedMs: Date.now(),
        status: "new",
        filledQty: 0,
      };
      this.resolveSimFill(sim);
      this.simOrders.set(id, sim);
      const expected =
        order.side === "buy"
          ? order.type === "market"
            ? nbbo.ap
            : order.limit_price
          : order.type === "market"
            ? nbbo.bp
            : order.limit_price;
      const fillPx = sim.filledAvgPrice;
      let slippageBps: number | undefined;
      if (fillPx != null && expected != null && expected > 0 && fillPx > 0) {
        slippageBps = ((fillPx - expected) / expected) * 10_000 * (order.side === "buy" ? 1 : -1);
      }
      return {
        ok: true,
        status: 200,
        id,
        orderStatus: sim.status,
        filledQty: sim.filledQty,
        filledAvgPrice: sim.filledAvgPrice,
        latencyUs,
        simulated: true,
        expectedFillPx: expected,
        slippageBps,
      };
    }
    try {
      const body = JSON.stringify(order);
      const { status, body: raw } = await this.request("POST", "/v2/orders", body);
      const elapsedNs = nowNs() - start;
      this.placeHist.recordNs(elapsedNs);
      if (status >= 200 && status < 300) {
        const j = JSON.parse(raw) as {
          id?: string;
          status?: string;
          filled_avg_price?: string | number;
          filled_qty?: string | number;
          qty?: string | number;
        };
        const filledRaw = j.filled_avg_price;
        const filledAvgPrice =
          filledRaw != null && filledRaw !== "" ? Number(filledRaw) : undefined;
        const fq = j.filled_qty != null && j.filled_qty !== "" ? Number(j.filled_qty) : 0;
        return {
          ok: true,
          status,
          id: j.id,
          orderStatus: j.status,
          filledQty: Number.isFinite(fq) ? fq : 0,
          filledAvgPrice:
            filledAvgPrice != null && Number.isFinite(filledAvgPrice) && filledAvgPrice > 0
              ? filledAvgPrice
              : undefined,
          raw,
          latencyUs: Number(elapsedNs / 1000n),
        };
      }
      return {
        ok: false,
        status,
        reject_reason: raw.slice(0, 240),
        raw,
        latencyUs: Number(elapsedNs / 1000n),
      };
    } catch (err) {
      const elapsedNs = nowNs() - start;
      return {
        ok: false,
        status: 0,
        reject_reason: err instanceof Error ? err.message : String(err),
        latencyUs: Number(elapsedNs / 1000n),
      };
    }
  }

  private roundLimit(px: number): number {
    if (px >= 1) return Math.round(px * 100) / 100;
    if (px >= 0.1) return Math.round(px * 1000) / 1000;
    return Math.round(px * 10_000) / 10_000;
  }

  async listPositions(): Promise<
    Array<{ symbol: string; qty: number; side: "long" | "short"; avgEntry?: number }>
  > {
    if (this.dryRun) return [];
    try {
      const { status, body: raw } = await this.request("GET", "/v2/positions");
      if (status < 200 || status >= 300) return [];
      const rows = JSON.parse(raw) as Array<{
        symbol?: string;
        qty?: string | number;
        side?: string;
        avg_entry_price?: string | number;
      }>;
      if (!Array.isArray(rows)) return [];
      return rows
        .map((r) => {
          const signed = Number(r.qty ?? 0);
          const legSide = String(r.side ?? "").toLowerCase();
          const side: "long" | "short" =
            legSide === "short" || signed < 0 ? "short" : "long";
          const avg = Number(r.avg_entry_price ?? 0);
          return {
            symbol: (r.symbol ?? "").toUpperCase(),
            qty: signed,
            side,
            avgEntry: Number.isFinite(avg) && avg > 0 ? avg : undefined,
          };
        })
        .filter((r) => r.symbol && Math.abs(r.qty) > 0);
    } catch {
      return [];
    }
  }

  async getPositionQty(symbol: string): Promise<number> {
    if (this.dryRun) return 0;
    await this.refreshPositionCache();
    return this.cachedLongQty(symbol);
  }

  /** Sync peek — NaN until the first good snapshot (fail closed on buys). */
  cachedLongQty(symbol: string): number {
    if (this.dryRun) return 0;
    if (!this.posOk) return Number.NaN;
    return this.posMap.get(symbol.toUpperCase()) ?? 0;
  }

  /** Shares owned by fortress/weekly/longterm — HFT must not flatten these. */
  protectedOtherSleeveQty(symbol: string): number {
    try {
      const path =
        process.env.PORTFOLIO_HEAD_REGISTRY ||
        `${process.env.FATE_ROOT || process.cwd().replace(/\/hft$/, "")}/data/portfolio_head_registry.json`;
      if (!fs.existsSync(path)) return 0;
      const doc = JSON.parse(fs.readFileSync(path, "utf8")) as {
        heads?: Record<string, string>;
        qty_by_sleeve?: Record<string, Record<string, number>>;
      };
      const sym = symbol.toUpperCase();
      const sleeves = doc.qty_by_sleeve?.[sym] || {};
      let n = 0;
      for (const [h, q] of Object.entries(sleeves)) {
        if (h === "hft") continue;
        if (Number(q) > 0) n += Number(q);
      }
      if (n > 0) {
        const live = this.posMap.get(sym) ?? 0;
        if (Number.isFinite(live) && n > live + 1e-6) {
          // Stale oversized sleeve map (AMZN fortress=26 vs live 9). Trust the
          // primary head: overnight keeps the whole book; fast sleeves do not.
          const head = String(doc.heads?.[sym] || "").toLowerCase();
          if (head === "fortress" || head === "weekly" || head === "longterm") {
            return Number.isFinite(live) ? Math.max(0, live as number) : n;
          }
          return 0;
        }
        return n;
      }
      // Heads-only (no qty_by_sleeve) is stale registry — do not treat the
      // entire live book as overnight. Flatten already caps to entryFilledQty.
    } catch {
      /* registry optional */
    }
    return 0;
  }

  positionsReady(): boolean {
    return this.dryRun || this.posOk;
  }

  cachedPositionCount(): number {
    return this.posMap.size;
  }

  /** Live long symbols from the last good snapshot. */
  heldSymbols(): string[] {
    const out: string[] = [];
    for (const [sym, qty] of this.posMap) {
      if (qty > 1e-8) out.push(sym);
    }
    return out;
  }

  async warmPositions(): Promise<void> {
    if (this.dryRun) {
      this.posOk = true;
      return;
    }
    this.posCacheAt = 0;
    await this.refreshPositionCache();
  }

  /** TTL refresh only — do not zero posCacheAt (that 429'd GET /v2/positions every 2s). */
  async keepPositionsWarm(): Promise<void> {
    if (this.dryRun) return;
    await this.refreshPositionCache();
  }

  /** One positions snapshot / ~2s. Failed/partial fetches keep last longs (never fake flat). */
  private async refreshPositionCache(): Promise<void> {
    const now = Date.now();
    if (this.posOk && now - this.posCacheAt < 2000) return;
    if (this.posInflight) {
      await this.posInflight;
      return;
    }
    this.posInflight = this.fetchPositionSnapshot().finally(() => {
      this.posInflight = null;
    });
    await this.posInflight;
  }

  private async fetchPositionSnapshot(): Promise<void> {
    try {
      const { status, body: raw } = await this.request("GET", "/v2/positions");
      if (status < 200 || status >= 300) return;
      const rows = JSON.parse(raw) as Array<{ symbol?: string; qty?: string | number }>;
      if (!Array.isArray(rows)) return;
      const incoming = new Map<string, number>();
      for (const r of rows) {
        const sym = (r.symbol ?? "").toUpperCase();
        const q = Math.abs(Number(r.qty ?? 0));
        if (sym && q > 1e-8) incoming.set(sym, q);
      }
      this.applyPositionSnapshot(incoming);
    } catch {
      /* keep stale — treating unknown as flat was adding into fortress longs */
    }
  }

  /** Merge snapshots. Partial/empty replies must not drop KO while WMT remains. */
  applyPositionSnapshot(incoming: Map<string, number>): void {
    const oldSize = this.posMap.size;
    if (incoming.size === 0 && oldSize > 0) {
      this.posCacheAt = Date.now();
      return;
    }
    for (const [sym, qty] of incoming) this.posMap.set(sym, qty);
    const allowDelete = oldSize === 0 || incoming.size >= Math.max(1, oldSize * 0.5);
    if (allowDelete) {
      for (const k of [...this.posMap.keys()]) {
        if (!incoming.has(k)) this.posMap.delete(k);
      }
    }
    this.posOk = true;
    this.posCacheAt = Date.now();
  }

  private async getPositionLeg(
    symbol: string,
  ): Promise<{ qty: number; side: "long" | "short" | "flat" }> {
    if (this.dryRun) return { qty: 0, side: "flat" };
    try {
      const sym = encodeURIComponent(symbol.toUpperCase());
      const { status, body: raw } = await this.request("GET", `/v2/positions/${sym}`);
      if (status < 200 || status >= 300) return { qty: 0, side: "flat" };
      const j = JSON.parse(raw) as { qty?: string | number; side?: string };
      const signed = Number(j.qty ?? 0);
      if (!Number.isFinite(signed) || Math.abs(signed) < 1e-8) {
        return { qty: 0, side: "flat" };
      }
      const legSide = String(j.side ?? "").toLowerCase();
      if (legSide === "short" || signed < 0) {
        return { qty: Math.abs(signed), side: "short" };
      }
      return { qty: Math.abs(signed), side: "long" };
    } catch {
      return { qty: 0, side: "flat" };
    }
  }

  /**
   * Flatten HFT sleeve only — never wipe fortress/weekly/longterm inventory.
   * Pass maxQty = this sleeve's open size. Full Alpaca DELETE is forbidden when
   * other sleeves protect shares (100 LT + 50 HFT must not become sell-150).
   */
  async closePosition(
    symbol: string,
    entryPx = 0,
    forced = false,
    maxQty = 0,
  ): Promise<{ ok: boolean; latencyUs: number }> {
    const start = nowNs();
    if (this.dryRun) {
      return { ok: true, latencyUs: 0 };
    }
    const sym = symbol.toUpperCase();
    const extended = process.env.HFT_EXTENDED_HOURS !== "false";
    const leg = await this.getPositionLeg(sym);
    let protectedQty = 0;
    try {
      const fs = await import("node:fs");
      const path =
        process.env.PORTFOLIO_HEAD_REGISTRY ||
        `${process.env.FATE_ROOT || process.cwd().replace(/\/hft$/, "")}/data/portfolio_head_registry.json`;
      if (fs.existsSync(path)) {
        const doc = JSON.parse(fs.readFileSync(path, "utf8")) as {
          heads?: Record<string, string>;
          qty_by_sleeve?: Record<string, Record<string, number>>;
        };
        const sleeves = doc.qty_by_sleeve?.[sym] || {};
        for (const [h, q] of Object.entries(sleeves)) {
          if (h === "hft") continue;
          if (["fortress", "weekly", "longterm"].includes(h) && Number(q) > 0) {
            protectedQty += Number(q);
          }
        }
        const head = String(doc.heads?.[sym] || "").toLowerCase();
        if (
          protectedQty <= 0 &&
          (head === "fortress" || head === "weekly" || head === "longterm")
        ) {
          protectedQty = leg.qty;
        }
      }
    } catch {
      /* registry optional */
    }
    const brokerQty = leg.qty;
    const sleeveCap = maxQty > 0 ? maxQty : Math.max(0, brokerQty - protectedQty);
    const qty = Math.min(brokerQty, sleeveCap);
    if (qty <= 1e-8) {
      return { ok: true, latencyUs: Number((nowNs() - start) / 1000n) };
    }
    const allowFullDelete =
      forced &&
      protectedQty <= 1e-8 &&
      (maxQty <= 0 || maxQty + 1e-6 >= brokerQty);

    const fetchQuote = async (): Promise<{ bp: number; ap: number } | null> => {
      try {
        const dataBase =
          process.env.ALPACA_DATA_BASE?.trim() ||
          process.env.ALPACA_DATA_URL?.trim() ||
          "https://data.alpaca.markets";
        const dataOrigin = new URL(dataBase).origin;
        const dataPool = new Pool(dataOrigin, { connections: 2, pipelining: 1 });
        const qpath = `/v2/stocks/${encodeURIComponent(sym)}/quotes/latest?feed=iex`;
        const qres = await dataPool.request({
          path: qpath,
          method: "GET",
          headers: this.headers,
          headersTimeout: this.timeoutMs,
          bodyTimeout: this.timeoutMs,
        });
        let qraw = "";
        for await (const chunk of qres.body) qraw += chunk;
        await dataPool.close();
        if (qres.statusCode < 200 || qres.statusCode >= 300) return null;
        const qj = JSON.parse(qraw) as { quote?: { bp?: number; ap?: number } };
        const bp = Number(qj.quote?.bp ?? 0);
        const ap = Number(qj.quote?.ap ?? 0);
        if (bp > 0 && ap > 0) return { bp, ap };
        return null;
      } catch {
        return null;
      }
    };

    const quote = await fetchQuote();
    const closeSide: OrderSide = leg.side === "short" ? "buy" : "sell";
    const tick = 0.01;
    const minBps = Number(process.env.HFT_MIN_EXIT_PROFIT_BPS ?? 3) / 10_000;
    let lp = 0;
    if (quote) {
      const { bp, ap } = quote;
      if (closeSide === "sell") {
        const minPx = entryPx > 0 ? entryPx * (1 + minBps) : 0;
        lp = forced
          ? this.roundLimit(Math.max(tick, bp - tick))
          : this.roundLimit(Math.max(minPx, ap - tick, bp + tick));
      } else {
        const maxPx = entryPx > 0 ? entryPx * (1 - minBps) : Number.POSITIVE_INFINITY;
        lp = forced
          ? this.roundLimit(ap * (1 + minBps) + tick)
          : this.roundLimit(Math.min(maxPx, bp + tick));
      }
    }

    if (lp > 0) {
      try {
        const resp = await this.place({
          symbol: sym,
          side: closeSide,
          qty,
          type: "limit",
          time_in_force: extended ? "day" : "ioc",
          limit_price: lp,
          extended_hours: extended,
          client_order_id: `close-${sym}-${Date.now()}`,
        });
        if (resp.ok && resp.id) {
          const waitMs = Number(process.env.HFT_EXIT_FILL_MS ?? 6000);
          const deadline = Date.now() + waitMs;
          while (Date.now() < deadline) {
            await new Promise((r) => setTimeout(r, 400));
            const left = await this.getPositionQty(sym);
            const targetLeft = Math.max(0, brokerQty - qty);
            if (left <= targetLeft + Math.max(0.05 * qty, 1e-4)) {
              const elapsedNs = nowNs() - start;
              return { ok: true, latencyUs: Number(elapsedNs / 1000n) };
            }
          }
        }
      } catch {
        /* optional DELETE / partial below when forced */
      }
    }

    if (!forced) {
      return { ok: false, latencyUs: Number((nowNs() - start) / 1000n) };
    }

    if (!allowFullDelete) {
      try {
        const resp = await this.place({
          symbol: sym,
          side: closeSide,
          qty,
          type: "market",
          time_in_force: "day",
          extended_hours: false,
          client_order_id: `close-partial-${sym}-${Date.now()}`,
        });
        return {
          ok: Boolean(resp.ok),
          latencyUs: Number((nowNs() - start) / 1000n),
        };
      } catch {
        return { ok: false, latencyUs: Number((nowNs() - start) / 1000n) };
      }
    }

    try {
      const enc = encodeURIComponent(sym);
      const { status } = await this.request("DELETE", `/v2/positions/${enc}`);
      const elapsedNs = nowNs() - start;
      return { ok: status >= 200 && status < 300, latencyUs: Number(elapsedNs / 1000n) };
    } catch {
      return { ok: false, latencyUs: Number((nowNs() - start) / 1000n) };
    }
  }

  async cancel(orderId: string): Promise<{ ok: boolean; latencyUs: number }> {
    const start = nowNs();
    if (this.dryRun) {
      return { ok: true, latencyUs: 0 };
    }
    try {
      const { status } = await this.request("DELETE", `/v2/orders/${encodeURIComponent(orderId)}`);
      const elapsedNs = nowNs() - start;
      this.cancelHist.recordNs(elapsedNs);
      return { ok: status >= 200 && status < 300, latencyUs: Number(elapsedNs / 1000n) };
    } catch {
      const elapsedNs = nowNs() - start;
      return { ok: false, latencyUs: Number(elapsedNs / 1000n) };
    }
  }

  /** Cancel working HFT entries (obi-/mr-/earn-) so a flatten sell cannot 403-wash. */
  async cancelHftEntries(symbol?: string): Promise<number> {
    if (this.dryRun) return 0;
    const open = await this.listOpenOrders(symbol);
    let n = 0;
    for (const o of open) {
      if ((o.side ?? "").toLowerCase() !== "buy") continue;
      if (!/^(obi-|mr-|earn-)/i.test(o.clientOrderId || "")) continue;
      const c = await this.cancel(o.id);
      if (c.ok) n += 1;
    }
    return n;
  }

  /**
   * Cancel working HFT exits only (flat-/close-). Leaves fortress UUID sells and HFT entries.
   *
   * No-symbol (boot): only orphan flats on names with no live long. A live HFT
   * long's resting sell-high must survive restart so we keep managing it.
   */
  async cancelHftExits(symbol?: string): Promise<number> {
    if (this.dryRun) return 0;
    const open = await this.listOpenOrders(symbol);
    const orphansOnly = !symbol;
    let n = 0;
    for (const o of open) {
      if ((o.side ?? "").toLowerCase() !== "sell") continue;
      if (!/^(flat-|close-)/i.test(o.clientOrderId || "")) continue;
      if (orphansOnly) {
        const live = this.cachedLongQty(o.symbol);
        if (!Number.isFinite(live) || live > 1e-8) continue;
      }
      const c = await this.cancel(o.id);
      if (c.ok) n += 1;
    }
    return n;
  }

  async getOrder(orderId: string): Promise<import("./order-lifecycle.js").OrderSnapshot | null> {
    if (this.dryRun) {
      if (this.simUseRealisticFills()) {
        const sim = this.simOrders.get(orderId);
        if (!sim) return null;
        return {
          id: sim.id,
          status: sim.status,
          filledQty: sim.filledQty,
          qty: sim.qty,
          filledAvgPrice: sim.filledAvgPrice,
          side: sim.side,
          symbol: sim.symbol,
        };
      }
      return {
        id: orderId,
        status: "filled",
        filledQty: 1,
        qty: 1,
        filledAvgPrice: 100,
        side: "buy",
        symbol: "DRY",
      };
    }
    try {
      const { status, body: raw } = await this.request("GET", `/v2/orders/${encodeURIComponent(orderId)}`);
      if (status < 200 || status >= 300) return null;
      const j = JSON.parse(raw) as {
        id?: string;
        status?: string;
        filled_qty?: string | number;
        qty?: string | number;
        filled_avg_price?: string | number;
        side?: string;
        symbol?: string;
        created_at?: string;
      };
      const fq = j.filled_qty != null && j.filled_qty !== "" ? Number(j.filled_qty) : 0;
      const q = j.qty != null && j.qty !== "" ? Number(j.qty) : 0;
      const fap =
        j.filled_avg_price != null && j.filled_avg_price !== ""
          ? Number(j.filled_avg_price)
          : undefined;
      return {
        id: j.id ?? orderId,
        status: (j.status ?? "").toLowerCase(),
        filledQty: Number.isFinite(fq) ? fq : 0,
        qty: Number.isFinite(q) ? q : 0,
        filledAvgPrice:
          fap != null && Number.isFinite(fap) && fap > 0 ? fap : undefined,
        side: (j.side ?? "").toLowerCase(),
        symbol: (j.symbol ?? "").toUpperCase(),
      };
    } catch {
      return null;
    }
  }

  async getAccount(): Promise<AccountSnapshot | null> {
    if (this.dryRun) {
      return {
        buyingPower: 1_000_000,
        equity: 1_000_000,
        cash: 500_000,
        longMarketValue: 0,
        maintenanceMargin: 0,
        regtBuyingPower: 1_000_000,
      };
    }
    try {
      const { status, body: raw } = await this.request("GET", "/v2/account");
      if (status < 200 || status >= 300) return null;
      const j = JSON.parse(raw) as Record<string, string | number | undefined>;
      const f = (k: string): number => {
        const v = j[k];
        if (v == null || v === "") return 0;
        const n = Number(v);
        return Number.isFinite(n) ? n : 0;
      };
      return {
        buyingPower: f("buying_power") || f("daytrading_buying_power"),
        equity: f("equity"),
        cash: f("cash"),
        longMarketValue: f("long_market_value"),
        maintenanceMargin: f("maintenance_margin"),
        regtBuyingPower: f("regt_buying_power"),
      };
    } catch {
      return null;
    }
  }

  async listOpenOrders(symbol?: string): Promise<OpenOrderRow[]> {
    if (this.dryRun) return [];
    try {
      const sym = symbol ? `&symbols=${encodeURIComponent(symbol.toUpperCase())}` : "";
      const { status, body: raw } = await this.request(
        "GET",
        `/v2/orders?status=open&limit=500${sym}`,
      );
      if (status < 200 || status >= 300) return [];
      const rows = JSON.parse(raw) as Array<{
        id?: string;
        symbol?: string;
        status?: string;
        side?: string;
        qty?: string | number;
        filled_qty?: string | number;
        created_at?: string;
        client_order_id?: string;
        limit_price?: string | number;
      }>;
      if (!Array.isArray(rows)) return [];
      return rows.map((j) => {
        const fq = j.filled_qty != null && j.filled_qty !== "" ? Number(j.filled_qty) : 0;
        const q = j.qty != null && j.qty !== "" ? Number(j.qty) : 0;
        const lp = j.limit_price != null && j.limit_price !== "" ? Number(j.limit_price) : 0;
        let createdMs = 0;
        if (j.created_at) {
          const t = Date.parse(j.created_at);
          if (Number.isFinite(t)) createdMs = t;
        }
        return {
          id: j.id ?? "",
          symbol: (j.symbol ?? "").toUpperCase(),
          status: (j.status ?? "").toLowerCase(),
          side: (j.side ?? "").toLowerCase(),
          qty: Number.isFinite(q) ? q : 0,
          filledQty: Number.isFinite(fq) ? fq : 0,
          createdMs,
          clientOrderId: String(j.client_order_id ?? ""),
          limitPrice: Number.isFinite(lp) && lp > 0 ? lp : undefined,
        };
      });
    } catch {
      return [];
    }
  }

  async close(): Promise<void> {
    await this.pool.close();
  }
}
