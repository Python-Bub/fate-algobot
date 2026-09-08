"""Classic quant strategies expressed as causal features.

Each column is computed strictly from past data so it is safe to train on and
evaluate at decision-time without leakage. Toggle via `USE_CLASSIC_QUANT_FEATURES=true`.

Strategies covered:
- Trend following: SMA(50/200) "golden/death cross", EMA(12/26) trend, MACD (line / signal / histogram).
- Momentum: price ROC + volume surge confirmation (volume-weighted momentum).
- Breakout: distance from rolling 20-day and 52-week highs, distance from 52-week low, 20-day breakout flag.
- Mean reversion: Bollinger %B (where close sits inside the bands), Bollinger width, RSI bucket flags.
- Volatility / structure: ATR(14) and ATR-as-fraction-of-price, Donchian channel position.
- Execution / VWAP: rolling VWAP proxy and close-vs-VWAP deviation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _safe_div(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a / b.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)


def _ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False).mean()


def add_trend_following(df: pd.DataFrame) -> pd.DataFrame:
    """SMA crossovers, EMA trend, MACD."""
    out = df.copy()
    c = out["Adj Close"].astype(float) if "Adj Close" in out.columns else out["Close"].astype(float)
    sma_50 = c.rolling(50, min_periods=20).mean()
    sma_200 = c.rolling(200, min_periods=50).mean()
    out["sma_50_over_200"] = _safe_div(sma_50, sma_200).fillna(1.0).clip(0.5, 1.5)
    out["sma_golden_cross"] = (sma_50 > sma_200).astype(float).fillna(0.0)
    ema_12 = _ema(c, 12)
    ema_26 = _ema(c, 26)
    out["ema_12_over_26"] = _safe_div(ema_12, ema_26).fillna(1.0).clip(0.7, 1.3)
    macd = ema_12 - ema_26
    macd_signal = _ema(macd, 9)
    out["macd_line"] = (_safe_div(macd, c.abs() + 1e-9)).fillna(0.0).clip(-0.1, 0.1)
    out["macd_signal"] = (_safe_div(macd_signal, c.abs() + 1e-9)).fillna(0.0).clip(-0.1, 0.1)
    out["macd_hist"] = (out["macd_line"] - out["macd_signal"]).clip(-0.1, 0.1)
    return out


def add_volume_momentum(df: pd.DataFrame, roc_window: int = 5) -> pd.DataFrame:
    """Price rate-of-change confirmed by volume surge (classic momentum)."""
    out = df.copy()
    c = out["Adj Close"].astype(float) if "Adj Close" in out.columns else out["Close"].astype(float)
    if "Volume" not in out.columns:
        out["price_roc_5"] = 0.0
        out["volume_ratio_20"] = 1.0
        out["vol_confirmed_mom"] = 0.0
        return out
    v = out["Volume"].astype(float)
    prev = c.shift(roc_window)
    out["price_roc_5"] = _safe_div(c - prev, prev).fillna(0.0).clip(-0.5, 0.5)
    v_ma = v.rolling(20, min_periods=5).mean().replace(0, np.nan)
    out["volume_ratio_20"] = _safe_div(v, v_ma).fillna(1.0).clip(0.0, 10.0)
    # Signed momentum only when volume is elevated vs 20d average.
    confirm = (out["volume_ratio_20"] > 1.2).astype(float)
    out["vol_confirmed_mom"] = (out["price_roc_5"] * confirm).clip(-0.5, 0.5)
    return out


def add_breakout(df: pd.DataFrame) -> pd.DataFrame:
    """20-day breakout flag, distance from 20d high / 52w high / 52w low."""
    out = df.copy()
    c = out["Adj Close"].astype(float) if "Adj Close" in out.columns else out["Close"].astype(float)
    high_20 = c.rolling(20, min_periods=10).max()
    high_52w = c.rolling(252, min_periods=60).max()
    low_52w = c.rolling(252, min_periods=60).min()
    # Exclude today's bar so this is strictly causal (no look-ahead via today's max).
    out["dist_from_20d_high"] = _safe_div(c - high_20.shift(1), high_20.shift(1)).fillna(0.0).clip(-0.5, 0.5)
    out["dist_from_52w_high"] = _safe_div(c - high_52w.shift(1), high_52w.shift(1)).fillna(0.0).clip(-1.0, 1.0)
    out["dist_from_52w_low"] = _safe_div(c - low_52w.shift(1), low_52w.shift(1) + 1e-9).fillna(0.0).clip(-1.0, 10.0)
    out["breakout_20d_high"] = (c > high_20.shift(1)).astype(float).fillna(0.0)
    return out


def add_bollinger(df: pd.DataFrame, window: int = 20, k: float = 2.0) -> pd.DataFrame:
    """%B (location inside bands) and band width (relative)."""
    out = df.copy()
    c = out["Adj Close"].astype(float) if "Adj Close" in out.columns else out["Close"].astype(float)
    mid = c.rolling(window, min_periods=window // 2).mean()
    std = c.rolling(window, min_periods=window // 2).std()
    upper = mid + k * std
    lower = mid - k * std
    out["bb_pct_b"] = _safe_div(c - lower, upper - lower).fillna(0.5).clip(-0.5, 1.5)
    out["bb_width"] = _safe_div(upper - lower, mid).fillna(0.0).clip(0.0, 1.5)
    # Mean-reversion trigger flags used by the classic playbook.
    out["bb_oversold"] = (c < lower).astype(float).fillna(0.0)
    out["bb_overbought"] = (c > upper).astype(float).fillna(0.0)
    return out


def add_rsi_flags(df: pd.DataFrame) -> pd.DataFrame:
    """RSI bucket flags. Assumes `rsi` column already exists (0-100)."""
    out = df.copy()
    if "rsi" not in out.columns:
        return out
    rsi = out["rsi"].astype(float).clip(0, 100)
    out["rsi_oversold"] = (rsi < 30).astype(float)
    out["rsi_overbought"] = (rsi > 70).astype(float)
    # Distance from neutral, signed — useful even when not at extremes.
    out["rsi_centered"] = ((rsi - 50.0) / 50.0).clip(-1.0, 1.0)
    return out


def add_atr(df: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    """Average True Range / price — for ATR-based volatility stops."""
    out = df.copy()
    if not {"High", "Low", "Close"}.issubset(out.columns):
        out["atr_14"] = 0.0
        out["atr_frac"] = 0.0
        return out
    h = out["High"].astype(float)
    l = out["Low"].astype(float)
    c = out["Close"].astype(float)
    pc = c.shift(1)
    tr = pd.concat([(h - l).abs(), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1.0 / window, adjust=False, min_periods=window).mean()
    out["atr_14"] = atr.fillna(0.0)
    out["atr_frac"] = _safe_div(atr, c).fillna(0.0).clip(0.0, 1.0)
    return out


def add_vwap_proxy(df: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    """Rolling VWAP proxy and close-vs-VWAP deviation. Uses Close*Volume so it works
    on daily bars; intraday consumers can swap to true tick VWAP."""
    out = df.copy()
    if not {"Close", "Volume"}.issubset(out.columns):
        out["vwap_20"] = 0.0
        out["close_vs_vwap"] = 0.0
        return out
    c = out["Close"].astype(float)
    v = out["Volume"].astype(float)
    pv = (c * v).rolling(window, min_periods=max(3, window // 4)).sum()
    vv = v.rolling(window, min_periods=max(3, window // 4)).sum().replace(0, np.nan)
    vwap = (pv / vv).ffill()
    out["vwap_20"] = vwap.fillna(c)
    out["close_vs_vwap"] = _safe_div(c - vwap, vwap).fillna(0.0).clip(-0.5, 0.5)
    return out


def add_donchian(df: pd.DataFrame, window: int = 55) -> pd.DataFrame:
    """Donchian channel position (turtle-style breakout context)."""
    out = df.copy()
    c = out["Adj Close"].astype(float) if "Adj Close" in out.columns else out["Close"].astype(float)
    hi = c.rolling(window, min_periods=window // 2).max().shift(1)
    lo = c.rolling(window, min_periods=window // 2).min().shift(1)
    out["donchian_pos_55"] = _safe_div(c - lo, hi - lo).fillna(0.5).clip(-0.5, 1.5)
    return out


def enrich_classic_quant_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out = add_trend_following(out)
    out = add_volume_momentum(out)
    out = add_breakout(out)
    out = add_bollinger(out)
    out = add_rsi_flags(out)
    out = add_atr(out)
    out = add_vwap_proxy(out)
    out = add_donchian(out)
    out.replace([np.inf, -np.inf], 0, inplace=True)
    out.fillna(0, inplace=True)
    return out


def classic_quant_feature_columns() -> list[str]:
    return [
        "sma_50_over_200",
        "sma_golden_cross",
        "ema_12_over_26",
        "macd_line",
        "macd_signal",
        "macd_hist",
        "price_roc_5",
        "volume_ratio_20",
        "vol_confirmed_mom",
        "dist_from_20d_high",
        "dist_from_52w_high",
        "dist_from_52w_low",
        "breakout_20d_high",
        "bb_pct_b",
        "bb_width",
        "bb_oversold",
        "bb_overbought",
        "rsi_oversold",
        "rsi_overbought",
        "rsi_centered",
        "atr_14",
        "atr_frac",
        "vwap_20",
        "close_vs_vwap",
        "donchian_pos_55",
    ]
