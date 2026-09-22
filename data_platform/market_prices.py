"""Unified daily OHLCV — Polygon-first, cache, throttled Yahoo fallback."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pandas as pd


def _period_start(period: str) -> str:
    p = (period or "1y").strip().lower()
    now = datetime.now(timezone.utc)
    mapping = {
        "1d": 2,
        "5d": 7,
        "1mo": 32,
        "3mo": 96,
        "6mo": 190,
        "1y": 370,
        "2y": 740,
        "5y": 1850,
        "10y": 3700,
        "max": 7300,
    }
    days = mapping.get(p, 370)
    return (now - timedelta(days=days)).strftime("%Y-%m-%d")


def configure_process_prices(*, training: bool = False) -> None:
    """Apply Yahoo-first price routing for this process (call after load_dotenv)."""
    from data_platform.price_fetch_policy import apply_price_env_defaults
    from data_platform.runtime_env import load_runtime_env

    load_runtime_env()
    apply_price_env_defaults(training=training)


def fetch_daily(ticker: str, start: str, end: str | None = None) -> pd.DataFrame:
    from feature_engineering import load_price_data

    return load_price_data(ticker.strip().upper(), start, end)


def fetch_period(
    ticker: str,
    period: str = "1y",
    interval: str = "1d",
    *,
    auto_adjust: bool = True,
) -> pd.DataFrame:
    """Daily bars via Polygon/cache; intraday still uses throttled Yahoo."""
    sym = ticker.strip().upper()
    iv = (interval or "1d").lower()
    if iv in ("1d", "1day", "day", "daily"):
        start = _period_start(period)
        end = (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%d")
        df = fetch_daily(sym, start, end)
        if df is not None and not df.empty:
            return df
    from multi_source_data import fetch_yahoo_intraday

    return fetch_yahoo_intraday(sym, period=period, interval=interval, auto_adjust=auto_adjust)


def download(
    tickers: str | list[str],
    *,
    period: str = "1y",
    interval: str = "1d",
    progress: bool = False,
    auto_adjust: bool = True,
) -> pd.DataFrame:
    """Drop-in for yf.download on daily data (single or multi ticker)."""
    _ = progress
    syms = [tickers.strip().upper()] if isinstance(tickers, str) else [s.strip().upper() for s in tickers if s]
    if not syms:
        return pd.DataFrame()
    if len(syms) == 1:
        return fetch_period(syms[0], period=period, interval=interval, auto_adjust=auto_adjust)

    frames: dict[str, pd.DataFrame] = {}
    for sym in syms:
        df = fetch_period(sym, period=period, interval=interval, auto_adjust=auto_adjust)
        if df is not None and not df.empty:
            frames[sym] = df
    if not frames:
        return pd.DataFrame()
    if len(frames) == 1 and len(syms) == 1:
        return next(iter(frames.values()))
    parts: list[pd.DataFrame] = []
    for sym, df in frames.items():
        sub = df.copy()
        sub.columns = pd.MultiIndex.from_product([sub.columns, [sym]])
        parts.append(sub)
    try:
        return pd.concat(parts, axis=1).sort_index(axis=1)
    except Exception as e:
        log.debug("[MARKET] multi download concat failed: %s", e)
        return next(iter(frames.values()))


def ticker_history(
    ticker: str,
    *,
    start: str | None = None,
    end: str | None = None,
    period: str | None = None,
    interval: str = "1d",
    auto_adjust: bool = True,
) -> pd.DataFrame:
    sym = ticker.strip().upper()
    if start:
        return fetch_daily(sym, start, end)
    return fetch_period(sym, period=period or "1y", interval=interval, auto_adjust=auto_adjust)
