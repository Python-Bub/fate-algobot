"""Expanded predictive feature families for cross-sectional robustness."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _safe_div(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a / b.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)


def add_volatility_regime(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    r = out["returns"].astype(float).fillna(0.0)
    out["vol_10"] = r.rolling(10, min_periods=5).std().fillna(0.0)
    out["vol_30"] = r.rolling(30, min_periods=10).std().fillna(0.0)
    out["vol_regime_ratio"] = _safe_div(out["vol_10"], out["vol_30"]).fillna(1.0).clip(0.0, 8.0)
    out["vol_of_vol_20"] = out["vol_10"].rolling(20, min_periods=5).std().fillna(0.0)
    out["tail_risk_30"] = r.rolling(30, min_periods=10).quantile(0.05).fillna(0.0)
    return out


def add_event_decay_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    dte = out.get("days_to_earnings", pd.Series(np.zeros(len(out)), index=out.index)).astype(float)
    out["earnings_decay"] = np.exp(-np.abs(dte) / 5.0)
    out["event_pre_window"] = ((dte >= 0) & (dte <= 2)).astype(float)
    out["event_post_window"] = ((dte < 0) & (dte >= -3)).astype(float)
    out["event_dte_le1"] = ((dte >= 0) & (dte <= 1)).astype(float)
    sent = out.get("sentiment", pd.Series(np.zeros(len(out)), index=out.index)).astype(float)
    out["sentiment_decay_3"] = sent.ewm(span=3, adjust=False).mean()
    out["sentiment_decay_10"] = sent.ewm(span=10, adjust=False).mean()
    out["sentiment_impulse"] = (out["sentiment_decay_3"] - out["sentiment_decay_10"]).fillna(0.0)
    return out


def add_microstructure_proxies(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    c = out["Close"].astype(float)
    h = out["High"].astype(float)
    l = out["Low"].astype(float)
    v = out["Volume"].astype(float).replace(0, np.nan)
    out["intraday_spread"] = _safe_div(h - l, c).fillna(0.0).clip(0.0, 1.0)
    out["close_loc_in_range"] = _safe_div(c - l, (h - l)).fillna(0.5).clip(0.0, 1.0)
    out["turnover_proxy"] = (c * v).fillna(0.0)
    out["turnover_z_20"] = (
        (out["turnover_proxy"] - out["turnover_proxy"].rolling(20, min_periods=5).mean())
        / (out["turnover_proxy"].rolling(20, min_periods=5).std() + 1e-9)
    ).fillna(0.0).clip(-10, 10)
    out["range_compression_5"] = _safe_div(
        out["intraday_spread"].rolling(5, min_periods=3).mean(),
        out["intraday_spread"].rolling(20, min_periods=5).mean(),
    ).fillna(1.0).clip(0.0, 10.0)
    return out


def add_sequence_state_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    r = out["returns"].astype(float).fillna(0.0)
    out["trend_state_5"] = np.sign(r.rolling(5, min_periods=3).sum()).fillna(0.0)
    out["trend_state_20"] = np.sign(r.rolling(20, min_periods=5).sum()).fillna(0.0)
    out["regime_transition_flag"] = (out["trend_state_5"] != out["trend_state_20"]).astype(float)
    out["shock_state"] = (r.abs() > (r.rolling(60, min_periods=20).std() * 2.5)).astype(float)
    return out


def add_cross_sectional_rank_features(df: pd.DataFrame, bench_df: pd.DataFrame | None = None) -> pd.DataFrame:
    out = df.copy()
    close = out["Close"].astype(float)
    mom_20 = close.pct_change(20).fillna(0.0)
    mom_60 = close.pct_change(60).fillna(0.0)
    out["mom_20"] = mom_20
    out["mom_60"] = mom_60
    out["mom_accel"] = (mom_20 - mom_60).fillna(0.0)
    if bench_df is not None and not bench_df.empty and "Close" in bench_df.columns:
        b = bench_df["Close"].reindex(out.index, method="ffill").ffill().astype(float)
        out["beta_proxy_60"] = (
            out["returns"].rolling(60, min_periods=20).cov(b.pct_change().fillna(0.0))
            / (b.pct_change().rolling(60, min_periods=20).var() + 1e-9)
        ).fillna(1.0).clip(-5, 5)
        out["alpha_proxy_20"] = (mom_20 - b.pct_change(20).fillna(0.0)).fillna(0.0)
    else:
        out["beta_proxy_60"] = 1.0
        out["alpha_proxy_20"] = mom_20
    return out


def enrich_advanced_features(df: pd.DataFrame, bench_df: pd.DataFrame | None = None) -> pd.DataFrame:
    out = df.copy()
    out = add_volatility_regime(out)
    out = add_event_decay_features(out)
    out = add_microstructure_proxies(out)
    out = add_sequence_state_features(out)
    out = add_cross_sectional_rank_features(out, bench_df=bench_df)
    out.replace([np.inf, -np.inf], 0, inplace=True)
    out.fillna(0, inplace=True)
    return out


def advanced_feature_columns() -> list[str]:
    return [
        "vol_10",
        "vol_30",
        "vol_regime_ratio",
        "vol_of_vol_20",
        "tail_risk_30",
        "earnings_decay",
        "sentiment_decay_3",
        "sentiment_decay_10",
        "sentiment_impulse",
        "intraday_spread",
        "close_loc_in_range",
        "turnover_proxy",
        "turnover_z_20",
        "range_compression_5",
        "trend_state_5",
        "trend_state_20",
        "regime_transition_flag",
        "shock_state",
        "mom_20",
        "mom_60",
        "mom_accel",
        "beta_proxy_60",
        "alpha_proxy_20",
    ]

