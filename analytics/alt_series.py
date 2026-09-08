"""Cached daily closes for alt-asset math (crypto, metals, energy, FX, rates).

Network-first, disk-cheap: Yahoo/Alpaca already have these series. We cache
in-process for a few minutes so rank + HFT do not refetch SI=F on every ticker.
"""

from __future__ import annotations

import time
from typing import Callable

import pandas as pd

_CACHE: dict[str, tuple[float, pd.Series]] = {}
_TTL_SEC = 900.0

FetchFn = Callable[[str, int], pd.Series | None]


def _default_fetch(symbol: str, days: int) -> pd.Series | None:
    try:
        from data_platform.market_prices import fetch_daily

        end = pd.Timestamp.utcnow().strftime("%Y-%m-%d")
        start = (pd.Timestamp.utcnow() - pd.Timedelta(days=int(days))).strftime("%Y-%m-%d")
        df = fetch_daily(symbol, start, end)
        if df is None or df.empty:
            return None
        col = "Close" if "Close" in df.columns else df.columns[0]
        s = pd.Series(df[col]).astype(float).dropna()
        s.index = pd.to_datetime(s.index, utc=True, errors="coerce")
        return s[s > 0]
    except Exception:
        return None


def daily_closes(
    symbol: str,
    *,
    days: int = 400,
    fetch: FetchFn | None = None,
    ttl: float | None = None,
) -> pd.Series:
    """Latest daily closes for `symbol`. Empty series if the feed is down."""
    key = f"{symbol.strip().upper()}|{int(days)}"
    now = time.time()
    ttl_s = float(_TTL_SEC if ttl is None else ttl)
    fn = fetch or _default_fetch
    if fetch is None:
        hit = _CACHE.get(key)
        if hit and now - hit[0] < ttl_s:
            return hit[1]
    try:
        s = fn(symbol, int(days))
    except Exception:
        s = None
    if s is None:
        s = pd.Series(dtype=float)
    else:
        s = pd.Series(s).astype(float).dropna()
    if fetch is None:
        _CACHE[key] = (now, s)
    return s


def ret_n(closes: pd.Series | None, n: int) -> float:
    if closes is None or len(closes) < n + 1:
        return 0.0
    a = float(closes.iloc[-1])
    b = float(closes.iloc[-(n + 1)])
    if b <= 0 or a <= 0:
        return 0.0
    return a / b - 1.0


def realized_vol(closes: pd.Series | None, n: int) -> float:
    if closes is None or len(closes) < n + 2:
        return 0.0
    r = pd.Series(closes).astype(float).pct_change().dropna().iloc[-n:]
    if r.empty:
        return 0.0
    return float(r.std(ddof=0))


def donchian_breakout(closes: pd.Series | None, n: int = 20, *, tol: float = 0.002) -> bool:
    if closes is None or len(closes) < n + 1:
        return False
    window = pd.Series(closes).astype(float).iloc[-(n + 1) : -1]
    last = float(closes.iloc[-1])
    hi = float(window.max())
    if hi <= 0:
        return False
    return last >= hi * (1.0 - float(tol))


def rolling_z(closes: pd.Series | None, n: int = 60) -> float:
    if closes is None or len(closes) < n:
        return 0.0
    w = pd.Series(closes).astype(float).iloc[-n:]
    mu = float(w.mean())
    sd = float(w.std(ddof=0))
    if sd <= 1e-12:
        return 0.0
    return float((float(w.iloc[-1]) - mu) / sd)


def aligned_ratio(num: pd.Series | None, den: pd.Series | None) -> pd.Series:
    if num is None or den is None or num.empty or den.empty:
        return pd.Series(dtype=float)
    a = pd.Series(num).astype(float)
    b = pd.Series(den).astype(float)
    a.index = pd.to_datetime(a.index, utc=True, errors="coerce")
    b.index = pd.to_datetime(b.index, utc=True, errors="coerce")
    j = pd.concat([a.rename("n"), b.rename("d")], axis=1).dropna()
    j = j[j["d"] > 0]
    if j.empty:
        return pd.Series(dtype=float)
    return (j["n"] / j["d"]).astype(float)
