"""
Multi-source OHLCV: Yahoo (always), optional Alpaca + Polygon for cross-check.

Set ALPACA_API_KEY, ALPACA_SECRET_KEY, POLYGON_API_KEY in .env when available.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Callable

import pandas as pd
import yfinance as yf

from utils import log


def _quiet_yfinance() -> None:
    """Delisted-ticker spam is not an app error — keep scans readable."""
    import logging

    logging.getLogger("yfinance").setLevel(logging.CRITICAL)


_quiet_yfinance()


def _naive_index(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    out = df.copy()
    idx = pd.to_datetime(out.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    out.index = idx
    return out


def fetch_yahoo(ticker: str, start: str, end: str | None = None) -> pd.DataFrame:
    """Throttled Yahoo daily history with disk cache fallback."""
    from data_platform.yahoo_throttle import note_rate_limit, wait_turn

    end = end or (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%d")
    sym = ticker.strip().upper()
    try:
        from data_store import load_cached_ohlcv

        cached = load_cached_ohlcv(sym)
        if cached is not None and not cached.empty:
            cached = _naive_index(cached)
            start_ts = pd.Timestamp(start)
            hit = cached.loc[cached.index >= start_ts]
            min_rows = int(os.getenv("PRICE_MIN_ROWS", "60"))
            max_gap = int(os.getenv("PRICE_CACHE_MAX_START_GAP_DAYS", "400"))
            if len(hit) >= min_rows:
                gap = int((hit.index.min() - start_ts).days) if len(hit) else 10**9
                last = cached.index.max()
                fresh = (pd.Timestamp(end) - last).days <= int(os.getenv("PRICE_CACHE_STALE_OK_DAYS", "5"))
                if fresh and gap <= max_gap:
                    return hit
    except Exception:
        cached = None

    for attempt in range(int(os.getenv("YAHOO_FETCH_RETRIES", "3"))):
        if not wait_turn():
            continue
        try:
            tk = yf.Ticker(sym)
            df = tk.history(start=start, end=end, auto_adjust=True, actions=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
            df = _naive_index(df)
            if df is not None and not df.empty:
                # Drop same-session stub bars (NaN/0 Close) before cache/return
                if "Close" in df.columns:
                    c = df["Close"].astype(float)
                    df = df.loc[c.notna() & (c > 0)].copy()
                if df.empty:
                    continue
                try:
                    from data_store import merge_and_save

                    merge_and_save(sym, df)
                except Exception:
                    pass
                return df
        except Exception as err:
            msg = str(err).lower()
            if "too many requests" in msg or "rate limit" in msg:
                note_rate_limit()
                continue
            log.warning("[DATA] Yahoo failed %s: %s", sym, err)
            break
    if cached is not None and not cached.empty:
        return cached.loc[cached.index >= pd.Timestamp(start)]
    return pd.DataFrame()


def fetch_yahoo_intraday(
    ticker: str,
    *,
    period: str = "5d",
    interval: str = "5m",
    auto_adjust: bool = True,
) -> pd.DataFrame:
    from data_platform.yahoo_throttle import note_rate_limit, wait_turn

    sym = ticker.strip().upper()
    for attempt in range(int(os.getenv("YAHOO_FETCH_RETRIES", "3"))):
        if not wait_turn():
            continue
        try:
            df = yf.download(
                sym,
                period=period,
                interval=interval,
                progress=False,
                auto_adjust=auto_adjust,
            )
            if df is None or df.empty:
                return pd.DataFrame()
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
            return _naive_index(df)
        except Exception as err:
            msg = str(err).lower()
            if "too many requests" in msg or "rate limit" in msg:
                note_rate_limit()
                continue
            log.warning("[DATA] Yahoo intraday failed %s: %s", sym, err)
            break
    return pd.DataFrame()


def fetch_alpaca_daily(ticker: str, start: str, end: str | None = None) -> pd.DataFrame:
    key = os.getenv("ALPACA_API_KEY", "").strip()
    sec = os.getenv("ALPACA_SECRET_KEY", "").strip()
    if not key or not sec:
        return pd.DataFrame()
    try:
        import requests

        base = os.getenv("ALPACA_DATA_URL", "https://data.alpaca.markets").rstrip("/")
        url = f"{base}/v2/stocks/{ticker}/bars"
        params = {"timeframe": "1Day", "start": start, "end": end or datetime.now(timezone.utc).isoformat()}
        r = requests.get(
            url,
            params=params,
            headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec},
            timeout=30,
        )
        if r.status_code == 429:
            try:
                from data_platform.source_rotator import note_limited

                note_limited("alpaca")
            except Exception:
                pass
            return pd.DataFrame()
        r.raise_for_status()
        js = r.json()
        bars = js.get("bars") or []
        if not bars:
            return pd.DataFrame()
        rows = []
        for b in bars:
            rows.append(
                {
                    "Open": float(b["o"]),
                    "High": float(b["h"]),
                    "Low": float(b["l"]),
                    "Close": float(b["c"]),
                    "Volume": float(b.get("v", 0)),
                }
            )
        idx = pd.to_datetime([b["t"] for b in bars])
        df = pd.DataFrame(rows, index=idx)
        return _naive_index(df)
    except Exception as e:
        log.warning("[DATA] Alpaca bars failed %s: %s", ticker, e)
        return pd.DataFrame()


def fetch_polygon_minute_bars(
    ticker: str,
    start: str,
    end: str | None = None,
    *,
    multiplier: int = 1,
    timespan: str = "minute",
) -> pd.DataFrame:
    """Polygon/Massive 1-min aggregates — full tape, not IEX-limited."""
    key = os.getenv("POLYGON_API_KEY", "").strip()
    if not key:
        return pd.DataFrame()
    try:
        from data_platform.polygon_throttle import note_rate_limit, wait_turn
        from symbol_aliases import price_feed_symbol

        import requests

        api_sym = price_feed_symbol(ticker)
        end_d = end or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        start_d = pd.Timestamp(start).strftime("%Y-%m-%d")
        url = (
            f"https://api.polygon.io/v2/aggs/ticker/{api_sym}/range/"
            f"{multiplier}/{timespan}/{start_d}/{end_d}"
        )
        rows: list[dict] = []
        ts: list = []
        next_url: str | None = url
        pages = 0
        while next_url and pages < int(os.getenv("POLYGON_MINUTE_MAX_PAGES", "40")):
            pages += 1
            for attempt in range(int(os.getenv("POLYGON_FETCH_RETRIES", "4"))):
                if not wait_turn():
                    continue
                params = (
                    {"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": key}
                    if next_url == url
                    else None
                )
                r = requests.get(next_url, params=params, timeout=60)
                if r.status_code == 429:
                    note_rate_limit()
                    continue
                if r.status_code != 200:
                    log.warning("[DATA] Polygon minute HTTP %s %s", r.status_code, ticker)
                    break
                body = r.json()
                for b in body.get("results") or []:
                    ts.append(pd.to_datetime(b["t"], unit="ms", utc=True))
                    rows.append(
                        {
                            "Open": b["o"],
                            "High": b["h"],
                            "Low": b["l"],
                            "Close": b["c"],
                            "Volume": b.get("v", 0),
                        }
                    )
                next_url = body.get("next_url")
                if next_url and "apiKey=" not in next_url:
                    sep = "&" if "?" in next_url else "?"
                    next_url = f"{next_url}{sep}apiKey={key}"
                break
            else:
                break
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows, index=pd.DatetimeIndex(ts))
        df = df.sort_index()
        df = df[~df.index.duplicated(keep="last")]
        df["Adj Close"] = df["Close"]
        df["TradeCount"] = 0.0
        df["VWAP"] = df["Close"]
        return df
    except Exception as e:
        log.warning("[DATA] Polygon minute failed %s: %s", ticker, e)
        return pd.DataFrame()


def fetch_polygon_daily(ticker: str, start: str, end: str | None = None) -> pd.DataFrame:
    key = os.getenv("POLYGON_API_KEY", "").strip()
    if not key:
        return pd.DataFrame()
    try:
        from data_platform.polygon_throttle import note_rate_limit, wait_turn
        from symbol_aliases import price_feed_symbol

        import requests

        api_sym = price_feed_symbol(ticker)
        end_d = end or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        url = f"https://api.polygon.io/v2/aggs/ticker/{api_sym}/range/1/day/{start}/{end_d}"
        for attempt in range(int(os.getenv("POLYGON_FETCH_RETRIES", "4"))):
            if not wait_turn():
                continue
            r = requests.get(
                url,
                params={"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": key},
                timeout=float(os.getenv("POLYGON_HTTP_TIMEOUT_SEC", "8")),
            )
            if r.status_code == 429:
                note_rate_limit()
                log.debug("[DATA] Polygon 429 %s (attempt %d)", ticker, attempt + 1)
                continue
            r.raise_for_status()
            res = r.json().get("results") or []
            if not res:
                return pd.DataFrame()
            rows = []
            ts = []
            for b in res:
                ts.append(pd.to_datetime(b["t"], unit="ms"))
                rows.append(
                    {
                        "Open": b["o"],
                        "High": b["h"],
                        "Low": b["l"],
                        "Close": b["c"],
                        "Volume": b.get("v", 0),
                    }
                )
            df = pd.DataFrame(rows, index=pd.DatetimeIndex(ts))
            return _naive_index(df)
        log.warning("[DATA] Polygon exhausted retries %s", ticker)
        return pd.DataFrame()
    except Exception as e:
        log.warning("[DATA] Polygon failed %s: %s", ticker, e)
        return pd.DataFrame()


def cross_verify_close(
    ticker: str,
    start: str,
    end: str | None = None,
    rel_tol: float = 0.02,
) -> tuple[pd.DataFrame, dict]:
    """
    Primary via SourceRotator (polygon→alpaca→yahoo on 429); cross-check others.
    Returns (primary_df, integrity_report).
    """
    from data_platform.source_rotator import fetch_daily_rotated, note_limited

    y, src = fetch_daily_rotated(ticker, start, end, min_rows=1)
    rep: dict = {
        "primary_source": src,
        "yahoo_rows": len(y),
        "alpaca_ok": False,
        "polygon_ok": False,
        "close_mismatch": None,
    }
    if y.empty:
        return y, rep
    y_close = float(y["Close"].iloc[-1]) if "Close" in y.columns else float(y.iloc[-1, 0])

    a = fetch_alpaca_daily(ticker, start, end)
    if not a.empty:
        rep["alpaca_ok"] = True
        a_close = float(a["Close"].iloc[-1])
        if abs(a_close - y_close) / max(y_close, 1e-9) > rel_tol:
            rep["close_mismatch"] = {"alpaca": a_close, "primary": y_close}

    p = fetch_polygon_daily(ticker, start, end)
    if not p.empty:
        rep["polygon_ok"] = True
        p_close = float(p["Close"].iloc[-1])
        if abs(p_close - y_close) / max(y_close, 1e-9) > rel_tol:
            rep["close_mismatch"] = rep.get("close_mismatch") or {"polygon": p_close, "primary": y_close}

    return y, rep


def fetch_daily_best(ticker: str, start: str, end: str | None = None) -> pd.DataFrame:
    """Public helper: rotated multi-source daily OHLCV."""
    from data_platform.source_rotator import fetch_daily_rotated

    df, _src = fetch_daily_rotated(ticker, start, end)
    return df
