"""Benchmark bot equity vs SPY — Alpaca/Polygon only (no Yahoo rate limits)."""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

_BENCH_CACHE: dict[str, Any] = {"ts": 0.0, "payload": {}}


def _fetch_return(symbol: str, days: int = 5) -> float | None:
    sym = symbol.strip().upper() or "SPY"
    end = datetime.now(timezone.utc).date()
    start = (end - timedelta(days=max(days + 10, 14))).isoformat()
    end_s = (end + timedelta(days=1)).isoformat()
    df = pd.DataFrame()

    if os.getenv("POLYGON_API_KEY", "").strip():
        try:
            from multi_source_data import fetch_polygon_daily

            df = fetch_polygon_daily(sym, start, end_s)
        except Exception:
            pass

    if df.empty:
        try:
            from alpaca_broker import fetch_alpaca_daily_bars

            df = fetch_alpaca_daily_bars(sym, start, end_s)
        except Exception:
            pass

    if df is None or df.empty:
        return None
    close = df["Close"].astype(float).dropna()
    if len(close) < 2:
        return None
    window = close.iloc[-min(len(close), days + 2) :]
    if len(window) < 2:
        return None
    return float(window.iloc[-1] / window.iloc[0] - 1.0)


def beat_market_snapshot(equity: float | None = None, *, lookback_days: int | None = None) -> dict[str, Any]:
    """
    Returns bot vs SPY over recent window.
    alpha > 0 means beating the market.
    """
    ttl = float(os.getenv("BEAT_MARKET_CACHE_SEC", "120"))
    now = time.time()
    if ttl > 0 and _BENCH_CACHE["payload"] and (now - float(_BENCH_CACHE["ts"])) < ttl:
        return dict(_BENCH_CACHE["payload"])

    days = int(lookback_days or os.getenv("SELF_IMPROVE_BENCHMARK_DAYS", "5"))
    bench_sym = os.getenv("SELF_IMPROVE_BENCHMARK", "SPY").strip().upper() or "SPY"
    spy_ret = _fetch_return(bench_sym, days)
    bot_ret: float | None = None
    if equity is None:
        try:
            from alpaca_broker import get_account

            acct = get_account() or {}
            eq_now = float(acct.get("equity") or acct.get("last_equity") or 0.0)
            eq_prev = float(acct.get("last_equity") or eq_now)
            if eq_prev > 0:
                bot_ret = (eq_now - eq_prev) / eq_prev
        except Exception:
            pass
    else:
        try:
            from alpaca_broker import get_account

            acct = get_account() or {}
            eq_now = float(acct.get("equity") or equity)
            if eq_now > 0 and equity > 0:
                bot_ret = (eq_now - float(equity)) / float(equity)
        except Exception:
            bot_ret = None

    alpha = None
    beating = False
    if spy_ret is not None and bot_ret is not None:
        alpha = float(bot_ret - spy_ret)
        beating = alpha >= float(os.getenv("SELF_IMPROVE_ALPHA_TARGET", "0.0"))
    out = {
        "benchmark": bench_sym,
        "lookback_days": days,
        "spy_return": spy_ret,
        "bot_return": bot_ret,
        "alpha": alpha,
        "beating_market": beating,
        "losing_to_market": alpha is not None and alpha < float(os.getenv("SELF_IMPROVE_ALPHA_MIN", "-0.001")),
    }
    _BENCH_CACHE["ts"] = now
    _BENCH_CACHE["payload"] = dict(out)
    return out
