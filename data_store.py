"""
Append-only-ish OHLCV cache on disk (Parquet when pyarrow is available, else CSV).

Large historical backfills can reach terabytes only if you intentionally retain
high-frequency data for the full universe; daily bars for all US listings are
far smaller but still substantial over decades.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from utils import log

CACHE_ROOT = Path(os.getenv("PRICE_CACHE_DIR", "data/cache/prices"))


def _path_for(ticker: str) -> Path:
    safe = ticker.replace("/", "_")
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    return CACHE_ROOT / f"{safe}.parquet"


def _path_csv(ticker: str) -> Path:
    safe = ticker.replace("/", "_")
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    return CACHE_ROOT / f"{safe}.csv"


def _naive_index_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    idx = pd.to_datetime(out.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    out.index = idx
    return out


def load_cached_ohlcv(ticker: str) -> pd.DataFrame | None:
    p = _path_for(ticker)
    if p.is_file():
        try:
            return _naive_index_df(pd.read_parquet(p))
        except Exception:
            log.warning("[CACHE] Parquet read failed for %s; try CSV", ticker)
    c = _path_csv(ticker)
    if c.is_file():
        df = pd.read_csv(c, index_col=0, parse_dates=True)
        return _naive_index_df(df)
    return None


def merge_and_save(ticker: str, new_df: pd.DataFrame) -> None:
    try:
        from data_platform.network_data import save_price_cache
    except ImportError:
        save_price_cache = lambda: os.getenv("USE_PRICE_CACHE", "false").lower() in ("1", "true", "yes")  # noqa: E731
    if not save_price_cache():
        return
    if new_df is None or new_df.empty:
        return
    out = new_df.copy()
    idx = pd.to_datetime(out.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    out.index = idx

    old = load_cached_ohlcv(ticker)
    if old is not None and not old.empty:
        oidx = pd.to_datetime(old.index)
        if getattr(oidx, "tz", None) is not None:
            oidx = oidx.tz_localize(None)
        old = old.copy()
        old.index = oidx
        combined = pd.concat([old, out])
        combined = combined[~combined.index.duplicated(keep="last")].sort_index()
    else:
        combined = out.sort_index()

    try:
        combined.to_parquet(_path_for(ticker))
    except Exception:
        combined.to_csv(_path_csv(ticker))
        log.info("[CACHE] Saved CSV for %s (install pyarrow for Parquet)", ticker)
