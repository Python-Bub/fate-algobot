/**
 * Centralised env-driven config. Loaded once at process start.  Re-reading
 * `process.env` on the hot path would tank perf, so we copy everything we need
 * into plain numbers/strings up front.
 */
import { config as loadDotenv } from "dotenv";
import { existsSync, readFileSync } from "node:fs";
import { hostname as osHostname } from "node:os";
import { resolve } from "node:path";
import { hftConfidenceFloorDelta } from "./overlay-runtime.js";

const candidates = [resolve(process.cwd(), ".env"), resolve(process.cwd(), "../.env")];
for (const p of candidates) {
  if (existsSync(p)) loadDotenv({ path: p, override: false });
}
loadDotenv();
// deploy_scale.env last-wins (200/min, DAY TIF, no cancel-unfilled) even if node
// was started without run_all.sh sourcing it.
for (const p of [
  resolve(process.cwd(), "data/deploy_scale.env"),
  resolve(process.cwd(), "../data/deploy_scale.env"),
]) {
  if (existsSync(p)) loadDotenv({ path: p, override: true });
}

function str(name: string, fallback: string): string {
  const v = process.env[name];
  return v == null || v === "" ? fallback : v;
}
function strFirst(names: string[], fallback: string): string {
  for (const n of names) {
    const v = process.env[n];
    if (v != null && v !== "") return v;
  }
  return fallback;
}
function num(name: string, fallback: number): number {
  const v = process.env[name];
  if (v == null || v === "") return fallback;
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}
function bool(name: string, fallback: boolean): boolean {
  const v = process.env[name];
  if (v == null || v === "") return fallback;
  return ["1", "true", "yes", "y", "on"].includes(v.toLowerCase());
}

/** Laptop/trainer must not POST the same Alpaca paper account as the GCP paper VM. */
function _orderRoleDryRun(): boolean {
  const hn = (process.env.HOSTNAME || process.env.HOST || osHostname() || "").toLowerCase();
  if (hn.includes("algobot-paper")) return false;
  if (hn.includes("algobot-trainer")) return true;
  const allowLocal = ["1", "true", "yes"].includes(
    (process.env.FATE_ALLOW_LOCAL_ORDERS || "").toLowerCase(),
  );
  if (allowLocal) {
    const role = (process.env.FATE_ORDER_ROLE || "").trim().toLowerCase();
    if (role === "gcp-paper" || role === "order" || role === "paper-vm") return false;
  }
  return true;
}
function csv(name: string, fallback: string[]): string[] {
  const v = process.env[name];
  if (v == null || v === "") return fallback;
  return v.split(",").map((s) => s.trim().toUpperCase()).filter(Boolean);
}

function tickersFromFile(path: string): string[] {
  if (!path || !existsSync(path)) return [];
  try {
    return readFileSync(path, "utf8")
      .split(/[\s,]+/)
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean);
  } catch {
    return [];
  }
}

function uniqueTickers(...lists: string[][]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const list of lists) {
    for (const t of list) {
      if (!t || seen.has(t)) continue;
      seen.add(t);
      out.push(t);
    }
  }
  return out;
}

const restTickerFiles = [
  str("HFT_REST_TICKERS_FILE", ""),
  resolve(process.cwd(), "data/ops/hft_rest_tickers.txt"),
  resolve(process.cwd(), "../data/ops/hft_rest_tickers.txt"),
].filter(Boolean);

/** Pull the alpaca origin even when ALPACA_BASE_URL accidentally includes /v2. */
function alpacaOrigin(): string {
  const raw = strFirst(["ALPACA_BASE_URL"], "https://paper-api.alpaca.markets");
  try {
    return new URL(raw).origin;
  } catch {
    return "https://paper-api.alpaca.markets";
  }
}

export const CFG = {
  // --- broker ---
  alpaca: {
    key: strFirst(["ALPACA_API_KEY", "ALPACA_KEY_ID"], ""),
    // The Python side names it ALPACA_SECRET_KEY; some Alpaca SDKs use ALPACA_API_SECRET.
    // Accept either to avoid mismatch between hft/ and the rest of the project.
    secret: strFirst(["ALPACA_API_SECRET", "ALPACA_SECRET_KEY"], ""),
    baseUrl: alpacaOrigin(),
    dataBase: strFirst(["ALPACA_DATA_BASE", "ALPACA_DATA_URL"], "https://data.alpaca.markets"),
    dataStream: str("ALPACA_DATA_STREAM", "wss://stream.data.alpaca.markets/v2/iex"),
  },
  polygon: {
    // Polygon.io (now branded "Massive") REST endpoint for news + delayed bars.
    // WebSocket streaming requires the *paid* tier; the Starter plan returns
    // `auth_failed` on the WS handshake, so we route streaming through Alpaca
    // by default and use Polygon for REST-side news lookups.
    key: str("POLYGON_API_KEY", ""),
    restBase: str("POLYGON_REST_BASE", "https://api.polygon.io"),
    stocksStream: str("POLYGON_STOCKS_STREAM", "wss://socket.polygon.io/stocks"),
    newsStream: str("POLYGON_NEWS_STREAM", "wss://socket.polygon.io/stocks"),
    useLevel2: bool("POLYGON_USE_LEVEL2", false),
    useWebsocket: bool("POLYGON_USE_WEBSOCKET", false), // flip true once on a paid plan
  },
  benzinga: {
    // Optional / disabled by default — premium news wire. Polygon news fills the gap.
    key: str("BENZINGA_API_KEY", ""),
    newsStream: str("BENZINGA_NEWS_STREAM", "wss://api.benzinga.com/api/v1/news/stream"),
  },
  // --- safety ---
  dryRun: bool("HFT_DRY_RUN", true) || _orderRoleDryRun(),
  globalKill: bool("HFT_GLOBAL_KILL", false),
  maxOrdersPerMin: num("HFT_MAX_ORDERS_PER_MIN", 200),
  cooldownMs: num("HFT_PER_TICKER_COOLDOWN_MS", 8_000),
  tickSize: num("TICK_SIZE", 0.01),
  // --- confidence-scaled sizing (shared by both algos) ---
  confidence: {
    floor: num("HFT_MIN_CONFIDENCE", 0.65),
    maxNotionalMult: num("HFT_MAX_NOTIONAL_MULT", 3.0),
  },
  // --- earnings ---
  earn: {
    tickers: csv("EARN_TICKER_WHITELIST", ["AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA", "AMD", "AVGO", "COST", "LLY", "JPM", "V", "MA"]),
    triggerPct: num("EARN_SURPRISE_PCT_TRIGGER", 5.0),
    notional: num("EARN_NOTIONAL_USD", 2500),
    tickOffset: num("EARN_LIMIT_TICK_OFFSET", 2),
    budgetMs: num("EARN_BUDGET_LATENCY_MS", 100),
    vwapWindowMs: num("EARN_VWAP_WINDOW_MS", 10_000),
    fillDeadlineMs: num("EARN_FILL_DEADLINE_MS", 400),
    // Default true: never open a second Alpaca IEX WS (OBI owns it). News+NBBO via REST.
    coexistWithObi: bool("EARNINGS_COEXIST_WITH_OBI", true),
  },
  // --- coexistence / rotator ---
  hftCoexist: bool("HFT_COEXIST", true),
  obi: {
    tickers: csv("OBI_TICKER_WHITELIST", ["NVDA", "AMD", "TSLA", "MSFT", "NFLX", "AMZN", "AAPL", "META", "GOOGL", "SBUX", "BX", "AVGO"]),
    restTickers: uniqueTickers(
      csv("HFT_REST_TICKERS", []),
      ...restTickerFiles.map((p) => tickersFromFile(p)),
    ),
    triggerLong: num("OBI_TRIGGER_LONG", 0.75),
    triggerShort: num("OBI_TRIGGER_SHORT", -0.75),
    tapeWindowMs: num("TAPE_VELOCITY_WINDOW_MS", 100),
    baselineWindowMs: num("TAPE_BASELINE_WINDOW_MS", 5000),
    velocityMult: num("TAPE_VELOCITY_MULTIPLIER", 5.0),
    notional: num("OBI_NOTIONAL_USD", 1000),
    microStopTicks: num("OBI_MICRO_STOP_TICKS", 3),
    budgetMs: num("OBI_BUDGET_LATENCY_MS", 10),
  },
};

/**
 * Map a raw signal strength in [0,1] to a notional-multiplier, gated by the
 * `HFT_MIN_CONFIDENCE` floor.  Returns 0 when below the floor (don't trade).
 *
 *   conf < floor          → 0           (skip)
 *   conf == floor         → 1.0 × base
 *   conf == 1.0           → maxMult × base
 *   in between            → linear
 */
export function effectiveConfidenceFloor(): number {
  return Math.max(0.35, Math.min(0.95, CFG.confidence.floor + hftConfidenceFloorDelta()));
}

export function confidenceNotionalMult(confidence: number): number {
  const floor = effectiveConfidenceFloor();
  const maxM = CFG.confidence.maxNotionalMult;
  if (!Number.isFinite(confidence) || confidence < floor) return 0;
  const span = Math.max(1e-6, 1 - floor);
  const t = Math.min(1, (confidence - floor) / span);
  return 1 + (maxM - 1) * t;
}

export type Config = typeof CFG;
