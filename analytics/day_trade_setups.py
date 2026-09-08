"""
Day-trading setup library — scored on Yahoo intraday OHLCV.

Each setup returns bias in [-1, 1] and a short label for logging.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from analytics.jp_candles import assess_candles_from_df


@dataclass
class SetupScan:
    ticker: str
    bias: float
    confidence: float
    bullish: list[str] = field(default_factory=list)
    bearish: list[str] = field(default_factory=list)
    details: dict[str, float] = field(default_factory=dict)
    vwap: float = 0.0
    last_close: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "bias": self.bias,
            "confidence": self.confidence,
            "bullish": self.bullish,
            "bearish": self.bearish,
            "details": self.details,
            "vwap": self.vwap,
            "last_close": self.last_close,
        }


def _ema(s: pd.Series, span: int) -> pd.Series:
    return s.astype(float).ewm(span=span, adjust=False).mean()


def _clip(x: float) -> float:
    return float(max(-1.0, min(1.0, x)))


def trend_signal(df: pd.DataFrame) -> tuple[float, str]:
    if len(df) < 30:
        return 0.0, ""
    c = df["Close"].astype(float)
    e9, e21 = _ema(c, 9), _ema(c, 21)
    if e9.iloc[-1] > e21.iloc[-1] and c.iloc[-1] > e9.iloc[-1]:
        return 0.75, "trend_up"
    if e9.iloc[-1] < e21.iloc[-1] and c.iloc[-1] < e9.iloc[-1]:
        return -0.75, "trend_down"
    return 0.0, ""


def pullback_signal(df: pd.DataFrame) -> tuple[float, str]:
    if len(df) < 25:
        return 0.0, ""
    c = df["Close"].astype(float)
    e9 = _ema(c, 9)
    trend_up = c.iloc[-10] < c.iloc[-1] and _ema(c, 21).iloc[-1] < c.iloc[-1]
    dipped = c.iloc[-2] < e9.iloc[-2] and c.iloc[-1] > c.iloc[-2]
    if trend_up and dipped and c.iloc[-1] > e9.iloc[-1]:
        return 0.7, "pullback_long"
    trend_dn = c.iloc[-10] > c.iloc[-1] and _ema(c, 21).iloc[-1] > c.iloc[-1]
    popped = c.iloc[-2] > e9.iloc[-2] and c.iloc[-1] < c.iloc[-2]
    if trend_dn and popped and c.iloc[-1] < e9.iloc[-1]:
        return -0.7, "pullback_short"
    return 0.0, ""


def breakout_signal(df: pd.DataFrame, lookback: int = 20) -> tuple[float, str]:
    if len(df) < lookback + 2:
        return 0.0, ""
    h = df["High"].astype(float)
    l = df["Low"].astype(float)
    c = df["Close"].astype(float)
    res = h.iloc[-lookback - 1 : -1].max()
    sup = l.iloc[-lookback - 1 : -1].min()
    if c.iloc[-1] > res * 1.0005:
        return 0.8, "breakout_up"
    if c.iloc[-1] < sup * 0.9995:
        return -0.8, "breakout_down"
    return 0.0, ""


def range_signal(df: pd.DataFrame, lookback: int = 40) -> tuple[float, str]:
    if len(df) < lookback:
        return 0.0, ""
    tail = df.tail(lookback)
    h, l, c = tail["High"].astype(float), tail["Low"].astype(float), tail["Close"].astype(float)
    rng = h.max() - l.min()
    mid = (h.max() + l.min()) / 2
    if rng <= 0 or mid <= 0:
        return 0.0, ""
    if rng / mid > 0.025:
        return 0.0, ""
    pos = (c.iloc[-1] - l.min()) / rng
    if pos < 0.22:
        return 0.55, "range_support"
    if pos > 0.78:
        return -0.55, "range_resistance"
    return 0.0, ""


def gap_signal(df: pd.DataFrame) -> tuple[float, str]:
    if len(df) < 5:
        return 0.0, ""
    c = df["Close"].astype(float)
    o = df["Open"].astype(float)
    prev_close = c.iloc[-2]
    gap = (o.iloc[-1] - prev_close) / prev_close if prev_close > 0 else 0
    if gap > 0.004:
        return 0.5, "gap_up"
    if gap < -0.004:
        return -0.5, "gap_down"
    return 0.0, ""


def momentum_signal(df: pd.DataFrame) -> tuple[float, str]:
    if len(df) < 12:
        return 0.0, ""
    c = df["Close"].astype(float)
    v = df["Volume"].astype(float)
    roc = (c.iloc[-1] - c.iloc[-6]) / c.iloc[-6] if c.iloc[-6] > 0 else 0
    vol_surge = v.iloc[-1] > 1.4 * v.iloc[-11:-1].mean() if v.iloc[-11:-1].mean() > 0 else False
    if roc > 0.003 and vol_surge:
        return 0.72, "momentum_up"
    if roc < -0.003 and vol_surge:
        return -0.72, "momentum_down"
    return 0.0, ""


def vwap_signal(df: pd.DataFrame, vwap: float) -> tuple[float, str]:
    if vwap <= 0 or df.empty:
        return 0.0, ""
    c = float(df["Close"].iloc[-1])
    dist = (c - vwap) / vwap
    if dist > 0.0015:
        return 0.6, "above_vwap"
    if dist < -0.0015:
        return -0.6, "below_vwap"
    return 0.0, ""


def ma_crossover_signal(df: pd.DataFrame) -> tuple[float, str]:
    if len(df) < 25:
        return 0.0, ""
    c = df["Close"].astype(float)
    f, s = _ema(c, 8), _ema(c, 21)
    if f.iloc[-2] <= s.iloc[-2] and f.iloc[-1] > s.iloc[-1]:
        return 0.65, "ma_cross_bull"
    if f.iloc[-2] >= s.iloc[-2] and f.iloc[-1] < s.iloc[-1]:
        return -0.65, "ma_cross_bear"
    return 0.0, ""


def candlestick_signal(df: pd.DataFrame) -> tuple[float, str]:
    if len(df) < 6:
        return 0.0, ""
    ca = assess_candles_from_df(df, lookback=6)
    if ca.bias > 0:
        return 0.85, f"candle_{ca.pattern.lower()}"
    if ca.bias < 0:
        return -0.85, f"candle_{ca.pattern.lower()}"
    return 0.0, ""


def orb_signal(df: pd.DataFrame, minutes: int = 15) -> tuple[float, str]:
    """Opening range breakout (first N minutes of session bars)."""
    if len(df) < minutes + 3:
        return 0.0, ""
    try:
        idx = df.index
        if hasattr(idx, "tz") and idx.tz is not None:
            local = idx.tz_convert("America/New_York")
        else:
            local = pd.DatetimeIndex(idx).tz_localize("UTC").tz_convert("America/New_York")
        today = local[-1].date()
        mask = (local.date == today) & (
            (local.hour > 9) | ((local.hour == 9) & (local.minute >= 30))
        )
        session = df.loc[mask]
        if len(session) < minutes + 2:
            return 0.0, ""
        orb = session.iloc[:minutes]
        hi, lo = orb["High"].astype(float).max(), orb["Low"].astype(float).min()
        c = float(session["Close"].iloc[-1])
        if c > hi:
            return 0.78, "orb_break_up"
        if c < lo:
            return -0.78, "orb_break_down"
    except Exception:
        return 0.0, ""
    return 0.0, ""


def mean_reversion_signal(df: pd.DataFrame, vwap: float) -> tuple[float, str]:
    if vwap <= 0 or len(df) < 20:
        return 0.0, ""
    c = df["Close"].astype(float)
    std = c.tail(20).std()
    if std <= 0:
        return 0.0, ""
    z = (c.iloc[-1] - vwap) / std
    if z < -1.8:
        return 0.6, "mean_rev_long"
    if z > 1.8:
        return -0.6, "mean_rev_short"
    return 0.0, ""


def fvg_signal(df: pd.DataFrame) -> tuple[float, str]:
    """Fair value gap (3-bar imbalance) on 1m bars."""
    if len(df) < 4:
        return 0.0, ""
    h, l = df["High"].astype(float), df["Low"].astype(float)
    # Bullish FVG: bar[-3] high < bar[-1] low
    if h.iloc[-3] < l.iloc[-1]:
        return 0.55, "fvg_bull"
    if l.iloc[-3] > h.iloc[-1]:
        return -0.55, "fvg_bear"
    return 0.0, ""


def flag_signal(df: pd.DataFrame) -> tuple[float, str]:
    if len(df) < 25:
        return 0.0, ""
    c = df["Close"].astype(float)
    thrust = (c.iloc[-15] - c.iloc[-25]) / c.iloc[-25] if c.iloc[-25] > 0 else 0
    consol = c.tail(8).std() / c.tail(8).mean() if c.tail(8).mean() > 0 else 1.0
    if thrust > 0.012 and consol < 0.004 and c.iloc[-1] > c.iloc[-8]:
        return 0.58, "bull_flag"
    if thrust < -0.012 and consol < 0.004 and c.iloc[-1] < c.iloc[-8]:
        return -0.58, "bear_flag"
    return 0.0, ""


def pivot_signal(df: pd.DataFrame) -> tuple[float, str]:
    if len(df) < 2:
        return 0.0, ""
    prev = df.iloc[-2]
    h, l, c = float(prev["High"]), float(prev["Low"]), float(prev["Close"])
    pp = (h + l + c) / 3
    r1 = 2 * pp - l
    s1 = 2 * pp - h
    px = float(df["Close"].iloc[-1])
    if px > r1:
        return 0.45, "above_pivot_r1"
    if px < s1:
        return -0.45, "below_pivot_s1"
    if px > pp:
        return 0.25, "above_pivot"
    if px < pp:
        return -0.25, "below_pivot"
    return 0.0, ""


def news_signal(ticker: str) -> tuple[float, str]:
    path = Path(os.getenv("HFT_TRADE_NEWS_PATH", "data/intel/hft_trade_news.json"))
    if not path.is_file():
        return 0.0, ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        row = (data.get("tickers") or {}).get(ticker.upper()) or {}
        if row.get("allow_long") is False:
            return -0.9, "news_block"
        imp = float(row.get("impulse") or 0)
        if imp > 0.15:
            return 0.5, "news_bull"
        if imp < -0.15:
            return -0.5, "news_bear"
    except Exception:
        pass
    return 0.0, ""


def fade_exhaustion_signal(df: pd.DataFrame) -> tuple[float, str]:
    if len(df) < 15:
        return 0.0, ""
    c = df["Close"].astype(float)
    roc5 = (c.iloc[-1] - c.iloc[-6]) / c.iloc[-6] if c.iloc[-6] > 0 else 0
    roc1 = (c.iloc[-1] - c.iloc[-2]) / c.iloc[-2] if c.iloc[-2] > 0 else 0
    if roc5 > 0.015 and roc1 < -0.002:
        return -0.5, "fade_rally"
    if roc5 < -0.015 and roc1 > 0.002:
        return 0.5, "fade_selloff"
    return 0.0, ""


_SETUPS: list[tuple[str, float]] = [
    ("trend", 1.0),
    ("pullback", 1.1),
    ("breakout", 1.0),
    ("range", 0.7),
    ("gap", 0.8),
    ("momentum", 1.2),
    ("vwap", 1.3),
    ("ma_cross", 0.9),
    ("candlestick", 1.4),
    ("orb", 1.1),
    ("mean_reversion", 0.9),
    ("fvg", 0.8),
    ("flag", 0.85),
    ("pivot", 0.6),
    ("news", 1.0),
    ("fade", 0.7),
    ("gainz", 1.5),
]


def scan_setups(ticker: str, df: pd.DataFrame, *, vwap: float) -> SetupScan:
    sym = ticker.upper()
    raw: dict[str, float] = {}
    bull: list[str] = []
    bear: list[str] = []

    checks = [
        ("trend", trend_signal(df)),
        ("pullback", pullback_signal(df)),
        ("breakout", breakout_signal(df)),
        ("range", range_signal(df)),
        ("gap", gap_signal(df)),
        ("momentum", momentum_signal(df)),
        ("vwap", vwap_signal(df, vwap)),
        ("ma_cross", ma_crossover_signal(df)),
        ("candlestick", candlestick_signal(df)),
        ("orb", orb_signal(df, int(os.getenv("DAY_TRADE_ORB_MINUTES", "15")))),
        ("mean_reversion", mean_reversion_signal(df, vwap)),
        ("fvg", fvg_signal(df)),
        ("flag", flag_signal(df)),
        ("pivot", pivot_signal(df)),
        ("news", news_signal(sym)),
        ("fade", fade_exhaustion_signal(df)),
    ]
    try:
        from analytics.gainz_v2 import assess as _gainz_assess

        g = _gainz_assess(df, symbol=sym)
        raw["gainz_entry"] = float(g.entry)
        raw["gainz_stop"] = float(g.stop)
        raw["gainz_target"] = float(g.target)
        raw["gainz_layers"] = float(g.layers_passed)
        raw["gainz_ts"] = float(g.trend_strength)
        if g.side == "buy":
            checks.append(("gainz", (min(1.0, 0.55 + 0.08 * g.layers_passed), f"gainz_{g.label.lower()}")))
        elif g.side == "sell":
            checks.append(("gainz", (max(-1.0, -0.55 - 0.08 * g.layers_passed), f"gainz_{g.label.lower()}")))
        elif g.ready:
            checks.append(("gainz", (0.35 if g.trend_strength >= 0 else -0.35, "gainz_ready")))
        elif g.bos or g.choch:
            checks.append(("gainz", (0.2 if g.trend_strength >= 0 else -0.2, f"gainz_{g.label.lower()}")))
    except Exception:
        pass
    weights = {k: w for k, w in _SETUPS}
    score = 0.0
    wsum = 0.0
    for name, (val, label) in checks:
        if not label:
            continue
        w = weights.get(name, 1.0)
        score += val * w
        wsum += abs(w)
        raw[name] = val
        if val > 0:
            bull.append(label)
        elif val < 0:
            bear.append(label)

    bias = _clip(score / wsum) if wsum > 0 else 0.0
    conf = min(1.0, abs(score) / max(wsum, 1e-6))
    last = float(df["Close"].iloc[-1]) if not df.empty else 0.0
    return SetupScan(sym, bias, conf, bull, bear, raw, vwap, last)
