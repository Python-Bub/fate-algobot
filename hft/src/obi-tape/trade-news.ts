/**
 * Trade-news gate from data/intel/hft_trade_news.json — allow_long + sizing tilt only.
 */
import fs from "node:fs";
import path from "node:path";

import { stdoutTag } from "../common/logger.js";

const log = stdoutTag("[NEWS]");

interface TradeNewsRow {
  allow_long?: boolean;
  tilt?: number;
  intensity?: number;
  good?: number;
  bad?: number;
  verdict?: string;
  headline?: string;
}

interface TradeNewsFile {
  tickers?: Record<string, TradeNewsRow>;
  updated_ms?: number;
}

let cache: { mtimeMs: number; data: TradeNewsFile } | null = null;
const blockLogAt = new Map<string, number>();

function newsPath(): string {
  return (
    process.env.HFT_TRADE_NEWS_PATH ??
    path.join(process.cwd(), "..", "data", "intel", "hft_trade_news.json")
  );
}

function load(): TradeNewsFile {
  const p = newsPath();
  try {
    const st = fs.statSync(p);
    if (cache && cache.mtimeMs === st.mtimeMs) return cache.data;
    const data = JSON.parse(fs.readFileSync(p, "utf8")) as TradeNewsFile;
    cache = { mtimeMs: st.mtimeMs, data };
    return data;
  } catch {
    return {};
  }
}

function row(ticker: string): TradeNewsRow | undefined {
  return load().tickers?.[ticker.toUpperCase()];
}

export function tradeNewsAllowsLong(ticker: string): boolean {
  if (process.env.HFT_NEWS_GATE === "false") return true;
  const r = row(ticker);
  if (!r) return true;
  return r.allow_long !== false;
}

export function tradeNewsSizingTilt(ticker: string): number {
  if (process.env.HFT_NEWS_GATE === "false") return 1;
  if (!tradeNewsAllowsLong(ticker)) return 0;
  const t = row(ticker)?.tilt;
  if (typeof t !== "number" || !Number.isFinite(t)) return 1;
  return 1 + t;
}

export function tradeNewsHeadline(ticker: string): string | null {
  const h = row(ticker)?.headline?.trim();
  return h ? h.slice(0, 120) : null;
}

export function tradeNewsLogFields(ticker: string): Record<string, unknown> | null {
  const r = row(ticker);
  if (!r) return null;
  return {
    allow_long: tradeNewsAllowsLong(ticker),
    news_tilt: tradeNewsSizingTilt(ticker),
    intensity: r.intensity,
    good: r.good,
    bad: r.bad,
    verdict: r.verdict,
  };
}

export function tradeNewsSentiment(ticker: string): number | undefined {
  const r = row(ticker);
  if (!r) return undefined;
  if (typeof r.intensity === "number" && Number.isFinite(r.intensity)) {
    return Math.max(-1, Math.min(1, r.intensity));
  }
  if (typeof r.tilt === "number" && Number.isFinite(r.tilt)) {
    return Math.max(-1, Math.min(1, r.tilt));
  }
  return undefined;
}

export function logTradeNewsBlock(ticker: string): void {
  const t = ticker.toUpperCase();
  const now = Date.now();
  if (now - (blockLogAt.get(t) ?? 0) < 60_000) return;
  blockLogAt.set(t, now);
  log("block-long", { ticker: t, ...tradeNewsLogFields(t), headline: tradeNewsHeadline(t) });
}
