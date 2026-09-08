#!/usr/bin/env python3
"""
Live loop over a capped universe: score with dual short/long models, optional real orders.

This cannot cover every global listing simultaneously with Yahoo data + one socket;
use MAX_LIVE_SYMBOLS and run multiple workers if you scale horizontally.
"""

from __future__ import annotations

import argparse
import os
import random
import time

from dotenv import load_dotenv

load_dotenv()

from config import IBKR_HOST, IBKR_PORT
from feature_engineering import build_features
from ml_model import predict_row_details
from news_reader import analyze_sentiment, fetch_news
from universe_provider import load_universe_with_cap
from utils import log
from runtime.worker_pool import BoundedWorkerPool
from runtime.signal_bus import SignalBus
from runtime.latency_monitor import LatencyMonitor
from runtime.degradation_policy import decide_degradation, as_dict as health_dict
from self_modify.policy_agent import GuardedPolicyAgent, get_runtime_param
from multi_algo_fusion import fused_decision
from compliance_guard import pretrade_check


def _score_ticker(ticker: str) -> tuple[float, int, float] | None:
    from datetime import datetime, timedelta, timezone

    end = (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%d")
    start = (datetime.now(timezone.utc) - timedelta(days=800)).strftime("%Y-%m-%d")
    df = build_features(ticker, start, end)
    if df.empty:
        return None
    news = fetch_news(ticker)
    scores = [analyze_sentiment(a["headline"] + " " + a.get("summary", "")) for a in news]
    blend = sum(scores) / len(scores) if scores else 0.0
    row = df.iloc[-1].copy()
    for k in ("sentiment", "lag_1_sentiment", "lag_2_sentiment", "lag_3_sentiment"):
        row[k] = blend

    path = os.path.join("models", f"{ticker}_model.pkl")
    if not os.path.isfile(path):
        return None
    det = predict_row_details(path, row)
    pred = int(det["pred"])
    p_up = float(det["p_up"])
    if os.getenv("USE_MULTI_ALGO_FUSION", "true").lower() in ("1", "true", "yes"):
        try:
            fd = fused_decision(
                ticker=ticker,
                model_bundle_path=path,
                row=row,
                p_base=float(p_up),
                min_conf=float(os.getenv("BUY_THRESHOLD", "0.95")),
            )
            p_up = float(fd["p_final"])
            pred = 1 if p_up >= 0.5 else 0
        except Exception:
            pass
    from analytics.execution_confidence import execution_confidence

    exec_c, _ = execution_confidence(
        p_up,
        det.get("p_short"),
        det.get("p_long"),
    )
    return p_up, pred, exec_c


def _score_ticker_safe(ticker: str) -> tuple[str, tuple[float, int, float] | None]:
    try:
        return ticker, _score_ticker(ticker)
    except Exception:
        log.exception("[LIVE] score failed %s", ticker)
        return ticker, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-symbols", type=int, default=int(os.getenv("MAX_LIVE_SYMBOLS", "200")))
    ap.add_argument("--sleep", type=float, default=float(os.getenv("LIVE_SLEEP_SEC", "0.4")))
    ap.add_argument("--shuffle", action="store_true", help="Randomize order each full pass")
    ap.add_argument("--once", action="store_true", help="Single pass over symbols then exit")
    ap.add_argument("--concurrency", type=int, default=int(os.getenv("LIVE_CONCURRENCY", "8")))
    args = ap.parse_args()

    use_real = os.getenv("USE_REAL_MONEY", "false").lower() in ("1", "true", "yes")
    broker = os.getenv("BROKER", "alpaca").strip().lower()
    ib = None
    try:
        if use_real and broker == "ibkr":
            log.warning(
                "[LIVE] USE_REAL_MONEY=true broker=ibkr — real market orders may be sent. "
                "You are responsible for sizing, margin, and compliance."
            )
            from ibkr_executor import connect_ib

            ib = connect_ib()
        elif use_real and broker == "alpaca":
            log.warning(
                "[LIVE] USE_REAL_MONEY=true broker=alpaca — orders go to ALPACA_BASE_URL "
                "(paper by default). Verify keys and account."
            )
        else:
            log.info("[LIVE] Signal-only / paper track (USE_REAL_MONEY not set or broker idle)")

        raw_list = os.getenv("LIVE_SYMBOL_LIST", "").strip()
        if raw_list:
            syms = [s.strip().upper() for s in raw_list.split(",") if s.strip()][: args.max_symbols]
        else:
            syms = load_universe_with_cap(max_symbols=args.max_symbols, refresh=False)
        if args.shuffle:
            random.shuffle(syms)

        buy_thr = float(os.getenv("BUY_THRESHOLD", "0.95"))
        sell_thr = float(os.getenv("SELL_THRESHOLD", "0.42"))
        buy_thr = float(get_runtime_param("BUY_THRESHOLD", buy_thr))
        sell_thr = float(get_runtime_param("SELL_THRESHOLD", sell_thr))
        qty = int(float(get_runtime_param("ORDER_QUANTITY", os.getenv("ORDER_QUANTITY", "1"))))
        from analytics.execution_confidence import use_execution_confidence_gate

        use_ex_gate = use_execution_confidence_gate()
        concurrent_mode = os.getenv("LIVE_CONCURRENT", "true").lower() in ("1", "true", "yes")
        pool = BoundedWorkerPool(max_workers=max(1, int(args.concurrency)))
        bus = SignalBus()
        lat = LatencyMonitor()
        policy = GuardedPolicyAgent()

        while True:
            results: list[tuple[str, tuple[float, int, float] | None]] = []
            if concurrent_mode:
                with lat.track("score_batch"):
                    results = pool.map_unordered(_score_ticker_safe, syms)
            else:
                with lat.track("score_batch"):
                    for t in syms:
                        results.append(_score_ticker_safe(t))

            n_err = 0
            for t, out in results:
                if out is None:
                    n_err += 1
                    continue
                p_up, _pred, exec_c = out
                sig = float(exec_c if use_ex_gate else p_up)
                bus.publish(
                    "model_score",
                    t,
                    {"p_up": float(p_up), "execution_confidence": float(exec_c), "signal": float(sig)},
                )
                if sig >= buy_thr:
                    log.info("[LIVE] BUY signal %s p_up=%.3f exec=%.3f sig=%.3f", t, p_up, exec_c, sig)
                    try:
                        from intel.algo_risk_filter import blocks_buy

                        if blocks_buy(t)[0]:
                            log.warning("[LIVE] algo risk block BUY %s", t)
                            continue
                    except Exception:
                        pass
                    c = pretrade_check(t, "BUY", qty, qty * 1.0, is_short=False)
                    if not c.ok:
                        log.warning("[LIVE] compliance block BUY %s: %s", t, c.reason)
                        continue
                    if use_real and broker == "ibkr" and ib is not None:
                        from ibkr_executor import place_market_order

                        with lat.track("order_route"):
                            place_market_order(ib, t, qty, "BUY")
                    elif use_real and broker == "alpaca":
                        from alpaca_broker import place_market_alpaca

                        with lat.track("order_route"):
                            place_market_alpaca(t, qty, "BUY")
                elif p_up <= sell_thr:
                    log.info("[LIVE] SELL signal %s p_up=%.3f", t, p_up)
                    c = pretrade_check(t, "SELL", qty, qty * 1.0, is_short=False)
                    if not c.ok:
                        log.warning("[LIVE] compliance block SELL %s: %s", t, c.reason)
                        continue
                    if use_real and broker == "ibkr" and ib is not None:
                        from ibkr_executor import place_market_order

                        with lat.track("order_route"):
                            place_market_order(ib, t, qty, "SELL")
                    elif use_real and broker == "alpaca":
                        from alpaca_broker import place_market_alpaca

                        with lat.track("order_route"):
                            place_market_alpaca(t, qty, "SELL")
                if not concurrent_mode:
                    time.sleep(args.sleep)
                    if ib is not None:
                        ib.sleep(0.01)
            if results:
                vals = [r[1][2] if use_ex_gate else r[1][0] for r in results if r[1] is not None]
                hit_proxy = sum(1 for p in vals if p >= buy_thr) / max(len(vals), 1)
                sharpe_proxy = (sum(vals) / max(len(vals), 1)) - 0.5
                lat_sum = lat.summary()
                avg_score_ms = float(lat_sum.get("score_batch", {}).get("avg_ms", 0.0))
                err_rate = n_err / max(len(results), 1)
                health = decide_degradation(avg_score_ms, err_rate, len(results))
                if health.mode != "normal":
                    log.warning("[LIVE] health=%s", health_dict(health))
                    if health.action == "disable_llm_signal":
                        os.environ["USE_LLM_SIGNAL"] = "false"
                    elif health.action == "disable_sentiment_and_reduce_universe_50pct":
                        os.environ["DISABLE_SENTIMENT"] = "true"
                        syms = syms[: max(1, len(syms) // 2)]
                adapt = policy.observe_and_maybe_adapt(
                    {
                        "hit_rate": float(hit_proxy),
                        "drawdown": 0.0,
                        "sharpe_proxy": float(sharpe_proxy),
                    }
                )
                if adapt.get("applied"):
                    log.info("[LIVE] policy adapted %s", adapt.get("accepted"))
            if concurrent_mode:
                time.sleep(max(0.05, args.sleep))
            if args.once:
                log.info("[LIVE] --once complete (%d symbols)", len(syms))
                log.info("[LIVE] latency %s", lat.summary())
                break
            time.sleep(float(os.getenv("PASS_SLEEP_SEC", "30")))
    finally:
        if ib is not None and ib.isConnected():
            ib.disconnect()
            log.info("[LIVE] Disconnected IBKR")


if __name__ == "__main__":
    br = os.getenv("BROKER", "alpaca").strip().lower()
    if br == "ibkr":
        log.info("[LIVE] broker=ibkr socket %s:%s", IBKR_HOST, IBKR_PORT)
    else:
        log.info(
            "[LIVE] broker=alpaca orders/data via env (ALPACA_BASE_URL=%s)",
            os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets"),
        )
    main()
