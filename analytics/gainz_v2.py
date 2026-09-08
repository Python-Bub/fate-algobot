"""Gainz-style 1m–1h signals — public Smart Money Structure math, not invite-only V2.

Teacher for the sandbox. Bar-close, non-repainting. Outputs BUY/SELL with
entry, ATR stop, and R:R target so HFT/day-trade can fire with precise levels.

Published formulas (TradingView open-source Smart Money Structure | GainzAlgo):
  MomentumThreshold = Base × (1 + (ATR ÷ Price) × 2)
  PreMomentum      = Base × (1 − (ATR ÷ Price) × 0.5)
  TrendStrength    = (mean of EMA+VWAP TF scores) × 100   # −100..+100
  CVD              = cumsum(volume × sign(close − prev))
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

TF_MINUTES = (1, 5, 15, 30, 60, 240, 1440)
_LAST_FIRE: dict[str, tuple[str, int]] = {}


@dataclass
class GainzSignal:
    symbol: str
    side: str  # buy | sell | none
    label: str
    entry: float
    stop: float
    target: float
    trend_strength: float
    confidence: float
    layers_passed: int
    reasons: list[str] = field(default_factory=list)
    cvd: float = 0.0
    bos: bool = False
    choch: bool = False
    ready: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "label": self.label,
            "entry": round(self.entry, 4),
            "stop": round(self.stop, 4),
            "target": round(self.target, 4),
            "trend_strength": round(self.trend_strength, 2),
            "confidence": round(self.confidence, 4),
            "layers_passed": self.layers_passed,
            "reasons": self.reasons[:8],
            "cvd": round(self.cvd, 2),
            "bos": self.bos,
            "choch": self.choch,
            "ready": self.ready,
        }


def _col(df: pd.DataFrame, name: str) -> pd.Series:
    for c in df.columns:
        if str(c).lower() == name.lower():
            return df[c].astype(float)
    raise KeyError(name)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    h, l, c = _col(df, "High"), _col(df, "Low"), _col(df, "Close")
    prev = c.shift(1)
    tr = pd.concat([(h - l).abs(), (h - prev).abs(), (l - prev).abs()], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def vwap_series(df: pd.DataFrame) -> pd.Series:
    c = _col(df, "Close")
    vol = _col(df, "Volume").clip(lower=0)
    tp = (_col(df, "High") + _col(df, "Low") + c) / 3.0
    pv = (tp * vol).cumsum()
    vv = vol.cumsum().replace(0, np.nan)
    return (pv / vv).fillna(c)


def cvd_series(df: pd.DataFrame) -> pd.Series:
    c = _col(df, "Close")
    vol = _col(df, "Volume").clip(lower=0)
    delta = np.sign(c.diff().fillna(0.0))
    return (vol * delta).cumsum()


def momentum_threshold(price: float, atr_v: float, base: float | None = None) -> float:
    base = float(base if base is not None else os.getenv("GAINZ_MOM_BASE", "0.004"))
    px = max(float(price), 1e-9)
    return base * (1.0 + (float(atr_v) / px) * 2.0)


def pre_momentum_factor(price: float, atr_v: float, base: float | None = None) -> float:
    base = float(base if base is not None else os.getenv("GAINZ_MOM_BASE", "0.004"))
    px = max(float(price), 1e-9)
    return base * (1.0 - (float(atr_v) / px) * 0.5)


def _ema_vwap_score(df: pd.DataFrame) -> float:
    """+1 EMA9>EMA21 and close>VWAP; −1 inverse; else 0."""
    if df is None or len(df) < 22:
        return 0.0
    c = _col(df, "Close")
    e9 = c.ewm(span=9, adjust=False).mean()
    e21 = c.ewm(span=21, adjust=False).mean()
    vw = vwap_series(df)
    last_c, last_e9, last_e21, last_vw = float(c.iloc[-1]), float(e9.iloc[-1]), float(e21.iloc[-1]), float(vw.iloc[-1])
    bull = last_e9 > last_e21 and last_c > last_vw
    bear = last_e9 < last_e21 and last_c < last_vw
    if bull:
        return 1.0
    if bear:
        return -1.0
    if last_e9 > last_e21:
        return 0.35
    if last_e9 < last_e21:
        return -0.35
    return 0.0


def _resample(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    if minutes <= 1:
        return df
    if not isinstance(df.index, pd.DatetimeIndex):
        return df.iloc[::minutes] if minutes < len(df) else df
    rule = f"{int(minutes)}min"
    o = _col(df, "Open").resample(rule).first()
    h = _col(df, "High").resample(rule).max()
    l = _col(df, "Low").resample(rule).min()
    c = _col(df, "Close").resample(rule).last()
    v = _col(df, "Volume").resample(rule).sum()
    out = pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c, "Volume": v}).dropna()
    return out


def trend_strength(df: pd.DataFrame) -> float:
    scores: list[float] = []
    for m in TF_MINUTES:
        sub = _resample(df, m)
        if len(sub) < 22:
            continue
        scores.append(_ema_vwap_score(sub))
    if not scores:
        return 0.0
    return float(np.mean(scores) * 100.0)


def _swings(df: pd.DataFrame, lookback: int = 5) -> tuple[float, float, float, float]:
    """Last confirmed swing high/low and prior (for CHoCH)."""
    h, l = _col(df, "High"), _col(df, "Low")
    if len(df) < lookback * 4:
        return float(h.max()), float(l.min()), float(h.max()), float(l.min())
    sh: list[float] = []
    sl: list[float] = []
    for i in range(lookback, len(df) - lookback):
        window_h = h.iloc[i - lookback : i + lookback + 1]
        window_l = l.iloc[i - lookback : i + lookback + 1]
        if float(h.iloc[i]) >= float(window_h.max()):
            sh.append(float(h.iloc[i]))
        if float(l.iloc[i]) <= float(window_l.min()):
            sl.append(float(l.iloc[i]))
    if len(sh) < 2:
        sh = [float(h.iloc[-20:].max()), float(h.iloc[-5:].max())]
    if len(sl) < 2:
        sl = [float(l.iloc[-20:].min()), float(l.iloc[-5:].min())]
    return sh[-1], sl[-1], sh[-2], sl[-2]


def structure_flags(df: pd.DataFrame) -> tuple[bool, bool]:
    """(bos, choch) on last close vs last swings. Bar-close only."""
    c = float(_col(df, "Close").iloc[-1])
    sh, sl, psh, psl = _swings(df)
    bos = c > sh or c < sl
    choch = (c > psh and float(_col(df, "Close").iloc[-3]) < psl) or (
        c < psl and float(_col(df, "Close").iloc[-3]) > psh
    )
    return bool(bos), bool(choch)


def _rr() -> float:
    return max(0.5, float(os.getenv("GAINZ_RR", "2.0")))


def _atr_stop_mult() -> float:
    return max(0.4, float(os.getenv("GAINZ_ATR_STOP_MULT", "1.5")))


def levels(entry: float, atr_v: float, side: str) -> tuple[float, float]:
    stop_dist = max(entry * 0.002, float(atr_v) * _atr_stop_mult())
    if side == "buy":
        stop = entry - stop_dist
        target = entry + stop_dist * _rr()
    else:
        stop = entry + stop_dist
        target = entry - stop_dist * _rr()
    return float(stop), float(target)


def assess(df: pd.DataFrame, *, symbol: str = "", bar_index: int | None = None) -> GainzSignal:
    """Six-layer filter at bar close. side=none unless ≥4 layers fire."""
    empty = GainzSignal(symbol.upper(), "none", "", 0.0, 0.0, 0.0, 0.0, 0.0, 0)
    if df is None or len(df) < 30:
        return empty
    c = _col(df, "Close")
    px = float(c.iloc[-1])
    a = float(atr(df).iloc[-1] or 0.0)
    roc = float(c.iloc[-1] / max(float(c.iloc[-6]), 1e-9) - 1.0) if len(c) >= 6 else 0.0
    thr = momentum_threshold(px, a)
    pre = pre_momentum_factor(px, a)
    ts = trend_strength(df)
    cvd = float(cvd_series(df).iloc[-1] or 0.0)
    bos, choch = structure_flags(df)
    vol = _col(df, "Volume")
    vol_ok = float(vol.iloc[-1]) >= float(vol.iloc[-20:].median()) * 0.9 if len(vol) >= 20 else True

    layers: list[str] = []
    # 1 volatility-adjusted momentum
    if abs(roc) >= thr:
        layers.append("momentum")
    elif abs(roc) >= pre:
        layers.append("pre_momentum")
    # 2 HTF trend
    if (roc > 0 and ts > 8) or (roc < 0 and ts < -8):
        layers.append("htf_trend")
    # 3 LTF conflict (1m vs 5m)
    s1 = _ema_vwap_score(df)
    s5 = _ema_vwap_score(_resample(df, 5))
    if s1 * s5 >= 0:
        layers.append("ltf_align")
    # 4 CVD / volume
    if (roc > 0 and cvd > 0 and vol_ok) or (roc < 0 and cvd < 0 and vol_ok):
        layers.append("cvd")
    # 5 structure
    if bos or choch:
        layers.append("structure")
    # 6 repeat restriction
    idx = int(bar_index if bar_index is not None else len(df))
    last = _LAST_FIRE.get(symbol.upper())
    if last is None or last[1] < idx - 2:
        layers.append("fresh")

    n = len(layers)
    need = int(os.getenv("GAINZ_MIN_LAYERS", "4"))
    ready = n >= max(2, need - 1) and "pre_momentum" in layers
    want_buy = roc > 0 and ts >= 0 and n >= need
    want_sell = roc < 0 and ts <= 0 and n >= need
    if last is not None and last[1] == idx:
        # Same-bar re-assess is idempotent (teacher+student, or scan twice).
        want_buy = last[0] == "buy"
        want_sell = last[0] == "sell"
    elif last is not None and last[1] >= idx - 1:
        if (want_buy and last[0] == "buy") or (want_sell and last[0] == "sell"):
            want_buy = want_sell = False

    side = "none"
    label = ""
    if want_buy:
        side, label = "buy", "BUY"
    elif want_sell:
        side, label = "sell", "SELL"
    elif choch:
        label = "CHOCH"
    elif bos:
        label = "BOS"
    elif ready:
        label = "READY"

    stop, target = (0.0, 0.0)
    if side in ("buy", "sell"):
        stop, target = levels(px, a, side)
        _LAST_FIRE[symbol.upper()] = (side, idx)

    conf = min(1.0, n / 6.0) * min(1.0, abs(ts) / 80.0 + 0.25)
    return GainzSignal(
        symbol=symbol.upper(),
        side=side,
        label=label,
        entry=px if side != "none" else 0.0,
        stop=stop,
        target=target,
        trend_strength=ts,
        confidence=float(conf),
        layers_passed=n,
        reasons=layers,
        cvd=cvd,
        bos=bos,
        choch=choch,
        ready=ready,
    )


def setup_bias(df: pd.DataFrame, *, symbol: str = "") -> tuple[float, str]:
    """Day-trade setup hook: bias in [-1,1] + label."""
    g = assess(df, symbol=symbol)
    if g.side == "buy":
        return min(1.0, 0.55 + 0.08 * g.layers_passed), f"gainz_{g.label.lower()}"
    if g.side == "sell":
        return max(-1.0, -0.55 - 0.08 * g.layers_passed), f"gainz_{g.label.lower()}"
    if g.ready and g.trend_strength > 0:
        return 0.35, "gainz_ready"
    if g.ready and g.trend_strength < 0:
        return -0.35, "gainz_ready"
    if g.bos:
        return (0.2 if g.trend_strength >= 0 else -0.2), "gainz_bos"
    return 0.0, ""
