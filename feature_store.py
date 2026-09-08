"""
FeatureStore: lags, z-scores, relative strength vs benchmark (SPY), VWAP, ATR,
Accumulation/Distribution, multi-timeframe placeholders (daily trend flags).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from utils import log


def _zscore(s: pd.Series, win: int = 60) -> pd.Series:
    minp = min(win, max(2, win // 10))
    m = s.rolling(win, min_periods=minp).mean()
    sd = s.rolling(win, min_periods=minp).std().replace(0, np.nan)
    return ((s - m) / sd).fillna(0)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    h, l, c = df["High"], df["Low"], df["Close"]
    prev_c = c.shift(1)
    tr = pd.concat([(h - l), (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=period).mean().fillna(0)


def vwap_daily(df: pd.DataFrame) -> pd.Series:
    """Approximate session VWAP using typical price * volume / cum vol per day."""
    tp = (df["High"] + df["Low"] + df["Close"]) / 3.0
    vol = df["Volume"].replace(0, np.nan).fillna(1.0)
    idx = df.index
    day = pd.Series(idx.date, index=idx)
    pv = tp * vol
    cum_pv = pv.groupby(day).cumsum()
    cum_v = vol.groupby(day).cumsum()
    return (cum_pv / cum_v).ffill().fillna(tp)


def accumulation_distribution(df: pd.DataFrame) -> pd.Series:
    clv = ((df["Close"] - df["Low"]) - (df["High"] - df["Close"])) / (df["High"] - df["Low"]).replace(0, np.nan)
    clv = clv.fillna(0) * df["Volume"].fillna(0)
    return clv.cumsum()


def relative_strength_vs_benchmark(stock_ret: pd.Series, bench_ret: pd.Series, win: int = 20) -> pd.Series:
    """Stock cumulative return / benchmark cumulative return over window."""

    def _cumret(r: pd.Series) -> pd.Series:
        return r.add(1.0).rolling(win, min_periods=max(3, win // 4)).apply(lambda x: float(np.prod(x) - 1.0), raw=True)

    cr_s = _cumret(stock_ret)
    cr_b = _cumret(bench_ret.reindex(stock_ret.index).fillna(0.0))
    rs = cr_s / cr_b.replace(0, np.nan)
    return rs.replace([np.inf, -np.inf], np.nan).fillna(1.0)


def enrich_features(
    df: pd.DataFrame,
    bench_df: pd.DataFrame | None = None,
    rsi_col: str = "rsi",
) -> pd.DataFrame:
    """
    Expects columns Open, High, Low, Close, Volume, returns, rsi (optional).
    Adds: lagged returns, z-scores, rs_spy, vwap, atr, ad_line, volume_ratio, ema signals.
    """
    if df.empty:
        return df
    out = df.copy()
    r = out["returns"] if "returns" in out.columns else out["Close"].pct_change().fillna(0)
    out["returns"] = r

    for lag in (1, 2, 5):
        out[f"ret_lag_{lag}"] = r.shift(lag).fillna(0)

    out["ret_z"] = _zscore(r, int(pd.Series([60, len(out) // 4]).min()))
    if rsi_col in out.columns:
        out["rsi_z"] = _zscore(out[rsi_col], 60)

    out["atr_14"] = atr(out, 14)
    out["vwap_est"] = vwap_daily(out)
    out["ad_line"] = accumulation_distribution(out)
    vol_ma = out["Volume"].rolling(20, min_periods=5).mean()
    out["volume_ratio"] = (out["Volume"] / vol_ma.replace(0, np.nan)).fillna(0)

    out["ema_20"] = out["Close"].ewm(span=20, adjust=False).mean()
    out["ema_50"] = out["Close"].ewm(span=50, adjust=False).mean()
    out["daily_bull_trend"] = (out["ema_20"] > out["ema_50"]).astype(int)

    if bench_df is not None and not bench_df.empty and "Close" in bench_df.columns:
        bclose = bench_df["Close"].reindex(out.index, method="ffill").ffill()
        br = bclose.pct_change().fillna(0)
        out["rs_spy"] = relative_strength_vs_benchmark(r, br, 20)
    else:
        out["rs_spy"] = 1.0

    out.replace([np.inf, -np.inf], 0, inplace=True)
    log.info("[FEATURE_STORE] enriched shape=%s", out.shape)
    return out


def volume_confirmed(row: pd.Series, mult: float = 1.5) -> bool:
    return float(row.get("volume_ratio", 0)) >= mult
