"""Light feature engineering for intraday (minute / hourly) bars.

Daily features (FRED spread, news rolls, Cramer factor, etc.) are not informative
intraday — they don't change frequently enough to drive 5-minute signals. We use
a focused, causal feature set:

  • Returns at lookbacks 1, 3, 5, 15, 60 bars
  • Rolling realised volatility (5/15/60 bars)
  • RSI(14)
  • MACD line + signal + histogram
  • Bollinger %B and bandwidth (20 bars)
  • Volume-weighted ratios (vol vs 20-bar mean)
  • VWAP deviation (price − rolling VWAP) / rolling VWAP
  • Bar-of-day cyclical encoding (sin/cos over US RTH minute index)
  • Trade-count z-score (intensity proxy)

All features are computed strictly causally (`.shift(1)` everywhere it matters)
so chronological train/test splits give honest holdout accuracy.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

INTRADAY_FEATURES = [
    "ret_1",
    "ret_3",
    "ret_5",
    "ret_15",
    "ret_60",
    "vol_roll_5",
    "vol_roll_15",
    "vol_roll_60",
    "rsi_14",
    "macd_line",
    "macd_signal",
    "macd_hist",
    "bb_pct_b",
    "bb_bandwidth",
    "vol_ratio_20",
    "vwap_dev",
    "tod_sin",
    "tod_cos",
    "trade_z",
]


def _rsi(series: pd.Series, window: int = 14) -> pd.Series:
    delta = series.diff()
    up = delta.clip(lower=0.0)
    down = -delta.clip(upper=0.0)
    roll_up = up.rolling(window).mean()
    roll_down = down.rolling(window).mean()
    rs = roll_up / roll_down.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def _macd(series: pd.Series, fast: int = 12, slow: int = 26, sig: int = 9) -> tuple[pd.Series, pd.Series, pd.Series]:
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    line = ema_fast - ema_slow
    signal = line.ewm(span=sig, adjust=False).mean()
    hist = line - signal
    return line, signal, hist


def _bollinger(series: pd.Series, window: int = 20, k: float = 2.0) -> tuple[pd.Series, pd.Series]:
    ma = series.rolling(window).mean()
    sd = series.rolling(window).std(ddof=0)
    pct_b = (series - (ma - k * sd)) / (2 * k * sd).replace(0, np.nan)
    bandwidth = (2 * k * sd) / ma.replace(0, np.nan)
    return pct_b, bandwidth


def _vwap_roll(price: pd.Series, vol: pd.Series, window: int = 60) -> pd.Series:
    pv = (price * vol).rolling(window).sum()
    v = vol.rolling(window).sum().replace(0, np.nan)
    return pv / v


def build_intraday_features(bars: pd.DataFrame) -> pd.DataFrame:
    """Take OHLCV-style intraday bars and return them with all features attached.

    Causal: every feature uses only data up to and including the current bar,
    then we shift the target ahead by ``H`` bars to predict the next move.
    """
    if bars.empty:
        return bars
    df = bars.copy()
    close = df["Close"].astype(float)
    vol = df["Volume"].astype(float).fillna(0)
    trades = df["TradeCount"].astype(float).fillna(0) if "TradeCount" in df.columns else pd.Series(0, index=df.index)

    log_ret = np.log(close).diff()
    for w in (1, 3, 5, 15, 60):
        df[f"ret_{w}"] = log_ret.rolling(w).sum()
    for w in (5, 15, 60):
        df[f"vol_roll_{w}"] = log_ret.rolling(w).std(ddof=0)
    df["rsi_14"] = _rsi(close, 14)
    line, sig, hist = _macd(close)
    df["macd_line"] = line
    df["macd_signal"] = sig
    df["macd_hist"] = hist
    pct_b, band = _bollinger(close, 20, 2.0)
    df["bb_pct_b"] = pct_b.fillna(0.5)
    df["bb_bandwidth"] = band.fillna(0.0)
    df["vol_ratio_20"] = (vol / vol.rolling(20).mean()).replace([np.inf, -np.inf], np.nan)
    rv = _vwap_roll(close, vol, 60)
    df["vwap_dev"] = (close / rv - 1.0).replace([np.inf, -np.inf], np.nan)

    # Bar-of-day cyclical encoding — minute index from 9:30 ET (US RTH start).
    minute_of_day = df.index.tz_convert("US/Eastern").hour * 60 + df.index.tz_convert("US/Eastern").minute
    period = 6.5 * 60  # 390 min RTH
    rth_idx = ((minute_of_day - 9 * 60 - 30) % period) / period * 2 * math.pi
    df["tod_sin"] = np.sin(rth_idx)
    df["tod_cos"] = np.cos(rth_idx)

    # Trade-count z-score over 60 bars (intensity proxy).
    tc_ma = trades.rolling(60).mean()
    tc_sd = trades.rolling(60).std(ddof=0).replace(0, np.nan)
    df["trade_z"] = ((trades - tc_ma) / tc_sd).replace([np.inf, -np.inf], np.nan).fillna(0)

    return df


def add_intraday_targets(df: pd.DataFrame, horizons: tuple[int, ...] = (5, 60)) -> pd.DataFrame:
    """Add binary up/down target columns ``target_h{H}`` for each H bars ahead."""
    if df.empty:
        return df
    close = df["Close"].astype(float)
    for h in horizons:
        fwd = close.shift(-h) / close.replace(0, np.nan) - 1.0
        df[f"target_h{h}"] = np.where(fwd.notna(), (fwd > 0).astype(float), np.nan)
    return df
