"""
Technical analysis formulas (RSI Wilder, MACD, Bollinger, composites).
"""

from __future__ import annotations

import numpy as np


def _closes_array(closes: list[float] | np.ndarray) -> np.ndarray:
    return np.asarray(closes, dtype=float)


def _ema(series: np.ndarray, span: int) -> np.ndarray:
    alpha = 2.0 / (span + 1.0)
    out = np.empty_like(series, dtype=float)
    out[0] = series[0]
    for i in range(1, len(series)):
        out[i] = alpha * series[i] + (1.0 - alpha) * out[i - 1]
    return out


def rsi(closes: list[float] | np.ndarray, period: int = 14) -> float:
    """
    Wilder RSI(period) on the last bar.

    RSI = 100 − 100 / (1 + RS),  RS = avg gain / avg loss.
    """
    c = _closes_array(closes)
    if len(c) < period + 1:
        return 50.0
    deltas = np.diff(c)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = float(np.mean(gains[:period]))
    avg_loss = float(np.mean(losses[:period]))
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss <= 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100.0 - 100.0 / (1.0 + rs))


def macd(
    closes: list[float] | np.ndarray,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[float, float, float]:
    """
    MACD line, signal line, histogram on the last bar.

    MACD = EMA(fast) − EMA(slow); signal = EMA(MACD, signal).
    """
    c = _closes_array(closes)
    if len(c) < slow:
        return 0.0, 0.0, 0.0
    ema_fast = _ema(c, fast)
    ema_slow = _ema(c, slow)
    macd_line = ema_fast - ema_slow
    sig = _ema(macd_line, signal)
    m = float(macd_line[-1])
    s = float(sig[-1])
    return m, s, m - s


def bollinger(
    closes: list[float] | np.ndarray,
    period: int = 20,
    n_std: float = 2.0,
) -> tuple[float, float, float, float]:
    """
    Bollinger bands on the last bar: mid, upper, lower, %B.

    %B = (price − lower) / (upper − lower).
    """
    c = _closes_array(closes)
    if len(c) < period:
        px = float(c[-1])
        return px, px, px, 0.5
    window = c[-period:]
    mid = float(np.mean(window))
    std = float(np.std(window, ddof=0))
    upper = mid + n_std * std
    lower = mid - n_std * std
    px = float(c[-1])
    width = upper - lower
    pct_b = (px - lower) / width if width > 0 else 0.5
    return mid, upper, lower, float(pct_b)


def zscore(closes: list[float] | np.ndarray, period: int = 20) -> float:
    """Z-score of last close vs rolling mean/std over period."""
    c = _closes_array(closes)
    if len(c) < period:
        return 0.0
    window = c[-period:]
    mean = float(np.mean(window))
    std = float(np.std(window, ddof=0))
    if std <= 0:
        return 0.0
    return float((c[-1] - mean) / std)


def breakout_score(closes: list[float] | np.ndarray, lookback: int = 20) -> float:
    """
    Breakout tilt in [-1, 1]: price vs N-day high.

    At/above high ⇒ +1; at/below low ⇒ −1.
    """
    c = _closes_array(closes)
    if len(c) < 2:
        return 0.0
    n = min(lookback, len(c))
    window = c[-n:]
    hi = float(np.max(window))
    lo = float(np.min(window))
    px = float(c[-1])
    if hi <= lo:
        return 0.0
    raw = 2.0 * (px - lo) / (hi - lo) - 1.0
    return float(np.clip(raw, -1.0, 1.0))


def trend_score(closes: list[float] | np.ndarray, short: int = 10, long: int = 50) -> float:
    """
    EMA stack trend in [-1, 1]: short EMA > long EMA ⇒ bullish.
    """
    c = _closes_array(closes)
    if len(c) < long:
        return 0.0
    ema_s = _ema(c, short)[-1]
    ema_l = _ema(c, long)[-1]
    if ema_l <= 0:
        return 0.0
    spread = (ema_s - ema_l) / ema_l
    return float(np.clip(np.tanh(spread * 20.0), -1.0, 1.0))


def mean_reversion_score(closes: list[float] | np.ndarray) -> float:
    """
    Mean-reversion tilt in [-1, 1] from z-score and RSI.

    Oversold (low z, low RSI) ⇒ positive (buy dip); overbought ⇒ negative.
    """
    z = zscore(closes)
    r = rsi(closes)
    z_comp = -np.tanh(z)
    rsi_comp = (50.0 - r) / 50.0
    return float(np.clip(0.55 * z_comp + 0.45 * rsi_comp, -1.0, 1.0))


def technical_composite(closes: list[float] | np.ndarray) -> float:
    """Blended technical score in [-1, 1] from trend, breakout, mean-reversion."""
    if len(closes) < 2:
        return 0.0
    t = trend_score(closes)
    b = breakout_score(closes)
    m = mean_reversion_score(closes)
    return float(np.clip(0.40 * t + 0.35 * b + 0.25 * m, -1.0, 1.0))
