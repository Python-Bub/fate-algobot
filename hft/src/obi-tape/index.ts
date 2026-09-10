/**
 * OBI + Tape Velocity HFT main entry point.
 *
 *   npm run obi-tape          # default
 *   npm run obi-tape:perf     # GC-quieted V8 flags for live spikes
 *
 * ----------------------------------------------------------------------------
 *  CONFIG (all values come from /.env or hft/.env — see hft/.env.example)
 * ----------------------------------------------------------------------------
 *   OBI_TICKER_WHITELIST=...      tickers to monitor
 *   OBI_TRIGGER_LONG=0.75         OBI ≥ this AND burst → buy
 *   OBI_TRIGGER_SHORT=-0.75       OBI ≤ this AND burst → sell
 *   TAPE_VELOCITY_WINDOW_MS=100   fast tape window
 *   TAPE_BASELINE_WINDOW_MS=5000  baseline tape window
 *   TAPE_VELOCITY_MULTIPLIER=5.0  burst threshold (5x baseline)
 *   OBI_NOTIONAL_USD=1000         per-order budget
 *   OBI_MICRO_STOP_TICKS=3        flatten threshold
 *   OBI_BUDGET_LATENCY_MS=10      per-update processing budget
 *   TICK_SIZE=0.01
 *   HFT_PER_TICKER_COOLDOWN_MS=60000  post-fill lockdown window
 *
 * Topology:
 *
 *   Polygon WS (T.*, Q.*, XL.*) ─► parser ─► L2Book / TapeVelocity
 *                                            │
 *                                            ├─► ObiTapeSignals.onObi/onTape
 *                                            │
 *                                            ▼
 *                                  ObiTapeSignals.maybeFire (Phase 3)
 *                                            │
 *                                            ▼
 *                                  ObiTapeRiskManager.monitor (Phase 4)
 */
import { request as httpRequest } from "undici";
import WebSocket, { type RawData } from "ws";
import fs from "node:fs";

import { AlpacaExecutor } from "../common/alpaca-exec.js";
import { CFG } from "../common/config.js";
import { KillSwitch } from "../common/kill-switch.js";
import { LatencyHistogram, nowNs } from "../common/latency.js";
import { fileLogger, stdoutTag } from "../common/logger.js";
import { TickerPrefilter } from "../common/prefilter.js";

import { L2Book } from "./l2-book.js";
import { TapeVelocity } from "./tape-velocity.js";
import { ObiTapeSignals } from "./obi-tape-signals.js";
import { ObiTapeRiskManager } from "./obi-tape-risk.js";
import { CandleBuilder } from "./jp-candles.js";
import { AdvancedChartEngine } from "./advanced-charts.js";
import { MicroMeanReversion } from "./micro-mean-reversion.js";
import { flattenQuoteOk, restSpreadOk, sanitizeRestQuote, completeNbbo } from "./order-pricing.js";
import { assessQuoteHealth } from "./quote-health.js";
import { resolveSignalMode } from "./signal-mode.js";
import { pickWsTickers } from "./pick-ws.js";

/** Alpaca IEX `t` is ISO-8601 string; Polygon may send ms/ns numbers. Never Number(iso). */
function parseExchangeTsMs(raw: unknown, fallbackMs = Date.now()): number {
  if (typeof raw === "number" && Number.isFinite(raw)) {
    if (raw > 1e15) return Math.floor(raw / 1e6); // ns → ms
    if (raw > 1e12) return Math.floor(raw); // ms
    if (raw > 1e9) return Math.floor(raw * 1000); // sec → ms
    return fallbackMs;
  }
  if (typeof raw === "string" && raw.trim()) {
    const p = Date.parse(raw);
    if (Number.isFinite(p)) return p;
  }
  return fallbackMs;
}
import { cancelStaleOpenOrders, hasOpenOrder, isHftEntryClientId } from "../common/order-lifecycle.js";
import { startMarginGuard } from "../common/margin-guard.js";
import { currentSession, hftLimitTif } from "../common/market-session.js";
import { CircuitBreaker } from "../common/circuit-breaker.js";

const log = stdoutTag("[OBI]");

// --- pre-allocated per-ticker state maps ---------------------------------
const books = new Map<string, L2Book>();
const tapes = new Map<string, TapeVelocity>();
const candles = new Map<string, CandleBuilder>();
const charts = new Map<string, AdvancedChartEngine>();
/** Last mid that passed quote-health — used to catch bad-feed price shocks. */
const lastGoodMid = new Map<string, number>();

function ensureState(ticker: string): {
  book: L2Book;
  tape: TapeVelocity;
  candle: CandleBuilder;
  chart: AdvancedChartEngine;
} {
  let book = books.get(ticker);
  if (!book) {
    book = new L2Book(ticker);
    books.set(ticker, book);
  }
  let tape = tapes.get(ticker);
  if (!tape) {
    tape = new TapeVelocity(ticker, CFG.obi.tapeWindowMs, CFG.obi.baselineWindowMs);
    tapes.set(ticker, tape);
  }
  let candle = candles.get(ticker);
  if (!candle) {
    candle = new CandleBuilder(ticker, Number(process.env.HFT_CANDLE_MS ?? 1000), 120);
    candles.set(ticker, candle);
  }
  let chart = charts.get(ticker);
  if (!chart) {
    chart = new AdvancedChartEngine(64);
    charts.set(ticker, chart);
  }
  return { book, tape, candle, chart };
}

function asBuffer(data: RawData): Buffer {
  if (Buffer.isBuffer(data)) return data;
  if (Array.isArray(data)) return Buffer.concat(data as Buffer[]);
  if (data instanceof ArrayBuffer) return Buffer.from(data);
  return Buffer.from(data as Uint8Array);
}

async function main(): Promise<void> {
  if (CFG.globalKill) {
    log("HFT_GLOBAL_KILL=true — refusing to start.");
    process.exit(2);
  }
  if (!CFG.polygon.key && !CFG.alpaca.key) {
    log("No POLYGON_API_KEY or ALPACA_API_KEY — set HFT_DRY_RUN=true for paper rehearsal.");
  }

  // Alpaca IEX: trades+quotes share a ~30-channel budget → ≤15 symbols on WS.
  // Overflow stays live via REST poll (do not shrink universe).
  const iexWsMax = Math.max(
    1,
    Number(process.env.HFT_IEX_WS_MAX_SYMBOLS ?? process.env.ALPACA_IEX_WS_MAX_SYMBOLS ?? 15),
  );
  const useAlpacaStream =
    !(CFG.polygon.key && CFG.polygon.useWebsocket) &&
    String(CFG.alpaca.dataStream || "").includes("alpaca.markets");
  const broker = new AlpacaExecutor(CFG.alpaca.baseUrl, CFG.alpaca.key, CFG.alpaca.secret, CFG.dryRun);
  await broker.warmPositions();
  log("positions-warm", { n: broker.cachedPositionCount(), ready: broker.positionsReady() });
  const held = new Set(broker.heldSymbols());
  // Rest file is unheld liquid names — put them on IEX WS first. Whitelist
  // mega-caps are often fortress longs and would skip-all under BLOCK_ADD.
  const pool = [...CFG.obi.restTickers, ...CFG.obi.tickers];
  const wsTickers = useAlpacaStream
    ? pickWsTickers(pool, held, iexWsMax)
    : pickWsTickers(pool, new Set(), Math.max(pool.length, 1));
  if (wsTickers.length < iexWsMax) {
    log("ws-universe-short", { got: wsTickers.length, want: iexWsMax, held: held.size });
  }
  const wsSet = new Set(wsTickers.map((t) => t.toUpperCase()));
  const restOnly = pool.filter(
    (t, i, arr) =>
      !wsSet.has(t.toUpperCase()) &&
      arr.findIndex((x) => x.toUpperCase() === t.toUpperCase()) === i,
  );
  const pollTickers = [...wsTickers, ...restOnly];
  log("iex-ws-cap", { ws: wsTickers.length, restSpill: restOnly.length, cap: iexWsMax, held: held.size });
  startMarginGuard(broker);
  const kill = new KillSwitch(pollTickers, CFG.cooldownMs, CFG.maxOrdersPerMin);
  const circuit = new CircuitBreaker();
  const signals = new ObiTapeSignals(broker, kill, circuit);
  const risk = new ObiTapeRiskManager(broker, signals.openPositions, circuit, kill);
  const mr = new MicroMeanReversion(broker, kill, (sym) => books.get(sym.toUpperCase()), circuit);
  const restMrLastMs = new Map<string, number>();
  const restMrMinGapMs = Number(process.env.HFT_MR_REST_MIN_GAP_MS ?? 1500);
  const prefilter = new TickerPrefilter(wsTickers);
  const procHist = new LatencyHistogram(8192, "obi.process");

  // Pre-touch state for every watched ticker so the first market frame doesn't
  // pay the Map allocation cost on the hot path.
  for (const t of pollTickers) ensureState(t);

  const obiEntriesEnabled =
    process.env.HFT_OBI_ENABLED !== "false" && process.env.HFT_JP_CANDLE_ONLY !== "true";

  const skips = {
    health: 0,
    oneSided: 0,
    synthetic: 0,
    restApplied: 0,
    fire: 0,
  };

  const tryFire = (sym: string, t0: bigint, candleJustClosed = false): void => {
    try {
    const st = ensureState(sym);
    const health = assessQuoteHealth(st.book, st.book.lastExchangeTsMs, lastGoodMid.get(sym));
    if (health.adoptMid !== false && st.book.mid > 0) lastGoodMid.set(sym, st.book.mid);
    if (!health.ok) {
      fileLogger.emit("quote_reject", {
        ticker: sym,
        reason: health.reason,
        detail: health.detail,
        ageMs: health.ageMs,
        moveBps: health.moveBps,
        bid: st.book.bestBid,
        ask: st.book.bestAsk,
        mid: st.book.mid,
      });
      // Never flatten on stale/crossed/shock quotes — that was the MAX-HOLD 429 storm.
      skips.health++;
      return;
    }
    if (mr.hasExposure(sym)) {
      mr.monitor(st.book);
    }
    if (mr.hasExposure(sym) || signals.hasExposure(sym)) {
      if (flattenQuoteOk(st.book)) risk.monitor(st.book);
      return;
    }
    if (st.book.syntheticNbbo) skips.synthetic++;
    let fired = false;
    if (obiEntriesEnabled) {
      fired = signals.maybeFire(st.book, st.tape, t0, wsSet.has(sym.toUpperCase()));
      if (fired) skips.fire++;
    }
    if (!fired && process.env.HFT_MR_ENABLED !== "false") {
      if (candleJustClosed) st.chart.onCandleClose(st.candle);
      mr.maybeFire(st.candle, st.book, st.tape, t0, candleJustClosed, st.chart.last);
    }
    if (flattenQuoteOk(st.book)) risk.monitor(st.book);
    } catch (e) {
      log("tryFire-err", { ticker: sym, err: e instanceof Error ? e.message : String(e) });
    }
  };

  let url = CFG.polygon.key && CFG.polygon.useWebsocket ? CFG.polygon.stocksStream : CFG.alpaca.dataStream;
  const useAlpaca = !(CFG.polygon.key && CFG.polygon.useWebsocket);
  let reconnectAttempt = 0;
  let ws: WebSocket | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let alpacaAuthed = false;
  let lastWsMsgMs = Date.now();
  let marketFrames = 0;

  function sendSubscribe(sock: WebSocket): void {
    if (!useAlpaca) {
      const subs: string[] = [];
      for (const t of wsTickers) {
        subs.push(`T.${t}`);
        subs.push(`Q.${t}`);
        if (CFG.polygon.useLevel2) subs.push(`XL.${t}`);
      }
      sock.send(JSON.stringify({ action: "subscribe", params: subs.join(",") }));
    } else {
      sock.send(JSON.stringify({ action: "subscribe", trades: wsTickers, quotes: wsTickers }));
      log("ws-subscribe", { ws: wsTickers.length, restOnly: restOnly.length });
    }
  }

  function connect(): void {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    if (ws) {
      ws.removeAllListeners();
      try {
        ws.terminate();
      } catch {
        /* ignore */
      }
      ws = null;
    }
    alpacaAuthed = false;
    ws = new WebSocket(url, {
      perMessageDeflate: false,
      skipUTF8Validation: true,
      handshakeTimeout: 5000,
    });
    bindHandlers(ws);
  }

  function scheduleReconnect(): void {
    reconnectAttempt++;
    const wait = Math.min(60000, 1000 * 2 ** Math.min(reconnectAttempt, 6));
    log("ws-reconnect", { attempt: reconnectAttempt, waitMs: wait });
    reconnectTimer = setTimeout(() => connect(), wait);
  }

  function bindHandlers(sock: WebSocket): void {

  sock.on("open", () => {
    reconnectAttempt = 0;
    log("ws-open", { url });
    if (!useAlpaca) {
      sock.send(JSON.stringify({ action: "auth", params: CFG.polygon.key }));
      sendSubscribe(sock);
    }
    // Alpaca: wait for "connected" / "authenticated" control frames before subscribe.
  });

  sock.on("message", (data) => {
    const t0 = nowNs();
    lastWsMsgMs = Date.now();
    const buf = asBuffer(data);
    if (useAlpaca) {
      try {
        const ctrl = JSON.parse(buf.toString("utf8")) as unknown;
        const rows: any[] = Array.isArray(ctrl) ? (ctrl as any[]) : [ctrl];
        for (const row of rows) {
          if (!row || typeof row !== "object") continue;
          const typ = String(row.T ?? row.t ?? "");
          const msg = String(row.msg ?? row.message ?? "");
          if (typ === "error" || typ === "subscription") {
            log("ws-ctrl", { typ, msg: msg || row });
            if (
              typ === "error" &&
              msg.includes("insufficient subscription") &&
              url.includes("/v2/sip")
            ) {
              url = "wss://stream.data.alpaca.markets/v2/iex";
              log("ws-fallback", { to: url });
              sock.close();
              return;
            }
          }
          if (typ === "success" && msg === "connected") {
            sock.send(JSON.stringify({ action: "auth", key: CFG.alpaca.key, secret: CFG.alpaca.secret }));
          }
          if (typ === "success" && msg === "authenticated" && !alpacaAuthed) {
            alpacaAuthed = true;
            sendSubscribe(sock);
          }
        }
      } catch {
        /* market frame */
      }
    }
    const hit = prefilter.match(buf);
    if (!hit) {
      procHist.recordNs(nowNs() - t0);
      return;
    }
    // Parse once we know it's relevant; payloads are small.
    let parsed: unknown;
    try {
      parsed = JSON.parse(buf.toString("utf8"));
    } catch {
      procHist.recordNs(nowNs() - t0);
      return;
    }
    const messages: any[] = Array.isArray(parsed) ? (parsed as any[]) : [parsed];
    for (let i = 0; i < messages.length; i++) {
      const m = messages[i];
      if (!m || typeof m !== "object") continue;
      const sym = (m.sym || m.S || m.T || m.ticker || "").toString().toUpperCase();
      if (!sym || sym !== hit) continue;
      const st = ensureState(sym);
      const ev = (m.ev || m.T || "").toString();
      const tsMs = parseExchangeTsMs(m.t ?? m.timestamp);

      if (ev === "T" || ev === "trade" || ev === "t") {
        const px = Number(m.p || m.price || 0);
        const sz = Number(m.s || m.size || 0);
        st.tape.onTrade(tsMs, px, sz);
        const candleJustClosed = st.candle.onTrade(tsMs, px, sz);
        const burst = st.tape.lastBurstRatio >= CFG.obi.velocityMult;
        signals.onTape(sym, burst);
        tryFire(sym, t0, candleJustClosed);
      } else if (ev === "Q" || ev === "quote" || ev === "q") {
        const rawBp = Number(m.bp || m.bid_price || m.bp_ || 0);
        const rawAp = Number(m.ap || m.ask_price || 0);
        const bs = Number(m.bs || m.bid_size || 0);
        const as_ = Number(m.as || m.ask_size || 0);
        const filled = completeNbbo(rawBp, rawAp, st.tape.lastPx);
        if (!(filled.bp > 0 && filled.ap > 0)) {
          skips.oneSided++;
          continue;
        }
        st.book.applyDelta(0, 0, filled.bp, Math.max(bs, filled.synthetic ? 1 : 0), tsMs);
        st.book.applyDelta(0, 1, filled.ap, Math.max(as_, filled.synthetic ? 1 : 0), tsMs);
        st.book.syntheticNbbo = filled.synthetic;
        signals.onObi(st.book);
        tryFire(sym, t0);
      } else if (ev === "XL" || ev === "l2book") {
        // Polygon L2 snapshot: { bids: [[px, sz],...], asks: [[px, sz],...] }
        const bids = Array.isArray(m.bids) ? (m.bids as [number, number][]) : [];
        const asks = Array.isArray(m.asks) ? (m.asks as [number, number][]) : [];
        st.book.applySnapshot(bids, asks, tsMs);
        signals.onObi(st.book);
        tryFire(sym, t0);
      }
    }
    wsMsgsSincePoll++;
    marketFrames++;
    procHist.recordNs(nowNs() - t0);
  });

  sock.on("close", (code) => {
    log("ws-close", { code });
    alpacaAuthed = false;
    if (sock === ws) scheduleReconnect();
  });
  sock.on("error", (err) => log("ws-error", err.message));
  sock.on("ping", () => sock.pong());
  } // end bindHandlers

  connect();

  // Dead WS: only force-reconnect when REST is NOT the heartbeat. REST-always
  // mode must not terminate a quiet IEX socket every 30s (code 1006 storm).
  const wsSilenceMs = Number(process.env.HFT_WS_SILENCE_RECONNECT_MS ?? 120_000);
  const restAlways = process.env.HFT_REST_POLL_ALWAYS === "true";
  const silenceTimer = setInterval(() => {
    if (!useAlpaca || wsSilenceMs <= 0 || restAlways) return;
    const quietFor = Date.now() - lastWsMsgMs;
    if (quietFor < wsSilenceMs) return;
    log("ws-silence-reconnect", { quietForMs: quietFor, marketFrames });
    marketFrames = 0;
    lastWsMsgMs = Date.now();
    try {
      alpacaAuthed = false;
      ws?.terminate();
    } catch {
      /* ignore */
    }
  }, Math.min(15_000, Math.max(5_000, wsSilenceMs / 3)));
  silenceTimer.unref();

  // When IEX websocket goes quiet (after-hours / closed), poll Alpaca REST quotes.
  let wsMsgsSincePoll = 0;
  const pollMs = Number(process.env.HFT_REST_POLL_MS ?? 2000);
  const pollAlways = process.env.HFT_REST_POLL_ALWAYS === "true";
  const pollQuietThreshold = Number(process.env.HFT_REST_POLL_QUIET_N ?? 30);

  let restBackoffUntil = 0;
  let restPollCursor = 0;
  let restFeed = (process.env.HFT_REST_QUOTE_FEED || "sip").trim().toLowerCase() || "sip";

  async function pollRestQuotes(): Promise<void> {
    if (!CFG.alpaca.key || CFG.dryRun) return;
    if (Date.now() < restBackoffUntil) return;
    const nTickers = pollTickers.length;
    if (nTickers === 0) return;
    const sliceN = Math.max(1, Number(process.env.HFT_REST_POLL_SLICE ?? 12));
    const pollAll = process.env.HFT_REST_POLL_ALL_SYMS === "true";
    let batch: string[];
    if (pollAll && sliceN >= nTickers) {
      batch = pollTickers;
    } else {
      batch = [];
      const take = Math.min(sliceN, nTickers);
      for (let k = 0; k < take; k++) {
        batch.push(pollTickers[(restPollCursor + k) % nTickers]!);
      }
      restPollCursor = (restPollCursor + take) % nTickers;
    }
    const chunkSz = Math.max(1, Number(process.env.HFT_REST_QUOTE_CHUNK ?? 12));
    try {
      const nowMs = Date.now();
      const sess = currentSession();
      const sessMode = (process.env.HFT_TRADE_SESSION || "extended").toLowerCase();
      const restExtendedMr =
        process.env.HFT_MR_REST_EXTENDED !== "false" &&
        (sessMode === "extended" || sessMode === "always" || sessMode === "24x5") &&
        sess !== "regular";

      for (let i = 0; i < batch.length; i += chunkSz) {
        const slice = batch.slice(i, i + chunkSz);
        const syms = slice.join(",");
        const path = `/v2/stocks/quotes/latest?symbols=${encodeURIComponent(syms)}&feed=${encodeURIComponent(restFeed)}`;
        const res = await httpRequest(`${CFG.alpaca.dataBase}${path}`, {
          method: "GET",
          headers: {
            "APCA-API-KEY-ID": CFG.alpaca.key,
            "APCA-API-SECRET-KEY": CFG.alpaca.secret,
          },
          headersTimeout: 8000,
          bodyTimeout: 8000,
        });
        const raw = await res.body.text();
        if (res.statusCode === 429) {
          const backoff = Number(process.env.HFT_REST_429_BACKOFF_MS ?? 20_000);
          restBackoffUntil = Date.now() + backoff;
          log("rest-poll-429", { backoffMs: backoff, body: raw.slice(0, 180) });
          break;
        }
        if (res.statusCode === 403 || res.statusCode === 422) {
          if (restFeed !== "iex") {
            log("rest-feed-fallback", { from: restFeed, to: "iex", status: res.statusCode });
            restFeed = "iex";
          }
          break;
        }
        if (res.statusCode < 200 || res.statusCode >= 300) {
          if (i === 0) log("rest-poll-http", { status: res.statusCode, body: raw.slice(0, 180) });
          break;
        }
        const body = JSON.parse(raw) as { quotes?: Record<string, { bp?: number; ap?: number; bs?: number; as?: number; t?: string }> };
        const quotes = body.quotes ?? {};
        for (const sym of slice) {
        const q = quotes[sym];
        if (!q) continue;
        const rawBp = Number(q.bp ?? 0);
        const rawAp = Number(q.ap ?? 0);
        const bs = Number(q.bs ?? 1);
        const as_ = Number(q.as ?? 1);
        const st = ensureState(sym);
        const filled = completeNbbo(rawBp, rawAp, st.tape.lastPx);
        if (!(filled.bp > 0 && filled.ap > 0)) {
          skips.oneSided++;
          continue;
        }
        const { bp, ap, mid, rawBps } = sanitizeRestQuote(filled.bp, filled.ap);
        if (!(bp > 0 && ap > 0)) {
          skips.oneSided++;
          continue;
        }
        const tsMs = nowMs;
        st.book.applyDelta(0, 0, bp, Math.max(bs, 1), tsMs);
        st.book.applyDelta(0, 1, ap, Math.max(as_, 1), tsMs);
        st.book.syntheticNbbo = filled.synthetic;
        signals.onObi(st.book);
        skips.restApplied++;
        if (
          restExtendedMr &&
          process.env.HFT_MR_ENABLED !== "false" &&
          restSpreadOk(st.book) &&
          !mr.hasExposure(sym) &&
          !signals.hasExposure(sym)
        ) {
          const lastRest = restMrLastMs.get(sym) ?? 0;
          if (nowMs - lastRest >= restMrMinGapMs) {
            const pollIdx = Math.floor(nowMs / pollMs);
            const symIdx = pollTickers.indexOf(sym);
            const dipEvery = Number(process.env.HFT_MR_REST_DIP_EVERY_N ?? 3);
            const dipPct = Number(process.env.HFT_MR_REST_DIP_PCT ?? 0.002);
            const dipMult = Number(process.env.HFT_MR_REST_DIP_MULT ?? 2.5);
            const dip =
              (pollIdx + symIdx) % dipEvery === 0 ? mid * dipPct * dipMult : 0;
            if (dip > 0 && mid > 0) {
              const sz = Math.max(bs, as_, 1);
              // Anchor VWAP at mid, then tick down so dipBelowVwap can trigger.
              st.tape.onTrade(tsMs, mid, sz);
              const closedA = st.candle.onTrade(tsMs, mid, sz);
              const px = Math.max(0.01, mid - dip);
              st.tape.onTrade(tsMs + 1, px, sz);
              const closedB = st.candle.onTrade(tsMs + 1, px, sz);
              if (closedA || closedB) st.chart.onCandleClose(st.candle);
              if (mr.maybeFire(st.candle, st.book, st.tape, nowNs(), closedA || closedB, st.chart.last)) {
                restMrLastMs.set(sym, nowMs);
              }
            }
          }
          if (mr.hasExposure(sym)) mr.monitor(st.book);
          if (flattenQuoteOk(st.book)) risk.monitor(st.book);
        } else {
          if (mr.hasExposure(sym)) mr.monitor(st.book);
          if (flattenQuoteOk(st.book)) risk.monitor(st.book);
        }
        if (process.env.HFT_REST_LOG_VERBOSE === "true") {
          log("rest-poll", { sym, bp, ap, rawBps: Math.round(rawBps), obi: st.book.obi });
        }
        try {
          const tRest = nowNs();
          tryFire(sym, tRest);
          procHist.recordNs(nowNs() - tRest);
        } catch (e) {
          log("tryFire-err", e instanceof Error ? e.message : String(e));
        }
      }
      }
    } catch (e) {
      log("rest-poll-err", e instanceof Error ? e.message : String(e));
    }
  }

  const pollTimer = setInterval(() => {
    const quiet = wsMsgsSincePoll < pollQuietThreshold;
    wsMsgsSincePoll = 0;
    if (pollAlways || quiet) void pollRestQuotes();
  }, pollMs);
  pollTimer.unref();

  const statsTimer = setInterval(() => {
    log("stats", {
      proc_us: procHist.snapshot(),
      place_us: broker.placeHist.snapshot(),
      openPositions: signals.openPositions.size,
      restFeed,
      skips: { ...skips },
    });
    skips.health = 0;
    skips.oneSided = 0;
    skips.synthetic = 0;
    skips.restApplied = 0;
    skips.fire = 0;
  }, 30_000);
  statsTimer.unref();

  const staleSweepMs = Number(process.env.HFT_STALE_ORDER_SWEEP_MS ?? 0);
  const staleMaxAgeMs = Number(process.env.HFT_STALE_ORDER_MAX_AGE_MS ?? 900_000);
  const sweepTimer = setInterval(() => {
    if (CFG.dryRun || !CFG.alpaca.key || staleSweepMs <= 0) return;
    void (async () => {
      let canceled = 0;
      for (const sym of pollTickers) {
        canceled += await cancelStaleOpenOrders(broker, sym, staleMaxAgeMs);
      }
      if (canceled > 0) log("stale-order-sweep", { canceled, maxAgeMs: staleMaxAgeMs });
    })();
  }, staleSweepMs);
  sweepTimer.unref();

  const shutdown = async (sig: string): Promise<void> => {
    log("shutdown", { sig });
    clearInterval(statsTimer);
    clearInterval(pollTimer);
    clearInterval(sweepTimer);
    clearInterval(silenceTimer);
    if (reconnectTimer) clearTimeout(reconnectTimer);
    if (ws) {
      ws.removeAllListeners();
      ws.terminate();
    }
    await broker.close();
    process.exit(0);
  };
  process.on("SIGINT", () => void shutdown("SIGINT"));
  process.on("SIGTERM", () => void shutdown("SIGTERM"));

  const scopeSet = new Set(pollTickers.map((t) => t.toUpperCase()));
  const reconcileMs = Number(process.env.HFT_ORPHAN_RECONCILE_MS ?? 180_000);
  const orphanLastAttempt = new Map<string, number>();
  const orphanCooldownMs = Number(process.env.HFT_ORPHAN_COOLDOWN_MS ?? 120_000);
  const hftMaxNotional = Number(
    process.env.HFT_MAX_ORDER_NOTIONAL ?? process.env.FORTRESS_GO_LIVE_MAX_NOTIONAL ?? 2500,
  );

  function loadProtectedSleeves(): Set<string> {
    const owned = new Set<string>();
    try {
      const path =
        process.env.PORTFOLIO_HEAD_REGISTRY ||
        `${process.env.FATE_ROOT || process.cwd().replace(/\/hft$/, "")}/data/portfolio_head_registry.json`;
      if (!fs.existsSync(path)) return owned;
      const doc = JSON.parse(fs.readFileSync(path, "utf8")) as {
        heads?: Record<string, string>;
      };
      for (const [sym, head] of Object.entries(doc.heads || {})) {
        const h = String(head || "").toLowerCase();
        if (h && h !== "hft") owned.add(sym.toUpperCase());
      }
    } catch {
      /* registry optional */
    }
    return owned;
  }

  async function adoptBrokerLegs(): Promise<void> {
    if (CFG.dryRun || process.env.HFT_ADOPT_BROKER_LEGS === "false") return;
    const protectedSleeves = loadProtectedSleeves();
    const legs = await broker.listPositions();
    let n = 0;
    for (const leg of legs) {
      const sym = leg.symbol.toUpperCase();
      if (!scopeSet.has(sym)) continue;
      if (protectedSleeves.has(sym)) continue;
      if (leg.side === "short" || leg.qty <= 0) continue;
      if (signals.hasExposure(sym) || mr.hasExposure(sym)) continue;
      const entry = leg.avgEntry && leg.avgEntry > 0 ? leg.avgEntry : 0;
      if (!(entry > 0)) continue;
      const notion = Math.abs(leg.qty) * entry;
      if (hftMaxNotional > 0 && notion > hftMaxNotional * 1.25) continue;
      signals.adoptBrokerLong(sym, Math.abs(leg.qty), entry);
      n += 1;
    }
    if (n > 0) log("adopt-broker-legs", { count: n });
  }

  async function adoptWorkingBuys(): Promise<void> {
    if (CFG.dryRun || process.env.HFT_ADOPT_WORKING_BUYS === "false") return;
    const open = await broker.listOpenOrders();
    let n = 0;
    for (const o of open) {
      if ((o.side ?? "").toLowerCase() !== "buy") continue;
      const sym = (o.symbol ?? "").toUpperCase();
      if (!sym || !scopeSet.has(sym)) continue;
      if (!isHftEntryClientId(o.clientOrderId || "")) continue;
      if (signals.hasExposure(sym) || mr.hasExposure(sym)) continue;
      signals.adoptWorkingBuy(sym);
      mr.adoptWorkingBuy(sym);
      n += 1;
    }
    if (n > 0) log("adopt-working-buys", { count: n });
  }

  async function reconcileOrphanLegs(): Promise<void> {
    // Default: adopt (manage to green), do NOT force-dump — that was a bleed source.
    if (process.env.HFT_FLATTEN_ORPHANS !== "true") {
      await adoptBrokerLegs();
      return;
    }
    if (CFG.dryRun) return;
    const now = Date.now();
    const legs = await broker.listPositions();
    const overnightOwned = loadProtectedSleeves();
    for (const leg of legs) {
      const sym = leg.symbol.toUpperCase();
      if (!scopeSet.has(sym)) continue;
      if (overnightOwned.has(sym)) continue;
      if (leg.side === "short" || leg.qty < 0) continue;
      const entry = leg.avgEntry && leg.avgEntry > 0 ? leg.avgEntry : 0;
      if (entry > 0 && hftMaxNotional > 0 && Math.abs(leg.qty) * entry > hftMaxNotional * 1.25) {
        continue;
      }
      if (mr.hasExposure(sym) || signals.hasExposure(sym)) continue;
      if (await hasOpenOrder(broker, sym, "sell")) continue;
      const last = orphanLastAttempt.get(sym) ?? 0;
      if (now - last < orphanCooldownMs) continue;
      orphanLastAttempt.set(sym, now);
      // Recycle leftover BP: last-wins force-exit closes HFT-sized orphans
      // instead of adopt-filling all 15 IEX slots (that pinned FIRE at ~15/min).
      const forceClose = process.env.HFT_MAX_HOLD_FORCE_EXIT === "true";
      if (!forceClose && leg.avgEntry && leg.avgEntry > 0) {
        signals.adoptBrokerLong(sym, Math.abs(leg.qty), leg.avgEntry);
        log("orphan-adopt", { ticker: sym, qty: leg.qty, entry: leg.avgEntry });
        continue;
      }
      log("orphan-flatten", { ticker: sym, qty: leg.qty });
      const closed = await broker.closePosition(sym, 0, true, leg.qty);
      if (closed.ok) {
        log("orphan-closed", { ticker: sym, qty: leg.qty });
        orphanLastAttempt.delete(sym);
      }
    }
  }

  void broker
    .cancelHftExits()
    .then((n) => {
      if (n > 0) log("cancel-orphan-hft-exits", { canceled: n });
    })
    .then(() => {
      // IOC mode: leftover DAY bids from persist-era block pending.has forever.
      const persistOff =
        process.env.HFT_FILL_PERSIST === "false" || process.env.FILL_PERSIST === "false";
      const wantIoc = (process.env.HFT_LIMIT_TIF || "").toLowerCase() === "ioc";
      if (!persistOff && !wantIoc) return 0;
      return broker.cancelHftEntries().then((n) => {
        if (n > 0) log("cancel-stale-hft-entries", { canceled: n });
        return n;
      });
    })
    .then(() => adoptWorkingBuys())
    .then(() => void reconcileOrphanLegs());
  const orphanTimer = setInterval(() => void reconcileOrphanLegs(), reconcileMs);
  orphanTimer.unref();

  // Flatten HFT-owned scalps before RTH close — never carry noise inventory overnight.
  let lastEodFlattenDay = "";
  async function maybeEodFlattenHft(): Promise<void> {
    if (process.env.HFT_FLATTEN_AT_RTH_CLOSE === "false") return;
    const sess = currentSession();
    if (sess !== "regular") return;
    const fmt = new Intl.DateTimeFormat("en-US", {
      timeZone: "America/New_York",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
    const parts = Object.fromEntries(fmt.formatToParts(new Date()).map((p) => [p.type, p.value]));
    const mins = Number(parts.hour) * 60 + Number(parts.minute);
    const windowStart = Number(process.env.HFT_EOD_FLATTEN_START_MIN ?? 15 * 60 + 35); // 15:35 ET
    if (mins < windowStart || mins >= 16 * 60) return;
    const dayKey = `${parts.year}-${parts.month}-${parts.day}`;
    if (lastEodFlattenDay === dayKey) return;
    lastEodFlattenDay = dayKey;

    let overnightOwned = new Set<string>();
    try {
      const fs = await import("node:fs");
      const path =
        process.env.PORTFOLIO_HEAD_REGISTRY ||
        `${process.env.FATE_ROOT || process.cwd().replace(/\/hft$/, "")}/data/portfolio_head_registry.json`;
      if (fs.existsSync(path)) {
        const doc = JSON.parse(fs.readFileSync(path, "utf8")) as {
          heads?: Record<string, string>;
        };
        for (const [sym, head] of Object.entries(doc.heads || {})) {
          const h = String(head || "").toLowerCase();
          if (h === "fortress" || h === "weekly" || h === "longterm") {
            overnightOwned.add(sym.toUpperCase());
          }
        }
      }
    } catch {
      /* optional */
    }

    const owned = new Set<string>(Array.from(signals.openPositions.keys()).map((t) => t.toUpperCase()));
    for (const t of pollTickers) {
      if (mr.hasExposure(t)) owned.add(t.toUpperCase());
    }
    for (const t of owned) {
      if (overnightOwned.has(t)) continue;
      try {
        log("eod-flatten", { ticker: t });
        await broker.closePosition(t, 0, true);
        signals.openPositions.delete(t);
      } catch (e) {
        log("eod-flatten-err", e instanceof Error ? e.message : String(e));
      }
    }
  }
  const eodTimer = setInterval(() => void maybeEodFlattenHft(), 30_000);
  eodTimer.unref();
  const posMs = Math.max(5_000, Number(process.env.HFT_POSITION_REFRESH_MS ?? 15_000));
  const posTimer = setInterval(() => void broker.keepPositionsWarm(), posMs);
  posTimer.unref();

  log("ready", {
    wsTickers: wsTickers.length,
    restTickers: restOnly.length,
    pollTickers: pollTickers.length,
    dryRun: CFG.dryRun,
    ultra: process.env.HFT_ULTRA_MODE === "true",
    signalMode: resolveSignalMode(),
    ws: wsTickers,
    held: [...held],
    restFeed: process.env.HFT_REST_QUOTE_FEED || "sip",
    minConf: Number(process.env.HFT_MIN_CONFIDENCE ?? CFG.confidence.floor),
    notional: CFG.obi.notional,
    maxNotional: Number(process.env.HFT_MAX_ORDER_NOTIONAL ?? 0),
    bpFrac: Number(process.env.HFT_BP_USE_FRAC ?? 0),
    tif: hftLimitTif(),
    buyLow: process.env.HFT_BUY_LOW,
    aggressive: process.env.HFT_AGGRESSIVE_ENTRY,
    maxOrdersPerSec: Number(process.env.HFT_MAX_ORDERS_PER_SEC ?? 0),
    maxOrdersPerMin: CFG.maxOrdersPerMin,
  });
}

void main().catch((e) => {
  console.error("[OBI] fatal", e);
  process.exit(1);
});

process.on("uncaughtException", (e) => {
  console.error("[OBI] uncaught", e);
  process.exit(1);
});
process.on("unhandledRejection", (e) => {
  console.error("[OBI] unhandledRejection", e);
  process.exit(1);
});
