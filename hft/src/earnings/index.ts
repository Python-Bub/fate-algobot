/**
 * Earnings sub-second HFT main entry point.
 *
 *   npm run earnings           # standard run (uses default V8 flags from package.json)
 *   npm run earnings:perf      # adds GC-quieting flags for maximum wire-speed
 *
 * Topology:
 *
 *   Newswire WS ─┐
 *                ├─► EarningsIngestor (Phase 1: prefilter, hrtime stamp)
 *   MarketData WS┘
 *                                                │
 *                                                ▼
 *                                EarningsEvaluator (Phase 2: surprise math,
 *                                                       VWAP guard, sizing)
 *                                                │
 *                                                ▼
 *                                  EarningsExecutor (Phase 3: IOC limit @
 *                                                       NBBO+ticks, circuit-
 *                                                       breakers)
 *                                                │
 *                                                ▼
 *                                  PostTradeAccountant (Phase 4: async log,
 *                                                       slippage, locks)
 *
 * Hot path runs on the single Node event loop. No Worker Threads — they only
 * help with CPU-bound work and we are network+memory bound.
 */
import { AlpacaExecutor } from "../common/alpaca-exec.js";
import { CFG } from "../common/config.js";
import { KillSwitch } from "../common/kill-switch.js";
import { stdoutTag } from "../common/logger.js";

import { EarningsIngestor, type EarningsFrame } from "./earnings-ingestor.js";
import { EarningsEvaluator } from "./earnings-evaluator.js";
import { EarningsExecutor } from "./earnings-executor.js";
import { PostTradeAccountant } from "./post-trade.js";
import { EarningsRestFeed } from "./rest-market-feed.js";

const log = stdoutTag("[EARN]");

async function main(): Promise<void> {
  if (CFG.globalKill) {
    log("HFT_GLOBAL_KILL=true — refusing to start.");
    process.exit(2);
  }
  if (!CFG.alpaca.key || !CFG.alpaca.secret) {
    log("WARNING: ALPACA_API_KEY/SECRET missing. Set HFT_DRY_RUN=true for paper rehearsal.");
  }

  const tickers = CFG.earn.tickers;
  const broker = new AlpacaExecutor(CFG.alpaca.baseUrl, CFG.alpaca.key, CFG.alpaca.secret, CFG.dryRun);
  const kill = new KillSwitch(tickers, CFG.cooldownMs, CFG.maxOrdersPerMin);
  const evaluator = new EarningsEvaluator(tickers);
  const executor = new EarningsExecutor(broker, kill);
  const accountant = new PostTradeAccountant(kill, /* lockForever */ true);

  const onFrame = (frame: EarningsFrame) => {
    try {
      const trig = evaluator.evaluate(frame);
      if (!trig) return;
      void executor.fire(trig).then((resp) => {
        if (!resp || !resp.ok) return;
        const fillPx =
          resp.filledAvgPrice != null && resp.filledAvgPrice > 0
            ? resp.filledAvgPrice
            : trig.limitPx;
        accountant.recordFill({
          ticker: trig.ticker,
          side: trig.side,
          limitPx: trig.limitPx,
          fillPx,
          qty: trig.qty,
          ingestToFireMs: resp.ingestToFireMs,
          wireMs: resp.wireMs,
          feeUsd: 0,
        });
      });
    } catch (err) {
      log("hot-path-error", err instanceof Error ? err.message : err);
    }
  };

  const ingestor = new EarningsIngestor({ tickers, onFrame });
  let restFeed: EarningsRestFeed | null = null;

  const useRest =
    CFG.earn.coexistWithObi ||
    CFG.hftCoexist ||
    (ingestor.usesAlpacaWebsocket() && !CFG.benzinga.key && !(CFG.polygon.key && CFG.polygon.useWebsocket));

  if (useRest && ingestor.usesAlpacaWebsocket()) {
    restFeed = new EarningsRestFeed(tickers, evaluator, onFrame);
    restFeed.start();
    log("mode", { feed: "rest-coexist", note: "Alpaca WS left for OBI" });
  } else {
    ingestor.start();
    log("mode", { feed: "websocket", coexist: false });
  }

  // Periodic stats dump (every 30s) — never on hot path.
  const statsTimer = setInterval(() => {
    log("stats", {
      ingest: ingestor.stats(),
      placeUs: broker.placeHist.snapshot(),
      rest: Boolean(restFeed),
    });
  }, 30_000);
  // Do not unref — REST coexist has no Alpaca WS; unref'd timers let Node exit.

  const shutdown = async (sig: string): Promise<void> => {
    log("shutdown", { sig });
    clearInterval(statsTimer);
    restFeed?.stop();
    ingestor.stop();
    await broker.close();
    process.exit(0);
  };
  process.on("SIGINT", () => void shutdown("SIGINT"));
  process.on("SIGTERM", () => void shutdown("SIGTERM"));

  log("ready", { tickers: tickers.length, dryRun: CFG.dryRun, restCoexist: Boolean(restFeed) });
}

void main().catch((e) => {
  console.error("[EARN] fatal", e);
  process.exit(1);
});

process.on("uncaughtException", (e) => {
  console.error("[EARN] uncaught", e);
  process.exit(1);
});
process.on("unhandledRejection", (e) => {
  console.error("[EARN] unhandledRejection", e);
  process.exit(1);
});
