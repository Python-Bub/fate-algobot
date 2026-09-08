"""FRED macro snapshot (10y–2y spread, levels) with disk cache.

Requires `FRED_API_KEY` in the environment. If missing, returns neutral zeros.

Series:
- DGS10 — 10-Year Treasury Constant Maturity Rate
- DGS2  — 2-Year Treasury Constant Maturity Rate
- VIXCLS — optional (CBOE VIX); falls back to neutral if unavailable

Env:
- FRED_CACHE_SECONDS  default 21600 (6h)
- FRED_MACRO_FILE     default data/cache/fred_macro.json
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from utils import log

_FRED_URL = "https://api.stlouisfed.org/fred/series/observations"
_FRED_HEADERS = {
    "User-Agent": os.getenv("FRED_USER_AGENT", "FATE_AlgoBot/1.0 (fred-macro)"),
}
# Yahoo yield proxies when FRED API is blocked or key invalid (10y−5y curve proxy).
_YF_YIELD = {"DGS10": "^TNX", "DGS2": "^FVX", "VIXCLS": "^VIX"}
_MEM: dict[str, Any] = {"t": 0.0, "bundle": None}


def _cache_path() -> Path:
    return Path(os.getenv("FRED_MACRO_FILE", "data/cache/fred_macro.json"))


def _yf_latest_yield(series_id: str) -> float | None:
    if os.getenv("FRED_YFINANCE_FALLBACK", "true").lower() not in ("1", "true", "yes"):
        return None
    sym = _YF_YIELD.get(series_id)
    if not sym:
        return None
    try:
        from data_platform.market_prices import fetch_period

        df = fetch_period(sym, period="10d", interval="1d")
        if df is None or df.empty:
            return None
        close = df["Close"].dropna()
        if close.empty:
            return None
        return float(close.to_numpy()[-1])
    except Exception as e:
        log.debug("[FRED] yfinance %s failed: %s", series_id, e)
        return None


def _fetch_series_fred(series_id: str, api_key: str, limit: int = 3) -> float | None:
    try:
        r = requests.get(
            _FRED_URL,
            params={
                "series_id": series_id,
                "api_key": api_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": limit,
            },
            headers=_FRED_HEADERS,
            timeout=float(os.getenv("FRED_HTTP_TIMEOUT", "12")),
        )
        if r.status_code == 200:
            obs = (r.json() or {}).get("observations") or []
            for row in obs:
                v = row.get("value")
                if v in (None, ".", ""):
                    continue
                return float(v)
        elif r.status_code != 403:
            r.raise_for_status()
    except Exception as e:
        log.debug("[FRED] %s fetch failed: %s", series_id, e)
    return None


def _fetch_series(series_id: str, api_key: str, limit: int = 3) -> tuple[float | None, bool]:
    """Return (value, used_yfinance_fallback)."""
    v = _fetch_series_fred(series_id, api_key, limit=limit)
    if v is not None:
        return v, False
    yv = _yf_latest_yield(series_id)
    if yv is not None:
        log.info("[FRED] %s via yfinance proxy (%s)", series_id, _YF_YIELD.get(series_id))
        return yv, True
    return None, False


def get_macro_bundle(force_refresh: bool = False) -> dict[str, Any]:
    """Return latest macro fields + a compact `macro_score` in [-1, 1]."""
    ttl = float(os.getenv("FRED_CACHE_SECONDS", str(6 * 3600)))
    now = time.time()
    if (
        not force_refresh
        and _MEM["bundle"] is not None
        and now - float(_MEM["t"]) < ttl
    ):
        return dict(_MEM["bundle"])

    key = os.getenv("FRED_API_KEY", "").strip()
    neutral = {
        "ok": False,
        "dgs10": None,
        "dgs2": None,
        "spread_10y2y": None,
        "vix": None,
        "macro_score": 0.0,
        "pmi_score": 0.0,
        "rate_shock_20d": 0.0,
        "source": "no_key",
        "fetched_at_utc": None,
    }
    if not key:
        _MEM["t"] = now
        _MEM["bundle"] = neutral
        return dict(neutral)

    d10, yf10 = _fetch_series("DGS10", key)
    d2, yf2 = _fetch_series("DGS2", key)
    vix, _yf_vix = _fetch_series("VIXCLS", key)
    pmi_raw, _ = _fetch_series(os.getenv("FRED_PMI_SERIES", "MANEMP"), key, limit=6)
    d10_prev, _ = _fetch_series("DGS10", key, limit=25)
    spread = None
    if d10 is not None and d2 is not None:
        spread = float(d10) - float(d2)
    if yf10 or yf2:
        source = "yfinance_10y5y_proxy"
    else:
        source = "fred"

    # PMI proxy: MANEMP momentum scaled to [-1,1] (expansion when rising)
    pmi_score = 0.0
    if pmi_raw is not None:
        pmi_score = float(max(-1.0, min(1.0, (float(pmi_raw) - 150000.0) / 50000.0)))
    rate_shock_20d = 0.0
    if d10 is not None and d10_prev is not None:
        rate_shock_20d = float(d10) - float(d10_prev)

    # macro_score: steep curve (wide positive spread) → risk-on tilt; inverted → negative
    score = 0.0
    if spread is not None:
        score += float(max(-1.0, min(1.0, spread / 1.5)))
    if vix is not None:
        score += float(max(-0.5, min(0.5, (25.0 - vix) / 40.0)))
    score = float(max(-1.0, min(1.0, score)))

    out = {
        "ok": spread is not None,
        "dgs10": d10,
        "dgs2": d2,
        "spread_10y2y": spread,
        "vix": vix,
        "pmi_score": pmi_score,
        "rate_shock_20d": rate_shock_20d,
        "macro_score": score,
        "source": source if spread is not None else "no_data",
        "fetched_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
    }

    try:
        p = _cache_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(out, indent=2), encoding="utf-8")
    except Exception:
        pass

    _MEM["t"] = now
    _MEM["bundle"] = out
    return dict(out)


def _fetch_fred_observations_range(series_id: str, start: str, end: str) -> pd.Series:
    """Daily FRED observations between start and end (inclusive), ascending index."""
    key = os.getenv("FRED_API_KEY", "").strip()
    if not key:
        return pd.Series(dtype=float)
    try:
        r = requests.get(
            _FRED_URL,
            params={
                "series_id": series_id,
                "api_key": key,
                "file_type": "json",
                "observation_start": start[:10],
                "observation_end": end[:10],
                "sort_order": "asc",
            },
            headers=_FRED_HEADERS,
            timeout=float(os.getenv("FRED_HTTP_TIMEOUT", "30")),
        )
        r.raise_for_status()
        obs = (r.json() or {}).get("observations") or []
        pts: list[tuple[pd.Timestamp, float]] = []
        for row in obs:
            d = row.get("date")
            v = row.get("value")
            if not d or v in (None, ".", ""):
                continue
            try:
                pts.append((pd.Timestamp(str(d)), float(v)))
            except Exception:
                continue
        if not pts:
            return pd.Series(dtype=float)
        idx, vals = zip(*pts)
        return pd.Series(vals, index=pd.DatetimeIndex(idx)).sort_index()
    except Exception as e:
        log.debug("[FRED] range fetch %s failed: %s", series_id, e)
        return pd.Series(dtype=float)


def _yf_yield_daily_series(series_id: str, start: str, end: str) -> pd.Series:
    sym = _YF_YIELD.get(series_id)
    if not sym:
        return pd.Series(dtype=float)
    try:
        import yfinance as yf

        df = yf.download(
            sym,
            start=start[:10],
            end=end[:10],
            interval="1d",
            progress=False,
            auto_adjust=True,
        )
        if df is None or df.empty:
            return pd.Series(dtype=float)
        close = df["Close"].dropna()
        close.index = pd.DatetimeIndex(close.index).tz_localize(None)
        return close.astype(float)
    except Exception as e:
        log.debug("[FRED] yfinance range %s failed: %s", series_id, e)
        return pd.Series(dtype=float)


def fred_spread_daily_series(start: str, end: str) -> pd.Series:
    """10y − 2y Treasury spread by calendar date (merge with ffill onto equity index)."""
    d10 = _fetch_fred_observations_range("DGS10", start, end)
    d2 = _fetch_fred_observations_range("DGS2", start, end)
    if d10.empty:
        d10 = _yf_yield_daily_series("DGS10", start, end)
    if d2.empty:
        d2 = _yf_yield_daily_series("DGS2", start, end)
    if d10.empty or d2.empty:
        return pd.Series(dtype=float)
    both = pd.DataFrame({"g10": d10, "g2": d2}).sort_index().ffill().bfill()
    sp = (both["g10"] - both["g2"]).dropna()
    return sp.astype(float)
