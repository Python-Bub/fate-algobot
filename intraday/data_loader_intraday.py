"""Fetch minute bars: Alpaca → Polygon fallback (no Yahoo — avoids rate limits)."""

from __future__ import annotations

import datetime as dt
import os
import time
from pathlib import Path

import pandas as pd
import requests

from dotenv import load_dotenv

load_dotenv()

from symbol_aliases import price_feed_symbol
from utils import log

CACHE_DIR = Path("data/intraday")
ALPACA_BASE = os.getenv("ALPACA_DATA_URL", "https://data.alpaca.markets").rstrip("/")
DEFAULT_FEED = os.getenv("ALPACA_INTRADAY_FEED", "iex")


def _auth_headers() -> dict[str, str]:
    key = os.getenv("ALPACA_API_KEY", "")
    sec = os.getenv("ALPACA_SECRET_KEY") or os.getenv("ALPACA_API_SECRET", "")
    if not key or not sec:
        raise RuntimeError(
            "Alpaca credentials missing — set ALPACA_API_KEY and ALPACA_SECRET_KEY in .env."
        )
    return {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec}


def _cache_path(symbol: str, timeframe: str, start: str) -> Path:
    safe = symbol.upper().replace("/", "_")
    return CACHE_DIR / timeframe / f"{safe}_{start}.parquet"


def _normalize_minute_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    if not isinstance(out.index, pd.DatetimeIndex):
        if "t" in out.columns:
            out["t"] = pd.to_datetime(out["t"], utc=True, errors="coerce")
            out = out.dropna(subset=["t"]).set_index("t")
    if out.index.tz is None:
        out.index = out.index.tz_localize("UTC")
    else:
        out.index = out.index.tz_convert("UTC")
    rename = {
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume",
        "vwap": "VWAP",
        "trades": "TradeCount",
    }
    for old, new in rename.items():
        if old in out.columns and new not in out.columns:
            out[new] = out[old]
    for col in ("Open", "High", "Low", "Close"):
        if col not in out.columns:
            return pd.DataFrame()
    if "Adj Close" not in out.columns:
        out["Adj Close"] = out["Close"]
    if "Volume" not in out.columns:
        out["Volume"] = 0.0
    if "TradeCount" not in out.columns:
        out["TradeCount"] = 0.0
    if "VWAP" not in out.columns:
        out["VWAP"] = out["Close"]
    return out[["Open", "High", "Low", "Close", "Adj Close", "Volume", "TradeCount", "VWAP"]].sort_index()


def _fetch_alpaca_minute_bars(
    symbol: str,
    start: str,
    end: str,
    *,
    timeframe: str = "1Min",
    feed: str,
    rate_limit_pause_s: float = 0.10,
) -> pd.DataFrame:
    api_symbol = price_feed_symbol(symbol)
    url = f"{ALPACA_BASE}/v2/stocks/{api_symbol.upper()}/bars"
    headers = _auth_headers()
    out_rows: list[dict] = []
    page_token: str | None = None
    fetched_pages = 0
    consecutive_429 = 0
    max_429 = int(os.getenv("INTRADAY_MAX_429_RETRIES", "40"))
    while True:
        params = {
            "timeframe": timeframe,
            "start": f"{start}T00:00:00Z",
            "end": f"{end}T23:59:59Z",
            "limit": 10_000,
            "adjustment": "all",
            "feed": feed,
        }
        if page_token:
            params["page_token"] = page_token
        try:
            r = requests.get(url, headers=headers, params=params, timeout=30)
        except requests.RequestException as e:
            log.warning("[INTRADAY] %s request error (%s): %s", symbol, feed, e)
            break
        if r.status_code == 429:
            consecutive_429 += 1
            if consecutive_429 > max_429:
                log.warning("[INTRADAY] %s Alpaca %s rate limit — %d bars so far", symbol, feed, len(out_rows))
                break
            time.sleep(min(2.0 * consecutive_429, 60.0))
            continue
        consecutive_429 = 0
        if r.status_code != 200:
            log.warning("[INTRADAY] %s Alpaca %s HTTP %s: %s", symbol, feed, r.status_code, r.text[:200])
            break
        body = r.json()
        bars = body.get("bars") or []
        for b in bars:
            out_rows.append(
                {
                    "t": b.get("t"),
                    "open": b.get("o"),
                    "high": b.get("h"),
                    "low": b.get("l"),
                    "close": b.get("c"),
                    "volume": b.get("v"),
                    "trades": b.get("n"),
                    "vwap": b.get("vw"),
                }
            )
        page_token = body.get("next_page_token")
        fetched_pages += 1
        if not page_token:
            break
        if fetched_pages > 200:
            log.warning("[INTRADAY] %s page cap reached", symbol)
            break
        time.sleep(rate_limit_pause_s)

    if not out_rows:
        return pd.DataFrame()
    df = pd.DataFrame(out_rows)
    df["t"] = pd.to_datetime(df["t"], utc=True, errors="coerce")
    df = df.dropna(subset=["t"]).set_index("t")
    return _normalize_minute_df(df)


def fetch_minute_bars(
    symbol: str,
    start: str,
    end: str | None = None,
    timeframe: str = "1Min",
    feed: str | None = None,
    use_cache: bool | None = None,
    rate_limit_pause_s: float = 0.10,
) -> pd.DataFrame:
    """Alpaca minute bars, then Polygon full-tape fallback — never Yahoo."""
    if end is None:
        end = dt.datetime.utcnow().strftime("%Y-%m-%d")
    min_bars = int(os.getenv("INTRADAY_MIN_BARS", "800"))
    if use_cache is None:
        use_cache = os.getenv("INTRADAY_USE_CACHE", "true").lower() in ("1", "true", "yes")

    feeds = [feed or DEFAULT_FEED]
    if os.getenv("ALPACA_HAS_SIP", "false").lower() in ("1", "true", "yes"):
        alt = os.getenv("ALPACA_INTRADAY_FEED_ALT", "sip").strip()
        if alt and alt not in feeds:
            feeds.append(alt)

    cache = _cache_path(symbol, timeframe, f"{start}_{end}_multi")
    if use_cache and cache.is_file():
        try:
            cached = pd.read_parquet(cache)
            if len(cached) >= min_bars:
                return cached
        except Exception as e:
            log.debug("[INTRADAY] cache read failed for %s: %s", symbol, e)

    best = pd.DataFrame()
    for fd in feeds:
        df = _fetch_alpaca_minute_bars(
            symbol, start, end, timeframe=timeframe, feed=fd, rate_limit_pause_s=rate_limit_pause_s
        )
        if len(df) > len(best):
            best = df
        if len(best) >= min_bars:
            log.info("[INTRADAY] %s Alpaca/%s → %d bars", symbol, fd, len(best))
            break

    poly_ok = os.getenv("INTRADAY_USE_POLYGON_FALLBACK", "true").lower() in ("1", "true", "yes")
    if len(best) < min_bars and poly_ok and os.getenv("POLYGON_API_KEY", "").strip():
        from multi_source_data import fetch_polygon_minute_bars

        pdf = fetch_polygon_minute_bars(symbol, start, end)
        pdf = _normalize_minute_df(pdf)
        if len(pdf) > len(best):
            log.info("[INTRADAY] %s Polygon minute fallback → %d bars (was %d)", symbol, len(pdf), len(best))
            best = pdf

    if not best.empty:
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            if use_cache and len(best) >= min_bars:
                best.to_parquet(cache)
        except Exception as e:
            log.debug("[INTRADAY] cache write failed for %s: %s", symbol, e)
    return best


def resample_to_hour(minute_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate 1-minute bars to 60-minute bars (label = bar-close)."""
    if minute_df.empty:
        return minute_df
    agg = {
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Adj Close": "last",
        "Volume": "sum",
        "TradeCount": "sum",
        "VWAP": "mean",
    }
    return minute_df.resample("60min").agg(agg).dropna(subset=["Close"])
