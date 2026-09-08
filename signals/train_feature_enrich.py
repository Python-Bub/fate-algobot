"""Causal training / inference features: Undercut & Rally, FRED spread, historical news.

Merged in `feature_engineering.build_features` so **train and live** share columns.
Toggle with `USE_TRAIN_SIGNAL_FEATURES` (default on).

- **FRED** `fred_spread_10y2y` — needs `FRED_API_KEY`.
- **U&R** `ur_score` — toggle `TRAIN_COMPUTE_UR`.
- **News / transcripts** — `signals/train_news_history.py` (Finnhub company-news backfill +
  optional dated lines in `data/replay/transcripts/{SYM}.jsonl`). Toggle `USE_TRAIN_NEWS_HISTORY`.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

from utils import log


def _b(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes")


def _ur_score_series(df: pd.DataFrame) -> pd.Series:
    cols = ("Open", "High", "Low", "Close", "Volume")
    if not all(c in df.columns for c in cols):
        return pd.Series(0.0, index=df.index)

    from signals.undercut_rally import detect_undercut_rally

    max_win = int(os.getenv("TRAIN_UR_MAX_LOOKBACK_BARS", "140"))
    n = len(df)
    out = np.zeros(n, dtype=np.float64)
    # First ~25 bars: pattern not meaningful
    min_i = max(25, int(os.getenv("TRAIN_UR_MIN_BAR", "25")))
    for i in range(min_i, n):
        lo = max(0, i - max_win)
        sub = df.iloc[lo : i + 1][list(cols)]
        try:
            ur = detect_undercut_rally(sub)
            out[i] = float(ur.score)
        except Exception:
            out[i] = 0.0
    return pd.Series(out, index=df.index, dtype=np.float64)


def enrich_train_signals(
    df: pd.DataFrame, start_date: str, end_date: str | None, ticker: str = ""
) -> pd.DataFrame:
    if not _b("USE_TRAIN_SIGNAL_FEATURES", True):
        out = df.copy()
        if "ur_score" not in out.columns:
            out["ur_score"] = 0.0
        if "fred_spread_10y2y" not in out.columns:
            out["fred_spread_10y2y"] = 0.0
        return out

    out = df.copy()
    idx = pd.DatetimeIndex(pd.to_datetime(out.index, errors="coerce"))
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    out.index = idx

    # --- FRED spread (historical, merged by calendar date) ---
    spread_s = pd.Series(0.0, index=out.index, dtype=np.float64)
    try:
        from signals.fred_macro import fred_spread_daily_series

        end_s = end_date or str(out.index[-1].date()) if len(out) else start_date
        raw = fred_spread_daily_series(str(start_date)[:10], str(end_s)[:10])
        if raw is not None and not raw.empty:
            ridx = pd.DatetimeIndex(raw.index)
            if getattr(ridx, "tz", None) is not None:
                ridx = ridx.tz_localize(None)
            raw = raw.copy()
            raw.index = ridx
            spread_s = raw.reindex(out.index).ffill().fillna(0.0).astype(np.float64)
    except Exception as e:
        log.debug("[TRAIN_FE] FRED spread merge skipped: %s", e)

    out["fred_spread_10y2y"] = spread_s

    # --- Undercut & Rally (causal path) ---
    if _b("TRAIN_COMPUTE_UR", True):
        try:
            out["ur_score"] = _ur_score_series(out)
        except Exception as e:
            log.warning("[TRAIN_FE] ur_score series failed: %s", e)
            out["ur_score"] = 0.0
    else:
        out["ur_score"] = 0.0

    # --- Historical Finnhub news + optional dated transcripts (train + live feature parity) ---
    try:
        from signals.train_news_history import enrich_news_history_features

        sym = (ticker or "").strip()
        if sym:
            out = enrich_news_history_features(out, sym, start_date, end_date)
    except Exception as e:
        log.debug("[TRAIN_FE] news history enrich skipped: %s", e)
        for c in ("news_sent_roll_5d", "news_intensity_roll_5d", "news_sent_trend_10d", "transcript_sent_roll_5d"):
            if c not in out.columns:
                out[c] = 0.0

    # --- Industry co-movement (50-bucket beta, factor tilts, Nasdaq alignment) ---
    try:
        from analytics.industry_comovement import enrich_industry_comovement

        sym = (ticker or "").strip()
        if sym:
            out = enrich_industry_comovement(out, sym, start_date, end_date)
    except Exception as e:
        log.debug("[TRAIN_FE] industry co-movement skipped: %s", e)
        for c in (
            "industry_ret_1d",
            "industry_ret_5d",
            "industry_beta_60",
            "industry_residual_1d",
            "industry_z_20",
            "nasdaq_beta_60",
            "factor_rate_tilt",
            "factor_expansion_tilt",
            "industry_sympathy_score",
            "industry_leader_momentum",
        ):
            if c not in out.columns:
                out[c] = 0.0

    # --- Industry pipeline feature weights (per-symbol ML emphasis) ---
    try:
        from analytics.industries.pipeline import enrich_training_feature_weights

        sym = (ticker or "").strip()
        if sym:
            out = enrich_training_feature_weights(out, sym)
    except Exception as e:
        log.debug("[TRAIN_FE] industry pipeline weights skipped: %s", e)
        for c in ("fpw_factor_rate", "fpw_factor_expansion", "fpw_industry_sympathy", "fpw_combined_tilt"):
            if c not in out.columns:
                out[c] = 1.0

    return out


def enrich_training_features(
    df: pd.DataFrame, ticker: str, start_date: str, end_date: str | None = None
) -> pd.DataFrame:
    """Alias used by industry anchors + project wiring."""
    return enrich_train_signals(df, start_date, end_date, ticker=ticker)
