/**
 * REST market + news feed for earnings — no Alpaca WebSocket.
 *
 * Lets earnings coexist with OBI on a single-key Alpaca Basic plan:
 * OBI owns the sole IEX WS; earnings polls news + NBBO over REST.
 */
import { CFG } from "../common/config.js";
import { stdoutTag } from "../common/logger.js";
import type { EarningsFrame } from "./earnings-ingestor.js";
import type { EarningsEvaluator } from "./earnings-evaluator.js";

const log = stdoutTag("[EARN-REST]");

function authHeaders(): Record<string, string> {
  return {
    "APCA-API-KEY-ID": CFG.alpaca.key,
    "APCA-API-SECRET-KEY": CFG.alpaca.secret,
  };
}

async function fetchJson(url: string, headers: Record<string, string>): Promise<unknown> {
  const r = await fetch(url, { headers });
  if (!r.ok) {
    throw new Error(`${r.status} ${r.statusText} ${url}`);
  }
  return r.json();
}

function newsToFrame(item: Record<string, unknown>, tickers: Set<string>): EarningsFrame | null {
  const syms = Array.isArray(item.symbols)
    ? (item.symbols as string[]).map((s) => String(s).toUpperCase())
    : [];
  const hit = syms.find((s) => tickers.has(s));
  if (!hit) return null;
  const headline = String(item.headline ?? item.title ?? "");
  const summary = String(item.summary ?? item.description ?? "");
  const raw = JSON.stringify({
    ...item,
    headline,
    summary,
    // Evaluator looks for eps/revenue keys when present on wire payloads.
  });
  return {
    ticker: hit,
    receivedNs: process.hrtime.bigint(),
    rawText: raw,
    source: "alpaca",
  };
}

export class EarningsRestFeed {
  private newsTimer: ReturnType<typeof setInterval> | null = null;
  private quoteTimer: ReturnType<typeof setInterval> | null = null;
  private seenNews = new Set<string>();
  private stopped = false;

  constructor(
    private readonly tickers: readonly string[],
    private readonly evaluator: EarningsEvaluator,
    private readonly onFrame: (frame: EarningsFrame) => void,
  ) {}

  start(): void {
    const newsMs = Math.max(5_000, Number(process.env.EARN_REST_NEWS_MS ?? 30_000));
    const quoteMs = Math.max(15_000, Number(process.env.EARN_REST_QUOTE_MS ?? 60_000));
    log("start", {
      tickers: this.tickers.length,
      newsMs,
      quoteMs,
      mode: "coexist-rest-no-alpaca-ws",
    });
    void this.pollNews();
    // Defer first quote poll — OBI owns the RPM budget at startup.
    setTimeout(() => {
      if (!this.stopped) void this.pollQuotes();
    }, Math.min(quoteMs, 45_000));
    this.newsTimer = setInterval(() => void this.pollNews(), newsMs);
    this.quoteTimer = setInterval(() => void this.pollQuotes(), quoteMs);
    // Keep the process alive — unref() let Node exit after ~30s (rotator then
    // spawned a new earnings every poll and looked like random HFT crashes).
  }

  stop(): void {
    this.stopped = true;
    if (this.newsTimer) clearInterval(this.newsTimer);
    if (this.quoteTimer) clearInterval(this.quoteTimer);
    this.newsTimer = null;
    this.quoteTimer = null;
  }

  private async pollNews(): Promise<void> {
    if (this.stopped) return;
    const set = new Set(this.tickers.map((t) => t.toUpperCase()));
    try {
      // Prefer Polygon REST news when key present (no WS needed).
      if (CFG.polygon.key) {
        const url =
          `${CFG.polygon.restBase}/v2/reference/news?limit=25&order=desc&apiKey=${encodeURIComponent(CFG.polygon.key)}`;
        const js = (await fetchJson(url, {})) as { results?: Record<string, unknown>[] };
        for (const item of js.results ?? []) {
          const id = String(item.id ?? item.published_utc ?? JSON.stringify(item).slice(0, 80));
          if (this.seenNews.has(id)) continue;
          this.seenNews.add(id);
          const tickers = Array.isArray(item.tickers)
            ? (item.tickers as string[]).map((t) => String(t).toUpperCase())
            : [];
          const hit = tickers.find((t) => set.has(t));
          if (!hit) continue;
          const frame: EarningsFrame = {
            ticker: hit,
            receivedNs: process.hrtime.bigint(),
            rawText: JSON.stringify(item),
            source: "polygon",
          };
          this.onFrame(frame);
        }
        if (this.seenNews.size > 2000) {
          const keep = [...this.seenNews].slice(-1000);
          this.seenNews = new Set(keep);
        }
        return;
      }

      // Alpaca news REST (no WS).
      const syms = this.tickers.slice(0, 50).join(",");
      const url =
        `${CFG.alpaca.dataBase}/v1beta1/news?symbols=${encodeURIComponent(syms)}&limit=25&include_content=true&exclude_contentless=true`;
      const js = (await fetchJson(url, authHeaders())) as { news?: Record<string, unknown>[] };
      for (const item of js.news ?? []) {
        const id = String(item.id ?? item.created_at ?? "");
        if (!id || this.seenNews.has(id)) continue;
        this.seenNews.add(id);
        const frame = newsToFrame(item, set);
        if (frame) this.onFrame(frame);
      }
      if (this.seenNews.size > 2000) {
        const keep = [...this.seenNews].slice(-1000);
        this.seenNews = new Set(keep);
      }
    } catch (err) {
      log("news-poll-error", err instanceof Error ? err.message : err);
    }
  }

  private async pollQuotes(): Promise<void> {
    if (this.stopped || !CFG.alpaca.key) return;
    // Keep REST quiet — OBI already hammers data RPM. Quotes only for NBBO/VWAP guard.
    const batchSize = Math.max(1, Number(process.env.EARN_REST_QUOTE_BATCH ?? 6));
    const batch = this.tickers.slice(0, batchSize);
    if (!batch.length) return;
    try {
      const url =
        `${CFG.alpaca.dataBase}/v2/stocks/quotes/latest?symbols=${encodeURIComponent(batch.join(","))}&feed=iex`;
      const js = (await fetchJson(url, authHeaders())) as {
        quotes?: Record<string, { bp?: number; ap?: number; bs?: number; as?: number }>;
      };
      const quotes = js.quotes ?? {};
      for (const [sym, q] of Object.entries(quotes)) {
        const bid = Number(q.bp ?? 0);
        const ask = Number(q.ap ?? 0);
        const bidSz = Number(q.bs ?? 0);
        const askSz = Number(q.as ?? 0);
        if (bid > 0 && ask > 0) {
          this.evaluator.ingestQuote(sym, bid, ask, bidSz, askSz);
          const mid = (bid + ask) / 2;
          this.evaluator.ingestTrade(sym, mid, Math.max(bidSz, askSz, 1), Date.now());
        }
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      log("quote-poll-error", msg);
      // On 429, stretch the quote interval by restarting timers lazily next cycle.
      if (msg.includes("429") && this.quoteTimer) {
        clearInterval(this.quoteTimer);
        const slow = Math.max(60_000, Number(process.env.EARN_REST_QUOTE_MS ?? 60_000) * 2);
        this.quoteTimer = setInterval(() => void this.pollQuotes(), slow);
        log("quote-backoff", { ms: slow });
      }
    }
  }
}
