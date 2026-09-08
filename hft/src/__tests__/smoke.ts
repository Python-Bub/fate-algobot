/**
 * Minimal self-test that exercises every hot-path module without requiring
 * a live broker or websocket.  Run with `npm run test` (added below).
 */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { CircularF64, TimeWindowCounter, VwapRing } from "../common/buffers.js";
import { LatencyHistogram, nowNs } from "../common/latency.js";
import { TickerPrefilter } from "../common/prefilter.js";
import { issuerCachedLongQty, issuerGroup, issuerSiblings, skipBuyAlreadyLong } from "../common/issuer-siblings.js";
import { KillSwitch } from "../common/kill-switch.js";
import { currentSession, fillPersistEnabled, hftExitTif, hftExtendedHoursFlag, hftLimitTif, mayCancelUnfilled } from "../common/market-session.js";
import {
  OPEN_ORDER_STATUSES,
  TERMINAL_ORDER_STATUSES,
  filledShareQty,
  interpretFillSnapshot,
  isHftEntryClientId,
  isHftExitClientId,
  orderFilledQty,
  shouldReleasePending,
} from "../common/order-lifecycle.js";
import { CircuitBreaker } from "../common/circuit-breaker.js";
import { L2Book, L2_LEVELS } from "../obi-tape/l2-book.js";
import {
  bestLevelObi,
  microPrice,
  microPriceDriftBps,
  flowIsSellToxic,
  microPriceSupportsLong,
} from "../obi-tape/micro-price.js";
import { TapeVelocity } from "../obi-tape/tape-velocity.js";
import { CFG, confidenceNotionalMult, effectiveConfidenceFloor } from "../common/config.js";
import { CandleBuilder, PAT_HAMMER, PAT_BULLISH_ENGULF, PAT_DOJI, PAT_SHOOTING_STAR } from "../obi-tape/jp-candles.js";
import { AdvancedChartEngine, fuseVotes, lineVote, PointAndFigure } from "../obi-tape/advanced-charts.js";
import { upwardProbability, type MicroInputs } from "../obi-tape/microstructure-prob.js";
import {
  chargedSpreadBps,
  entryLimitPx,
  exitLimitPx,
  exitProfitable,
  flattenQuoteOk,
  spreadBps,
  spreadOk,
  spreadOkForSession,
  sellLimitUnfillable,
  completeNbbo,
} from "../obi-tape/order-pricing.js";
import { assessQuoteHealth } from "../obi-tape/quote-health.js";
import { AlpacaExecutor } from "../common/alpaca-exec.js";
import { execDelayFeeBps, effectiveBudgetMs, loadExecDelayMs } from "../obi-tape/exec-delay.js";

import { fuseObiMicro, fuseObiTape, expectedBps, shouldEnterEv } from "../obi-tape/trade-ev.js";
import { plumbingHitsTarget, rollingCount, tpmTarget } from "../obi-tape/pace-governor.js";
import { clipNotional, combinedHaircut, inventoryHaircut, lagHaircut, sizeHftClip } from "../obi-tape/firm-risk.js";
import { canEnterBuy, resolveHftNotionalUsd, __setMarginCacheForTest } from "../common/margin-guard.js";
import { resolveSignalMode, wantsDirection } from "../obi-tape/signal-mode.js";
import { pickWsTickers } from "../obi-tape/pick-ws.js";

let failed = 0;
function ok(name: string, fn: () => void): void {
  try {
    fn();
    console.log("ok  -", name);
  } catch (err) {
    failed++;
    console.error("FAIL -", name, err);
  }
}

ok("CircularF64 sum/mean is correct over wrap", () => {
  const r = new CircularF64(3);
  r.push(1);
  r.push(2);
  r.push(3);
  assert.equal(r.sum(), 6);
  r.push(4); // evict 1
  assert.equal(r.sum(), 9);
  assert.equal(r.mean(), 3);
});

ok("TimeWindowCounter counts only inside window", () => {
  const c = new TimeWindowCounter(16, 100);
  c.bump(1000);
  c.bump(1050);
  c.bump(1095);
  assert.equal(c.count(1100), 3);
  c.bump(1200);
  // The 1200 bump is the only one inside the last 100 ms window.
  assert.equal(c.count(1200), 1);
});

ok("VwapRing weighted average is correct", () => {
  const v = new VwapRing(8, 1000);
  v.add(0, 100, 10);
  v.add(50, 110, 30);
  // VWAP = (100*10 + 110*30) / 40 = (1000+3300)/40 = 107.5
  assert.equal(v.vwap(), 107.5);
});

ok("TickerPrefilter ignores non-watched", () => {
  const pf = new TickerPrefilter(["AAPL", "NVDA"]);
  const buf = Buffer.from('{"sym":"MSFT","p":410.5}');
  assert.equal(pf.match(buf), null);
  const buf2 = Buffer.from('{"sym":"AAPL","p":200}');
  assert.equal(pf.match(buf2), "AAPL");
});

ok("KillSwitch locks per ticker and respects cooldown", () => {
  const k = new KillSwitch(["AAPL"], 100, 5);
  assert.equal(k.isLocked("AAPL", 1000), false);
  k.lock("AAPL", 1000);
  assert.equal(k.isLocked("AAPL", 1099), true);
  assert.equal(k.isLocked("AAPL", 1101), false);
});

ok("KillSwitch enforces per-minute order cap", () => {
  process.env.HFT_GLOBAL_MAX_ORDERS_PER_MIN = "0";
  process.env.HFT_MAX_ORDERS_PER_SEC = "0";
  const k = new KillSwitch(["AAPL"], 0, 2);
  assert.equal(k.reserveOrderSlot(0), true);
  assert.equal(k.reserveOrderSlot(0), true);
  assert.equal(k.reserveOrderSlot(0), false); // cap = 2
  assert.equal(k.reserveOrderSlot(61_000), true); // rolling 60s elapsed
});

ok("KillSwitch rolling 60s does not reset at calendar minute", () => {
  process.env.HFT_GLOBAL_MAX_ORDERS_PER_MIN = "0";
  process.env.HFT_MAX_ORDERS_PER_SEC = "0";
  const k = new KillSwitch(["AAPL"], 0, 2);
  assert.equal(k.reserveOrderSlot(59_000), true);
  assert.equal(k.reserveOrderSlot(59_500), true);
  // :00 clock wall — first submit is still inside the rolling 60s window.
  assert.equal(k.reserveOrderSlot(61_000), false);
  assert.equal(k.reserveOrderSlot(119_001), true);
});

ok("KillSwitch allows 200 submits inside a rolling minute", () => {
  process.env.HFT_GLOBAL_MAX_ORDERS_PER_MIN = "0";
  process.env.HFT_MAX_ORDERS_PER_SEC = "0";
  const k = new KillSwitch(["AAPL"], 0, 200);
  for (let i = 0; i < 200; i++) {
    assert.equal(k.reserveOrderSlot(i), true, `slot ${i}`);
  }
  assert.equal(k.reserveOrderSlot(199), false);
  assert.equal(k.reserveOrderSlot(60_001), true);
});

ok("GOOG and GOOGL are the same issuer", () => {
  assert.equal(issuerGroup("GOOG"), "GOOGL");
  assert.ok(issuerSiblings("GOOG").includes("GOOGL"));
  assert.ok(issuerSiblings("GOOGL").includes("GOOG"));
  const qty = issuerCachedLongQty((s) => (s === "GOOGL" ? 14 : 0), "GOOG");
  assert.equal(qty, 14);
  assert.equal(skipBuyAlreadyLong(14, 0), true);
  assert.equal(skipBuyAlreadyLong(0, 0), false);
  assert.equal(skipBuyAlreadyLong(Number.NaN, 0), true);
});

ok("partial position snapshot does not fake-flat other longs", () => {
  const ex = new AlpacaExecutor("http://127.0.0.1", "k", "s", false);
  ex.applyPositionSnapshot(
    new Map([
      ["KO", 82],
      ["WMT", 26],
      ["XOM", 30],
    ]),
  );
  assert.equal(ex.cachedLongQty("KO"), 82);
  ex.applyPositionSnapshot(new Map([["WMT", 26]]));
  assert.equal(ex.cachedLongQty("KO"), 82);
  assert.equal(ex.cachedLongQty("WMT"), 26);
  assert.ok(ex.heldSymbols().includes("KO"));
  ex.applyPositionSnapshot(new Map());
  assert.equal(ex.cachedLongQty("KO"), 82);
});

ok("RTH entry TIF follows HFT_LIMIT_TIF; exits stay DAY", () => {
  process.env.HFT_FILL_PERSIST = "false";
  process.env.HFT_LIMIT_TIF = "ioc";
  process.env.HFT_EXIT_TIF = "day";
  process.env.HFT_EXTENDED_HOURS = "true";
  const sess = currentSession();
  if (sess === "regular") {
    assert.equal(hftLimitTif(), "ioc");
    assert.equal(hftExtendedHoursFlag(), false);
  } else {
    assert.equal(hftLimitTif(), "day");
  }
  assert.equal(hftExitTif(), "day");
  process.env.HFT_EXIT_TIF = "ioc";
  assert.equal(hftExitTif(), "ioc");
  process.env.HFT_EXIT_TIF = "day";
});

ok("fill persist forces DAY and refuses cancel-unfilled", () => {
  process.env.HFT_FILL_PERSIST = "true";
  process.env.HFT_LIMIT_TIF = "ioc";
  assert.equal(fillPersistEnabled(), true);
  assert.equal(hftLimitTif(), "day");
  assert.equal(mayCancelUnfilled(true), false);
  process.env.HFT_FILL_PERSIST = "false";
  process.env.HFT_LIMIT_TIF = "ioc";
  assert.equal(mayCancelUnfilled(true), true);
  process.env.HFT_LIMIT_TIF = "day";
  assert.equal(mayCancelUnfilled(true), false);
  process.env.HFT_FILL_PERSIST = "true";
});

ok("RTH spread cap is tight; charged spread is capped for edge gate", () => {
  const b = new L2Book("MSFT");
  b.applySnapshot([[393.02, 100]], [[435.08, 100]], Date.now());
  assert.ok(spreadBps(b) > 500);
  assert.equal(spreadOk(b), false);
  assert.equal(spreadOkForSession(b, "regular"), false);
  assert.equal(flattenQuoteOk(b), false);
  process.env.HFT_EDGE_SPREAD_CAP_BPS = "12";
  assert.equal(chargedSpreadBps(b), 12);
  const tight = new L2Book("KO");
  tight.applySnapshot([[70.00, 100]], [[70.02, 100]], Date.now());
  assert.ok(spreadOkForSession(tight, "regular"));
  assert.ok(flattenQuoteOk(tight));
  assert.ok(chargedSpreadBps(tight) < 12);
});

ok("185/min buffer leaves headroom under 200 cap", () => {
  process.env.HFT_GLOBAL_MAX_ORDERS_PER_MIN = "0";
  process.env.HFT_MAX_ORDERS_PER_SEC = "0";
  const cap = 185;
  const k = new KillSwitch(["AAPL"], 0, cap);
  for (let i = 0; i < cap; i++) {
    assert.equal(k.reserveOrderSlot(i), true, `slot ${i}`);
  }
  assert.equal(k.reserveOrderSlot(cap - 1), false);
});

ok("L2Book OBI is +1 with all bid liquidity and -1 with all ask", () => {
  const b = new L2Book("SPY");
  const bidsHeavy: [number, number][] = Array.from({ length: L2_LEVELS }, (_, i) => [500 - i, 1000]);
  const asksHeavy: [number, number][] = Array.from({ length: L2_LEVELS }, (_, i) => [501 + i, 0]);
  b.applySnapshot(bidsHeavy, asksHeavy, Date.now());
  assert.equal(b.obi, 1);
  b.applySnapshot(asksHeavy.map(([p]) => [p, 0] as [number, number]), bidsHeavy.map(([p, s]) => [p, s] as [number, number]), Date.now());
  // Now all qty is on the ask side → OBI = -1
  assert.equal(b.obi, -1);
});

ok("TapeVelocity burst ratio matches expected", () => {
  const prevCap = process.env.HFT_TAPE_BURST_CAP;
  const prevBase = process.env.HFT_TAPE_MIN_BASELINE;
  const prevFast = process.env.HFT_TAPE_MIN_FAST;
  process.env.HFT_TAPE_BURST_CAP = "8";
  process.env.HFT_TAPE_MIN_BASELINE = "10";
  process.env.HFT_TAPE_MIN_FAST = "2";
  const t = new TapeVelocity("AAPL", 100, 1000);
  // 20 trades in last 100 ms vs 20 over 1000 ms = burst ratio 10x, capped at 8.
  for (let i = 0; i < 20; i++) t.onTrade(2000, 100, 100);
  assert.equal(t.lastBurstRatio, 8);
  if (prevCap === undefined) delete process.env.HFT_TAPE_BURST_CAP;
  else process.env.HFT_TAPE_BURST_CAP = prevCap;
  if (prevBase === undefined) delete process.env.HFT_TAPE_MIN_BASELINE;
  else process.env.HFT_TAPE_MIN_BASELINE = prevBase;
  if (prevFast === undefined) delete process.env.HFT_TAPE_MIN_FAST;
  else process.env.HFT_TAPE_MIN_FAST = prevFast;
});

ok("TapeVelocity ignores a lone print on a quiet baseline", () => {
  const prevBase = process.env.HFT_TAPE_MIN_BASELINE;
  const prevFast = process.env.HFT_TAPE_MIN_FAST;
  process.env.HFT_TAPE_MIN_BASELINE = "10";
  process.env.HFT_TAPE_MIN_FAST = "2";
  const t = new TapeVelocity("AAPL", 100, 5000);
  t.onTrade(2000, 100, 100);
  assert.equal(t.lastBurstRatio, 0);
  if (prevBase === undefined) delete process.env.HFT_TAPE_MIN_BASELINE;
  else process.env.HFT_TAPE_MIN_BASELINE = prevBase;
  if (prevFast === undefined) delete process.env.HFT_TAPE_MIN_FAST;
  else process.env.HFT_TAPE_MIN_FAST = prevFast;
});

ok("LatencyHistogram percentiles non-zero", () => {
  const h = new LatencyHistogram(128, "smoke");
  for (let i = 1; i <= 100; i++) h.recordNs(BigInt(i * 1000)); // 1µs to 100µs
  const s = h.snapshot();
  assert.ok(s.p50 > 0 && s.p95 > s.p50 && s.p99 >= s.p95);
});

ok("hrtime monotonic", () => {
  const a = nowNs();
  const b = nowNs();
  assert.ok(b >= a);
});

ok("confidence floor blocks below floor and scales above", () => {
  const floor = effectiveConfidenceFloor();
  const maxM = CFG.confidence.maxNotionalMult;
  assert.equal(confidenceNotionalMult(floor - 0.01), 0);
  assert.equal(confidenceNotionalMult(floor - 0.1), 0);
  assert.ok(Math.abs(confidenceNotionalMult(floor) - 1.0) < 1e-6);
  assert.ok(Math.abs(confidenceNotionalMult(1.0) - maxM) < 1e-6);
  const midConf = (floor + 1) / 2;
  const mid = confidenceNotionalMult(midConf);
  const expectedMid = 1 + (maxM - 1) * ((midConf - floor) / Math.max(1e-6, 1 - floor));
  assert.ok(Math.abs(mid - expectedMid) < 1e-6, `mid=${mid} expected=${expectedMid}`);
});

ok("Candle DOJI: tiny body", () => {
  const cb = new CandleBuilder("X", 1000, 10);
  // First trade opens bar at t=0.
  cb.onTrade(0, 100.00, 100);
  // More trades inside the bar: tight close to open, equal up/down range.
  cb.onTrade(200, 100.50, 100);
  cb.onTrade(400, 99.50, 100);
  cb.onTrade(600, 100.00, 100);
  // Next bar closes the previous one.
  cb.onTrade(1100, 100.00, 100);
  assert.equal(cb.lastPattern, PAT_DOJI);
});

ok("Candle HAMMER after downtrend", () => {
  const cb = new CandleBuilder("X", 1000, 30);
  // 6 downtrending bars
  for (let i = 0; i < 7; i++) {
    cb.onTrade(i * 1000 + 100, 100 - i, 100);
    cb.onTrade(i * 1000 + 900, 99.5 - i, 100);
  }
  // Hammer bar: long lower shadow, small green body up at the top.
  cb.onTrade(7 * 1000 + 100, 93.0, 100); // open
  cb.onTrade(7 * 1000 + 200, 90.5, 100); // wick down
  cb.onTrade(7 * 1000 + 900, 93.2, 100); // close back up
  cb.onTrade(8 * 1000 + 100, 93.5, 100); // close prev bar
  assert.equal(cb.lastPattern, PAT_HAMMER);
});

ok("Candle SHOOTING_STAR after uptrend", () => {
  const cb = new CandleBuilder("X", 1000, 30);
  for (let i = 0; i < 7; i++) {
    cb.onTrade(i * 1000 + 100, 100 + i, 100);
    cb.onTrade(i * 1000 + 900, 100.5 + i, 100);
  }
  // Shooting star: long upper shadow, small red body near low.
  cb.onTrade(7 * 1000 + 100, 107.0, 100);
  cb.onTrade(7 * 1000 + 200, 109.5, 100);   // wick up
  cb.onTrade(7 * 1000 + 900, 106.8, 100);
  cb.onTrade(8 * 1000 + 100, 106.5, 100);
  assert.equal(cb.lastPattern, PAT_SHOOTING_STAR);
});

ok("Candle BULLISH_ENGULF wraps the prior bar", () => {
  const cb = new CandleBuilder("X", 1000, 20);
  // Prior bar bearish: open 100, close 98, range 97-100
  cb.onTrade(100, 100.00, 100);
  cb.onTrade(900, 98.00, 100);
  // Current bar bullish that engulfs: open 97.5, close 100.5
  cb.onTrade(1100, 97.5, 100);
  cb.onTrade(1900, 100.5, 100);
  cb.onTrade(2100, 100.0, 100); // close current
  assert.equal(cb.lastPattern, PAT_BULLISH_ENGULF);
});

ok("spreadOk rejects wide extended-hours quotes", () => {
  const b = new L2Book("MSFT");
  b.applySnapshot([[393.02, 100]], [[435.08, 100]], Date.now());
  assert.ok(spreadBps(b) > 500);
  assert.equal(spreadOk(b), false);
});

ok("entryLimitPx caps buy away from distant ask", () => {
  const prevBuy = process.env.HFT_BUY_LOW;
  const prevAgg = process.env.HFT_AGGRESSIVE_ENTRY;
  process.env.HFT_BUY_LOW = "true";
  process.env.HFT_AGGRESSIVE_ENTRY = "false";
  const b = new L2Book("MSFT");
  b.applySnapshot([[393.02, 100]], [[435.09, 100]], Date.now());
  const px = entryLimitPx("buy", b);
  assert.ok(px != null);
  assert.ok(px! < 435.09);
  assert.ok(px! <= 395);
  if (prevBuy === undefined) delete process.env.HFT_BUY_LOW;
  else process.env.HFT_BUY_LOW = prevBuy;
  if (prevAgg === undefined) delete process.env.HFT_AGGRESSIVE_ENTRY;
  else process.env.HFT_AGGRESSIVE_ENTRY = prevAgg;
});

ok("exitProfitable blocks sell below entry", () => {
  const b = new L2Book("TSLA");
  b.applySnapshot([[408.5, 100]], [[408.7, 100]], Date.now());
  assert.equal(exitProfitable("buy", 410.96, b), false);
  b.applySnapshot([[411.25, 100]], [[411.45, 100]], Date.now());
  assert.equal(exitProfitable("buy", 410.96, b), true);
});

ok("exitLimitPx sell high — never below entry+edge unless forced", () => {
  const b = new L2Book("MSFT");
  b.applySnapshot([[410.71, 100]], [[410.95, 100]], Date.now());
  const px = exitLimitPx("sell", b, 409.5);
  assert.ok(px >= 409.62, `exit px ${px} should be >= entry+min edge`);
  assert.ok(px <= 410.95, `exit px ${px} must not sit above the ask`);
  const loss = exitLimitPx("sell", b, 409.5, true);
  assert.ok(loss < 411, `forced exit ${loss} may cross at bid`);
});

ok("exitLimitPx underwater rest at/above entry — wait for green", () => {
  const b = new L2Book("TSLA");
  b.applySnapshot([[335.94, 100]], [[335.99, 100]], Date.now());
  const px = exitLimitPx("sell", b, 339.46);
  assert.ok(px >= 339.46, `underwater exit ${px} must not dump below entry`);
  assert.equal(sellLimitUnfillable(339.46, 335.94, 335.99), true);
  assert.equal(sellLimitUnfillable(335.98, 335.94, 335.99), false);
});

ok("orderFilledQty never invents requested size on a zero fill", () => {
  assert.equal(orderFilledQty({ filledQty: 0, qty: 16, status: "canceled" }), 0);
  assert.equal(orderFilledQty({ filledQty: 0, qty: 16, status: "filled" }), 0);
  assert.equal(orderFilledQty({ filledQty: 3, qty: 16, status: "partially_filled" }), 3);
  assert.equal(filledShareQty(0), 0);
  assert.equal(filledShareQty(0.4), 0.4);
  assert.equal(filledShareQty(16), 16);
  assert.equal(isHftExitClientId("flat-abc"), true);
  assert.equal(isHftExitClientId("uuid-fortress"), false);
  assert.equal(isHftEntryClientId("obi-msyx"), true);
  assert.equal(isHftEntryClientId("flat-abc"), false);
  const fakeFilled = interpretFillSnapshot({ status: "filled", filledQty: 0 }, 16);
  assert.equal(fakeFilled.kind, "poll");
  const canceled = interpretFillSnapshot({ status: "canceled", filledQty: 0 }, 16);
  assert.equal(canceled.kind, "done");
  if (canceled.kind === "done") {
    assert.equal(canceled.filled, false);
    assert.equal(canceled.filledQty, 0);
    assert.equal(canceled.canceled, true);
  }
  const real = interpretFillSnapshot({ status: "filled", filledQty: 16 }, 16);
  assert.equal(real.kind, "done");
  if (real.kind === "done") {
    assert.equal(real.filled, true);
    assert.equal(real.filledQty, 16);
  }
  const partial = interpretFillSnapshot({ status: "canceled", filledQty: 3 }, 16);
  assert.equal(partial.kind, "done");
  if (partial.kind === "done") {
    assert.equal(partial.filled, true);
    assert.equal(partial.filledQty, 3);
  }
});

ok("order lifecycle knows terminal vs open statuses", () => {
  assert.ok(TERMINAL_ORDER_STATUSES.has("expired"));
  assert.ok(TERMINAL_ORDER_STATUSES.has("canceled"));
  assert.ok(OPEN_ORDER_STATUSES.has("new"));
  assert.ok(!OPEN_ORDER_STATUSES.has("filled"));
});

ok("L2Book computes micro-price and best-level OBI on refresh", () => {
  const b = new L2Book("SPY");
  b.applySnapshot([[100, 800]], [[100.02, 200]], Date.now());
  assert.ok(Math.abs(b.bestObi - 0.6) < 0.01);
  const mp = microPrice(b);
  assert.ok(mp > 100 && mp < 100.02);
  assert.ok(microPriceDriftBps(b) > 0);
  assert.equal(bestLevelObi(b), b.bestObi);
});

ok("flowIsSellToxic blocks burst + negative micro-price drift", () => {
  const prevDrift = process.env.HFT_VPIN_MIN_DRIFT_BPS;
  process.env.HFT_VPIN_MIN_DRIFT_BPS = "0.5";
  const b = new L2Book("SPY");
  b.applySnapshot([[100, 50]], [[100.02, 950]], Date.now());
  const tape = new TapeVelocity("SPY", 100, 5000);
  const t0 = Date.now();
  tape.onTrade(t0 - 4000, 100, 1);
  for (let i = 0; i < 40; i++) tape.onTrade(t0 + i, 100, 10);
  assert.ok(flowIsSellToxic(b, tape));
  if (prevDrift === undefined) delete process.env.HFT_VPIN_MIN_DRIFT_BPS;
  else process.env.HFT_VPIN_MIN_DRIFT_BPS = prevDrift;
});

ok("assessQuoteHealth rejects stale and crossed books", () => {
  const prevAge = process.env.HFT_MAX_QUOTE_AGE_MS;
  const prevSkip = process.env.HFT_SKIP_QUOTE_HEALTH;
  delete process.env.HFT_SKIP_QUOTE_HEALTH;
  process.env.HFT_MAX_QUOTE_AGE_MS = "1000";
  const b = new L2Book("AAPL");
  const now = Date.now();
  b.applySnapshot([[100, 10]], [[100.02, 10]], now);
  assert.equal(assessQuoteHealth(b, now).ok, true);
  // Stale only when BOTH exchange ts and local receive are old (IEX `t` can be
  // NaN; lastUpdateMs is the fallback so a fresh receive is not rejected).
  b.lastUpdateMs = now - 5000;
  assert.equal(assessQuoteHealth(b, now - 5000).ok, false);
  b.applySnapshot([[101, 10]], [[100, 10]], now);
  assert.equal(assessQuoteHealth(b, now).reason, "crossed");
  if (prevAge === undefined) delete process.env.HFT_MAX_QUOTE_AGE_MS;
  else process.env.HFT_MAX_QUOTE_AGE_MS = prevAge;
  if (prevSkip === undefined) delete process.env.HFT_SKIP_QUOTE_HEALTH;
  else process.env.HFT_SKIP_QUOTE_HEALTH = prevSkip;
});

ok("SimBroker dry-run fills IOC buy only when limit crosses ask", async () => {
  const prevDry = process.env.HFT_DRY_RUN;
  const prevSim = process.env.HFT_SIM_BROKER;
  process.env.HFT_DRY_RUN = "true";
  process.env.HFT_SIM_BROKER = "true";
  const ex = new AlpacaExecutor("https://paper-api.alpaca.markets", "k", "s", true);
  ex.registerNbbo("SPY", 100, 100.05);
  const miss = await ex.place({
    symbol: "SPY",
    side: "buy",
    qty: 10,
    type: "limit",
    time_in_force: "ioc",
    limit_price: 100.02,
    client_order_id: "t-miss",
  });
  assert.equal(miss.orderStatus, "new");
  assert.equal(miss.filledQty, 0);
  const hit = await ex.place({
    symbol: "SPY",
    side: "buy",
    qty: 10,
    type: "limit",
    time_in_force: "ioc",
    limit_price: 100.06,
    client_order_id: "t-hit",
  });
  assert.equal(hit.orderStatus, "filled");
  assert.equal(hit.filledAvgPrice, 100.05);
  const snap = await ex.getOrder(hit.id!);
  assert.equal(snap?.status, "filled");
  if (prevDry === undefined) delete process.env.HFT_DRY_RUN;
  else process.env.HFT_DRY_RUN = prevDry;
  if (prevSim === undefined) delete process.env.HFT_SIM_BROKER;
  else process.env.HFT_SIM_BROKER = prevSim;
});

ok("DAY working tickets keep pending (no repeat FIRE)", () => {
  assert.equal(shouldReleasePending({ working: true }), false);
  assert.equal(shouldReleasePending({ working: false }), true);
});

ok("CircuitBreaker trips on rolling loss budget", () => {
  const prevMax = process.env.HFT_CB_MAX_LOSS_USD;
  const prevEn = process.env.HFT_CIRCUIT_BREAKER;
  const prevPersist = process.env.HFT_CB_PERSIST;
  const prevDay = process.env.HFT_CB_DAY_LOSS_USD;
  process.env.HFT_CB_MAX_LOSS_USD = "50";
  process.env.HFT_CIRCUIT_BREAKER = "true";
  process.env.HFT_CB_PERSIST = "false";
  process.env.HFT_CB_DAY_LOSS_USD = "0";
  const cb = new CircuitBreaker();
  cb.recordRoundTripPnl(-30, 1000);
  assert.equal(cb.isTripped(), false);
  cb.recordRoundTripPnl(-25, 2000);
  assert.equal(cb.isTripped(), true);
  if (prevMax === undefined) delete process.env.HFT_CB_MAX_LOSS_USD;
  else process.env.HFT_CB_MAX_LOSS_USD = prevMax;
  if (prevEn === undefined) delete process.env.HFT_CIRCUIT_BREAKER;
  else process.env.HFT_CIRCUIT_BREAKER = prevEn;
  if (prevPersist === undefined) delete process.env.HFT_CB_PERSIST;
  else process.env.HFT_CB_PERSIST = prevPersist;
  if (prevDay === undefined) delete process.env.HFT_CB_DAY_LOSS_USD;
  else process.env.HFT_CB_DAY_LOSS_USD = prevDay;
});

ok("HFT signals/MR use effectiveBudgetMs so 8ms local proc is not a skip-all", () => {
  const here = path.dirname(fileURLToPath(import.meta.url));
  const sig = fs.readFileSync(path.join(here, "../obi-tape/obi-tape-signals.js"), "utf8");
  const mr = fs.readFileSync(path.join(here, "../obi-tape/micro-mean-reversion.js"), "utf8");
  assert.ok(sig.includes("effectiveBudgetMs"));
  assert.ok(mr.includes("effectiveBudgetMs"));
});

ok("execDelayFeeBps uses RTT excess vs baseline, capped", () => {
  const prevSkip = process.env.HFT_SKIP_LATENCY_BUDGET;
  const prevMs = process.env.HFT_EXEC_DELAY_MS;
  const prevCap = process.env.HFT_EXEC_DELAY_MAX_FEE_BPS;
  const prevBase = process.env.HFT_EXEC_DELAY_BASELINE_MS;
  const prevPer = process.env.HFT_EXEC_DELAY_BPS_PER_10MS;
  process.env.HFT_SKIP_LATENCY_BUDGET = "false";
  process.env.HFT_EXEC_DELAY_MS = "106";
  process.env.HFT_EXEC_DELAY_BASELINE_MS = "20";
  process.env.HFT_EXEC_DELAY_BPS_PER_10MS = "0.5";
  process.env.HFT_EXEC_DELAY_MAX_FEE_BPS = "8";
  assert.equal(loadExecDelayMs(), 106);
  assert.ok(Math.abs(execDelayFeeBps() - 4.3) < 1e-9);
  const bud = effectiveBudgetMs(25);
  assert.ok(bud >= 25);
  assert.ok(bud > 25); // delay*1.25+5 ≈ 137
  if (prevSkip === undefined) delete process.env.HFT_SKIP_LATENCY_BUDGET;
  else process.env.HFT_SKIP_LATENCY_BUDGET = prevSkip;
  if (prevMs === undefined) delete process.env.HFT_EXEC_DELAY_MS;
  else process.env.HFT_EXEC_DELAY_MS = prevMs;
  if (prevCap === undefined) delete process.env.HFT_EXEC_DELAY_MAX_FEE_BPS;
  else process.env.HFT_EXEC_DELAY_MAX_FEE_BPS = prevCap;
  if (prevBase === undefined) delete process.env.HFT_EXEC_DELAY_BASELINE_MS;
  else process.env.HFT_EXEC_DELAY_BASELINE_MS = prevBase;
  if (prevPer === undefined) delete process.env.HFT_EXEC_DELAY_BPS_PER_10MS;
  else process.env.HFT_EXEC_DELAY_BPS_PER_10MS = prevPer;
});

ok("HFT_SKIP_LATENCY_BUDGET=true makes budget infinite (explicit opt-out only)", () => {
  const prev = process.env.HFT_SKIP_LATENCY_BUDGET;
  process.env.HFT_SKIP_LATENCY_BUDGET = "true";
  assert.equal(effectiveBudgetMs(25), Number.POSITIVE_INFINITY);
  if (prev === undefined) delete process.env.HFT_SKIP_LATENCY_BUDGET;
  else process.env.HFT_SKIP_LATENCY_BUDGET = prev;
});

ok("advanced charts: 4-way agreement beats a lone candle", () => {
  const lone = fuseVotes(0.9, 0, 0, 0);
  const agree = fuseVotes(0.5, 0.5, 0.4, 0.35);
  assert.equal(lone.crossFamily, false);
  assert.ok(agree.nAgree >= 2);
  assert.equal(agree.crossFamily, true);
  assert.ok(Math.abs(agree.score) > Math.abs(lone.score));
});

ok("advanced charts: line vote fires on first range break", () => {
  const c = new Float64Array(40);
  for (let i = 0; i < 30; i++) c[i] = 100 + Math.sin(i) * 0.4;
  c[30] = 101.3;
  for (let i = 31; i < 40; i++) c[i] = 101.3 + (i - 30) * 0.01;
  assert.ok(lineVote(c, 31) > 0.2);
});

ok("advanced charts: PnF prints X on a sustained rise", () => {
  const p = new PointAndFigure(0.01, 3);
  let maxV = 0;
  let px = 100;
  for (let i = 0; i < 20; i++) {
    px *= 1.015;
    maxV = Math.max(maxV, p.onClose(px));
  }
  assert.equal(p.dir, 1);
  assert.ok(maxV > 0);
});

ok("advanced charts: engine onFinishedOHLC produces a vote", () => {
  const eng = new AdvancedChartEngine(64, 0.002);
  let v = eng.last;
  let px = 100;
  for (let i = 0; i < 40; i++) {
    const o = px;
    px *= 1.004;
    v = eng.onFinishedOHLC(o, px + 0.05, o - 0.05, px, 1);
  }
  assert.ok(Number.isFinite(v.score));
});

ok("microstructure chart overlay moves p when 3 charts agree", () => {
  const b = new L2Book("AAPL");
  b.applySnapshot([[190.0, 100]], [[190.02, 100]], Date.now());
  const tape = new TapeVelocity("AAPL", 100, 5000);
  tape.onTrade(Date.now(), 190.01, 50);
  const base: MicroInputs = {
    book: b,
    tape,
    trend: 0,
    vwap: 190,
    lastClose: 190.01,
    jpBias: 0,
  };
  const prev = process.env.HFT_W_CHART_PROB;
  process.env.HFT_W_CHART_PROB = "0.2";
  const p0 = upwardProbability(base);
  const p1 = upwardProbability({ ...base, chartScore: 0.8, chartAgree: 3 });
  if (prev === undefined) delete process.env.HFT_W_CHART_PROB;
  else process.env.HFT_W_CHART_PROB = prev;
  assert.ok(p1 > p0);
});

ok("trade-ev logit fuse prefers aligned OBI+tape", () => {
  const weak = fuseObiTape(0.2, 1.1, 2.4);
  const strong = fuseObiTape(0.7, 4.0, 2.4);
  assert.ok(strong > weak);
  assert.ok(strong > 0.7);
});

ok("trade-ev skips when cost eats the edge", () => {
  const bad = shouldEnterEv(0.55, 2.0, 8.0, 0.4, 0.52);
  const good = shouldEnterEv(0.62, 12.0, 3.0, 0.4, 0.52);
  assert.equal(bad.ok, false);
  assert.equal(good.ok, true);
  assert.ok(expectedBps(0.6, 10, 2) > 0);
});

ok("pace plumbing hits 185/min with 50 names and 18s cooldown", () => {
  assert.equal(plumbingHitsTarget(50, 18_000, 185, 2), true);
  assert.equal(plumbingHitsTarget(8, 90_000, 185, 2), false);
  const now = 1_000_000;
  const stamps = Array.from({ length: 185 }, (_, i) => now - i * 300);
  assert.ok(rollingCount(now, stamps) >= 185);
  assert.ok(tpmTarget() > 0);
});

ok("pace plumbing hits 200/min on 15 IEX WS names at 6s cooldown", () => {
  // 15 × (60/6) × 2 = 300 theoretical; Alpaca cap 200.
  assert.equal(plumbingHitsTarget(15, 6_000, 200, 2), true);
  assert.equal(plumbingHitsTarget(15, 90_000, 200, 2), false);
});

ok("gap vs lastGoodMid is adopted when the NBBO is tight", () => {
  const prevShock = process.env.HFT_MAX_MID_SHOCK_BPS;
  const prevWide = process.env.HFT_SHOCK_WIDE_SPREAD_BPS;
  const prevSkip = process.env.HFT_SKIP_QUOTE_HEALTH;
  delete process.env.HFT_SKIP_QUOTE_HEALTH;
  process.env.HFT_MAX_MID_SHOCK_BPS = "500";
  process.env.HFT_SHOCK_WIDE_SPREAD_BPS = "80";
  const b = new L2Book("MELI");
  const now = Date.now();
  b.applySnapshot([[1786, 100]], [[1792, 100]], now);
  const gap = assessQuoteHealth(b, now, 1680);
  assert.equal(gap.ok, true);
  assert.equal(gap.adoptMid, true);
  const wide = new L2Book("SPIKE");
  wide.applySnapshot([[100, 10]], [[110, 10]], now);
  const shock = assessQuoteHealth(wide, now, 90);
  assert.equal(shock.ok, false);
  assert.equal(shock.reason, "shock");
  assert.equal(shock.adoptMid, false);
  if (prevShock === undefined) delete process.env.HFT_MAX_MID_SHOCK_BPS;
  else process.env.HFT_MAX_MID_SHOCK_BPS = prevShock;
  if (prevWide === undefined) delete process.env.HFT_SHOCK_WIDE_SPREAD_BPS;
  else process.env.HFT_SHOCK_WIDE_SPREAD_BPS = prevWide;
  if (prevSkip === undefined) delete process.env.HFT_SKIP_QUOTE_HEALTH;
  else process.env.HFT_SKIP_QUOTE_HEALTH = prevSkip;
});

ok("lag haircut sits out and never rounds a thin clip up to the floor", () => {
  const prevFloor = process.env.HFT_MIN_ORDER_NOTIONAL;
  const prevCap = process.env.HFT_MAX_ORDER_NOTIONAL;
  const prevMinH = process.env.HFT_MIN_HAIRCUT;
  process.env.HFT_MIN_ORDER_NOTIONAL = "80";
  process.env.HFT_MAX_ORDER_NOTIONAL = "350";
  process.env.HFT_MIN_HAIRCUT = "0.12";
  assert.ok(Math.abs(lagHaircut(0, 0, 250) - 1) < 1e-9);
  assert.ok(Math.abs(lagHaircut(250, 0, 250) - 0.5) < 1e-9);
  const fresh = combinedHaircut(0, 0, 72_000, 0);
  assert.equal(fresh.sitOut, false);
  assert.ok(fresh.haircut > 0.9);
  const stale = combinedHaircut(2_000, 0, 72_000, 250);
  assert.equal(stale.sitOut, true);
  const fullInv = inventoryHaircut(5_760, 72_000, 0.08);
  assert.equal(fullInv, 0);
  assert.equal(clipNotional(180, 0.5), 90);
  assert.equal(clipNotional(180, 0.1), 0);
  assert.equal(clipNotional(6_400, 1), 350);
  const sit = sizeHftClip({
    baseUsd: 6_400,
    quoteAgeMs: 2_000,
    hftInventoryUsd: 0,
    equityUsd: 72_000,
    rttMs: 250,
  });
  assert.equal(sit.sitOut, true);
  assert.equal(sit.notional, 0);
  if (prevFloor === undefined) delete process.env.HFT_MIN_ORDER_NOTIONAL;
  else process.env.HFT_MIN_ORDER_NOTIONAL = prevFloor;
  if (prevCap === undefined) delete process.env.HFT_MAX_ORDER_NOTIONAL;
  else process.env.HFT_MAX_ORDER_NOTIONAL = prevCap;
  if (prevMinH === undefined) delete process.env.HFT_MIN_HAIRCUT;
  else process.env.HFT_MIN_HAIRCUT = prevMinH;
});

ok("ofi mode longs on OBI+micro without tape burst; dual does not", () => {
  const ofi = wantsDirection(
    "ofi",
    true,
    { obiLong: true, obiShort: false, tapeBurst: false },
    { microOk: true, sellToxic: false },
  );
  const dual = wantsDirection(
    "dual",
    true,
    { obiLong: true, obiShort: false, tapeBurst: false },
    { microOk: true, sellToxic: false },
  );
  const toxic = wantsDirection(
    "ofi",
    true,
    { obiLong: true, obiShort: false, tapeBurst: true },
    { microOk: true, sellToxic: true },
  );
  assert.equal(ofi.long, true);
  assert.equal(dual.long, false);
  assert.equal(toxic.long, false);
  const prevOr = process.env.HFT_OR_SIGNAL;
  const prevMode = process.env.HFT_SIGNAL_MODE;
  process.env.HFT_OR_SIGNAL = "false";
  delete process.env.HFT_SIGNAL_MODE;
  assert.equal(resolveSignalMode(), "ofi");
  process.env.HFT_SIGNAL_MODE = "dual";
  assert.equal(resolveSignalMode(), "dual");
  if (prevOr === undefined) delete process.env.HFT_OR_SIGNAL;
  else process.env.HFT_OR_SIGNAL = prevOr;
  if (prevMode === undefined) delete process.env.HFT_SIGNAL_MODE;
  else process.env.HFT_SIGNAL_MODE = prevMode;
});

ok("aggressive IOC take crosses the ask when buy-low is off", () => {
  const prevBuy = process.env.HFT_BUY_LOW;
  const prevAgg = process.env.HFT_AGGRESSIVE_ENTRY;
  process.env.HFT_BUY_LOW = "false";
  process.env.HFT_AGGRESSIVE_ENTRY = "true";
  const b = new L2Book("KO");
  b.applySnapshot([[70.00, 400]], [[70.02, 200]], Date.now());
  const px = entryLimitPx("buy", b);
  assert.ok(px != null);
  assert.ok(px! >= 70.02);
  if (prevBuy === undefined) delete process.env.HFT_BUY_LOW;
  else process.env.HFT_BUY_LOW = prevBuy;
  if (prevAgg === undefined) delete process.env.HFT_AGGRESSIVE_ENTRY;
  else process.env.HFT_AGGRESSIVE_ENTRY = prevAgg;
});

ok("fuseObiMicro does not need a tape burst", () => {
  const quiet = fuseObiMicro(0.7, 2.0);
  const dualQuiet = fuseObiTape(0.7, 0.2, 2.4);
  assert.ok(quiet > 0.6);
  assert.ok(quiet > dualQuiet);
});

ok("completeNbbo fills a missing IEX ask from last sale and marks synthetic", () => {
  const one = completeNbbo(90.5, 0, 90.62);
  assert.equal(one.synthetic, true);
  assert.equal(one.bp, 90.5);
  assert.equal(one.ap, 90.62);
  const tight = completeNbbo(90.5, 90.52, 90.51);
  assert.equal(tight.synthetic, false);
  assert.equal(tight.bp, 90.5);
  assert.equal(tight.ap, 90.52);
  const empty = completeNbbo(0, 0, 0);
  assert.equal(empty.bp, 0);
  assert.equal(empty.ap, 0);
});

ok("pickWsTickers skips names we already hold", () => {
  const ws = pickWsTickers(
    ["NVDA", "KO", "UBER", "PLTR", "CRWD", "NVDA"],
    new Set(["NVDA", "KO"]),
    3,
  );
  assert.deepEqual(ws, ["UBER", "PLTR", "CRWD"]);
  assert.equal(pickWsTickers(["KO"], new Set(["KO"]), 15).length, 0);
});

ok("microPriceSupportsLong defers to OBI when sizes are equal", () => {
  const b = new L2Book("UBER");
  b.applySnapshot([[70, 100]], [[70.02, 100]], Date.now());
  b.obi = 0.5;
  assert.equal(microPriceSupportsLong(b), true);
  b.obi = 0;
  assert.equal(microPriceSupportsLong(b), false);
});

ok("TapeVelocity records lastPx", () => {
  const tape = new TapeVelocity("UBER", 100, 5000);
  tape.onTrade(Date.now(), 91.25, 10);
  assert.equal(tape.lastPx, 91.25);
});

ok("HFT does not size or enter on negative cash / over-gross", () => {
  process.env.HFT_SIZE_FROM_CASH = "true";
  process.env.HFT_MIN_CASH_TO_BUY = "250";
  process.env.HFT_MAX_GROSS_FRAC = "1.0";
  process.env.HFT_BP_USE_FRAC = "0.35";
  process.env.HFT_CASH_RESERVE_USD = "500";
  __setMarginCacheForTest({
    buyingPower: 171_000,
    equity: 70_000,
    cash: -5_800,
    longMarketValue: 76_000,
    maintenanceMargin: 0,
    regtBuyingPower: 70_000,
  });
  const blocked = canEnterBuy(250);
  assert.equal(blocked.ok, false);
  assert.ok((blocked.reason || "").includes("cash"));
  assert.equal(resolveHftNotionalUsd(250), 0);
  __setMarginCacheForTest({
    buyingPower: 20_000,
    equity: 70_000,
    cash: 8_000,
    longMarketValue: 62_000,
    maintenanceMargin: 0,
    regtBuyingPower: 20_000,
  });
  const okBuy = canEnterBuy(250);
  assert.equal(okBuy.ok, true);
  assert.ok(resolveHftNotionalUsd(250) >= 80);
  __setMarginCacheForTest(null);
});

if (failed > 0) {
  console.error(`${failed} test(s) failed`);
  process.exit(1);
}
console.log("all hot-path tests passed");
