/**
 * ============================================================================
 * PHASE 1 — ULTRA-LOW LATENCY INGESTION ENGINE
 * ============================================================================
 *
 * Connects to a premium news wire (Benzinga or Polygon, auto-selected on key
 * presence) and a market-data stream (Polygon stocks or Alpaca data).
 *
 *   • `ws` with perMessageDeflate=false + skipUTF8Validation=true → zero
 *     compression/CPU overhead, raw Buffer delivered per frame.
 *   • Byte-level Boyer-Moore prefilter via `TickerPrefilter.match()`. JSON.parse
 *     is *only* called once a ticker token has hit, so >99% of irrelevant
 *     frames (sports headlines etc.) are rejected in ~5-15 µs.
 *   • `process.hrtime.bigint()` stamps every received frame; the timestamp is
 *     forwarded to the evaluator so the full ingest→fire chain is measurable.
 */
import WebSocket, { type RawData } from "ws";

import { CFG } from "../common/config.js";
import { LatencyHistogram, nowNs } from "../common/latency.js";
import { stdoutTag } from "../common/logger.js";
import { TickerPrefilter } from "../common/prefilter.js";

const log = stdoutTag("[INGEST]");

export interface EarningsFrame {
  ticker: string;
  receivedNs: bigint;
  rawText: string;
  source: "benzinga" | "polygon" | "alpaca" | "unknown";
}

export interface IngestorOptions {
  tickers: readonly string[];
  onFrame: (frame: EarningsFrame) => void;
}

/** Pre-allocated UTF-8 decoder reused for every frame. */
const TEXT_DECODER = new TextDecoder("utf-8", { fatal: false });

/** Convert raw ws data → single Buffer with minimal copying. */
function asBuffer(data: RawData): Buffer {
  if (Buffer.isBuffer(data)) return data;
  if (Array.isArray(data)) return Buffer.concat(data as Buffer[]);
  if (data instanceof ArrayBuffer) return Buffer.from(data);
  return Buffer.from(data as Uint8Array);
}

export class EarningsIngestor {
  private ws: WebSocket | null = null;
  private readonly prefilter: TickerPrefilter;
  private readonly source: "benzinga" | "polygon" | "alpaca";
  private readonly hist = new LatencyHistogram(8192, "ingest.prefilter");
  private framesSeen = 0;
  private framesMatched = 0;
  private reconnectMs = 500;

  constructor(private readonly opts: IngestorOptions) {
    this.prefilter = new TickerPrefilter(opts.tickers);
    if (CFG.benzinga.key) this.source = "benzinga";
    else if (CFG.polygon.key && CFG.polygon.useWebsocket) this.source = "polygon";
    else this.source = "alpaca";
  }

  /** True when this process would open Alpaca IEX WS (conflicts with OBI). */
  usesAlpacaWebsocket(): boolean {
    return this.source === "alpaca";
  }

  start(): void {
    // Coexist mode: refuse Alpaca WS so OBI keeps the sole connection.
    if (this.source === "alpaca" && (CFG.earn.coexistWithObi || CFG.hftCoexist)) {
      log("alpaca-ws-skipped", {
        reason: "EARNINGS_COEXIST_WITH_OBI — use EarningsRestFeed instead",
      });
      return;
    }
    const url = this.streamUrl();
    log("connecting", { source: this.source, url, tickers: this.prefilter.tickerCount() });
    const ws = new WebSocket(url, {
      perMessageDeflate: false,
      skipUTF8Validation: true,
      handshakeTimeout: 5000,
    });
    this.ws = ws;
    ws.on("open", () => this.onOpen());
    ws.on("message", (data) => this.onMessage(asBuffer(data)));
    ws.on("close", (code) => this.onClose(code));
    ws.on("error", (err) => log("ws-error", { msg: err.message }));
    ws.on("ping", () => ws.pong());
  }

  stop(): void {
    if (this.ws) {
      this.ws.removeAllListeners();
      this.ws.terminate();
      this.ws = null;
    }
  }

  private streamUrl(): string {
    switch (this.source) {
      case "benzinga":
        return CFG.benzinga.newsStream;
      case "polygon":
        return CFG.polygon.stocksStream;
      case "alpaca":
        return CFG.alpaca.dataStream;
    }
  }

  private onOpen(): void {
    this.reconnectMs = 500;
    log("ws-open", { source: this.source });
    if (!this.ws) return;
    switch (this.source) {
      case "benzinga":
        this.ws.send(JSON.stringify({ action: "authenticate", token: CFG.benzinga.key }));
        this.ws.send(JSON.stringify({ action: "subscribe", channels: ["news"] }));
        break;
      case "polygon":
        this.ws.send(JSON.stringify({ action: "auth", params: CFG.polygon.key }));
        // News + trades on watched tickers.
        const stars = this.opts.tickers.map((t) => `T.${t}`).join(",");
        this.ws.send(JSON.stringify({ action: "subscribe", params: `N.*,${stars}` }));
        break;
      case "alpaca":
        // News-only when forced onto Alpaca WS (legacy). Prefer REST coexist path.
        this.ws.send(JSON.stringify({ action: "auth", key: CFG.alpaca.key, secret: CFG.alpaca.secret }));
        this.ws.send(
          JSON.stringify({
            action: "subscribe",
            news: ["*"],
            // Never subscribe trades/quotes here — burns channel budget shared with OBI.
          }),
        );
        break;
    }
  }

  private onClose(code: number): void {
    log("ws-close", { code, reconnectMs: this.reconnectMs });
    setTimeout(() => this.start(), this.reconnectMs);
    this.reconnectMs = Math.min(15_000, this.reconnectMs * 2);
  }

  private onMessage(buf: Buffer): void {
    const t0 = nowNs();
    this.framesSeen++;
    const hit = this.prefilter.match(buf);
    if (!hit) {
      this.hist.recordNs(nowNs() - t0);
      return;
    }
    this.framesMatched++;
    const text = TEXT_DECODER.decode(buf);
    this.hist.recordNs(nowNs() - t0);
    this.opts.onFrame({ ticker: hit, receivedNs: t0, rawText: text, source: this.source });
  }

  stats(): Record<string, number | object> {
    return {
      framesSeen: this.framesSeen,
      framesMatched: this.framesMatched,
      hitRate: this.framesSeen === 0 ? 0 : this.framesMatched / this.framesSeen,
      prefilterUs: this.hist.snapshot(),
    };
  }
}
