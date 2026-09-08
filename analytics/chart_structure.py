"""Detailed OHLC structure for prediction — ATR channel, volume climax, wick rejects.

Additive to classic_quant / structure_patterns. Extra columns fill 0 on short
histories so old model bundles keep working (inference aligns by name).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _safe_div(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a / b.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)


def enrich_chart_structure(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    out = df.copy()
    need = {"Open", "High", "Low", "Close"}
    if not need.issubset(out.columns):
        for c in (
            "vol_climax_z",
            "atr_channel_pos",
            "close_stretch_20",
            "wick_reject",
            "ema_ribbon_spread",
            "range_compress",
            "broke_high",
            "broke_low",
            "volume_trend",
            "gap_pct",
        ):
            if c not in out.columns:
                out[c] = 0.0
        return out

    c = out["Close"].astype(float)
    h = out["High"].astype(float)
    l = out["Low"].astype(float)
    o = out["Open"].astype(float)
    v = out["Volume"].astype(float) if "Volume" in out.columns else pd.Series(0.0, index=out.index)

    tr = pd.concat([(h - l), (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14, min_periods=5).mean()
    mid = c.rolling(20, min_periods=5).mean()
    upper = mid + 2.0 * atr
    lower = mid - 2.0 * atr
    width = (upper - lower).replace(0, np.nan)
    out["atr_channel_pos"] = ((c - lower) / width).fillna(0.5).clip(0.0, 1.0)

    v_mean = v.rolling(20, min_periods=5).mean()
    v_std = v.rolling(20, min_periods=5).std()
    out["vol_climax_z"] = ((v - v_mean) / (v_std + 1e-9)).fillna(0.0).clip(-8.0, 8.0)

    hh20 = h.rolling(20, min_periods=5).max()
    ll20 = l.rolling(20, min_periods=5).min()
    rng = (hh20 - ll20).replace(0, np.nan)
    out["close_stretch_20"] = ((c - ll20) / rng).fillna(0.5).clip(0.0, 1.0)

    bar = (h - l).replace(0, np.nan)
    lower_wick = (pd.concat([o, c], axis=1).min(axis=1) - l).clip(lower=0)
    upper_wick = (h - pd.concat([o, c], axis=1).max(axis=1)).clip(lower=0)
    out["wick_reject"] = _safe_div(lower_wick - upper_wick, bar).fillna(0.0).clip(-1.0, 1.0)

    # Extra graph dimensions (0-fill on short history so old pickles stay aligned).
    ema_f = c.ewm(span=8, adjust=False).mean()
    ema_s = c.ewm(span=21, adjust=False).mean()
    out["ema_ribbon_spread"] = _safe_div(ema_f - ema_s, c).fillna(0.0).clip(-0.2, 0.2)
    out["range_compress"] = _safe_div(atr, c).fillna(0.0).clip(0.0, 0.2)
    hh = h.rolling(10, min_periods=3).max().shift(1)
    ll = l.rolling(10, min_periods=3).min().shift(1)
    out["broke_high"] = (h > hh).astype(float).fillna(0.0)
    out["broke_low"] = (l < ll).astype(float).fillna(0.0)
    vsma = v.rolling(20, min_periods=5).mean()
    out["volume_trend"] = _safe_div(v, vsma).fillna(1.0).clip(0.0, 8.0)
    prev_c = c.shift(1)
    out["gap_pct"] = _safe_div(o - prev_c, prev_c).fillna(0.0).clip(-0.15, 0.15)

    out.replace([np.inf, -np.inf], 0, inplace=True)
    extra_cols = (
        "vol_climax_z",
        "atr_channel_pos",
        "close_stretch_20",
        "wick_reject",
        "ema_ribbon_spread",
        "range_compress",
        "broke_high",
        "broke_low",
        "volume_trend",
        "gap_pct",
    )
    for col in extra_cols:
        if col not in out.columns:
            out[col] = 0.0
        out[col] = out[col].fillna(0.0)
    return out


def chart_structure_score(row: pd.Series | dict) -> float:
    """Small rank overlay in [-0.08, 0.08] from last-bar structure."""
    try:
        pos = float(row.get("atr_channel_pos", 0.5) or 0.5)
        stretch = float(row.get("close_stretch_20", 0.5) or 0.5)
        wick = float(row.get("wick_reject", 0.0) or 0.0)
        volz = float(row.get("vol_climax_z", 0.0) or 0.0)
        ribbon = float(row.get("ema_ribbon_spread", 0.0) or 0.0)
        compress = float(row.get("range_compress", 0.0) or 0.0)
        broke_hi = float(row.get("broke_high", 0.0) or 0.0)
        broke_lo = float(row.get("broke_low", 0.0) or 0.0)
        vtrend = float(row.get("volume_trend", 1.0) or 1.0)
        gap = float(row.get("gap_pct", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0
    # Mid-channel + hammer-like wick + not climax dump.
    mid = 1.0 - abs(pos - 0.5) * 2.0
    bounce = max(-1.0, min(1.0, wick))
    climax = max(-1.0, min(1.0, volz / 4.0))
    stretch_pen = max(0.0, stretch - 0.92) * 2.0  # extended highs
    ribbon_n = max(-1.0, min(1.0, ribbon / 0.04))
    squeeze = max(0.0, 0.04 - compress) / 0.04  # coiled range is tradable
    brk = 0.02 * broke_hi - 0.03 * broke_lo
    vol_ok = max(-1.0, min(1.0, (vtrend - 1.0) / 2.0))
    gap_pen = max(0.0, abs(gap) - 0.03) * 1.5
    raw = (
        0.035 * mid
        + 0.025 * bounce
        - 0.02 * climax
        - 0.035 * stretch_pen
        + 0.02 * ribbon_n
        + 0.015 * squeeze
        + brk
        + 0.01 * vol_ok
        - 0.04 * gap_pen
    )
    return float(max(-0.08, min(0.08, raw)))
