"""Undercut & Rally (U&R) pattern detector — O'Neil / Minervini style.

Definition (per Mark Minervini's "Trade Like a Stock Market Wizard"):
- Price recently established a meaningful prior swing low ("pivot low") in the last
  N bars (default lookback 20, scanning >= MIN_PIVOT_AGE bars back).
- The most recent close *undercut* that prior low intraday (low_today < pivot_low),
  shaking out weak hands.
- Then price *rallied back above* the prior low by close (close_today > pivot_low),
  ideally on expanding volume.
- The setup is invalidated if the larger trend is broken (close < EMA(50) by more
  than INVALIDATE_PCT, default 7%).

Output: a score in [0, 1] indicating the strength of an undercut-and-rally signal.
0   = no U&R
1   = textbook U&R: deep undercut, full reclaim, volume expansion, in uptrend.

Env knobs:
- UR_LOOKBACK            default 20
- UR_MIN_PIVOT_AGE       default 3   (pivot must be >=N bars old, no same-day cheating)
- UR_PIVOT_WINDOW        default 5   (rolling-min window used to detect "pivot low")
- UR_VOL_EXPANSION       default 1.3 (today's volume / 20-day avg)
- UR_REQUIRE_TREND       default true
- UR_INVALIDATE_PCT      default 0.07
- UR_MAX_BARS_PAST_PIVOT default 30  (don't rally off a year-old low)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd


@dataclass
class UndercutRallyResult:
    score: float
    detected: bool
    pivot_low: float
    pivot_age_bars: int
    today_low: float
    today_close: float
    undercut_depth_pct: float
    reclaim_pct: float
    volume_expansion: float
    trend_ok: bool
    rationale: str

    def to_dict(self) -> dict:
        return asdict(self)


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default


def _i(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def _b(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes")


def detect_undercut_rally(df: pd.DataFrame) -> UndercutRallyResult:
    """Detect undercut & rally on the *last* bar of `df`.

    `df` must have columns: ['Open', 'High', 'Low', 'Close', 'Volume'] indexed by date.
    """
    cols_needed = {"Open", "High", "Low", "Close", "Volume"}
    if df is None or df.empty or not cols_needed.issubset(df.columns):
        return UndercutRallyResult(
            score=0.0, detected=False, pivot_low=float("nan"), pivot_age_bars=0,
            today_low=float("nan"), today_close=float("nan"),
            undercut_depth_pct=0.0, reclaim_pct=0.0, volume_expansion=0.0,
            trend_ok=False, rationale="missing_columns",
        )

    lookback = max(8, _i("UR_LOOKBACK", 20))
    pivot_window = max(2, _i("UR_PIVOT_WINDOW", 5))
    min_age = max(1, _i("UR_MIN_PIVOT_AGE", 3))
    max_age = max(min_age + 1, _i("UR_MAX_BARS_PAST_PIVOT", 30))
    vol_expand_target = _f("UR_VOL_EXPANSION", 1.3)
    require_trend = _b("UR_REQUIRE_TREND", True)
    invalidate_pct = _f("UR_INVALIDATE_PCT", 0.07)

    sub = df.tail(max(lookback + max_age, 60)).copy()
    if len(sub) < min_age + pivot_window + 2:
        return UndercutRallyResult(
            score=0.0, detected=False, pivot_low=float("nan"), pivot_age_bars=0,
            today_low=float("nan"), today_close=float("nan"),
            undercut_depth_pct=0.0, reclaim_pct=0.0, volume_expansion=0.0,
            trend_ok=False, rationale="insufficient_history",
        )

    today = sub.iloc[-1]
    today_low = float(today["Low"])
    today_close = float(today["Close"])
    today_volume = float(today["Volume"])

    history = sub.iloc[:-1]
    lows_arr = history["Low"].to_numpy(dtype=float)
    n_hist = len(lows_arr)

    # A *true* swing-low pivot is a bar whose low is the minimum within +/- pivot_window
    # bars on each side. We then take the MOST RECENT such pivot inside the
    # [min_age, max_age] window, so we don't accidentally rally off a year-old absolute low.
    pivots: list[tuple[int, float]] = []
    for i in range(pivot_window, n_hist - pivot_window):
        window_lo = lows_arr[i - pivot_window: i + pivot_window + 1]
        if lows_arr[i] == window_lo.min():
            pivots.append((i, float(lows_arr[i])))

    if not pivots:
        return UndercutRallyResult(
            score=0.0, detected=False, pivot_low=float("nan"), pivot_age_bars=0,
            today_low=today_low, today_close=today_close,
            undercut_depth_pct=0.0, reclaim_pct=0.0, volume_expansion=0.0,
            trend_ok=False, rationale="no_pivot_window",
        )

    eligible_pivots = [(i, lo) for (i, lo) in pivots if min_age <= (n_hist - i) <= max_age]
    if not eligible_pivots:
        return UndercutRallyResult(
            score=0.0, detected=False, pivot_low=float("nan"), pivot_age_bars=0,
            today_low=today_low, today_close=today_close,
            undercut_depth_pct=0.0, reclaim_pct=0.0, volume_expansion=0.0,
            trend_ok=False, rationale="no_pivot_in_age_window",
        )

    pivot_idx, pivot_low = max(eligible_pivots, key=lambda p: p[0])
    pivot_age = int(n_hist - pivot_idx)

    undercut = today_low < pivot_low
    reclaim = today_close > pivot_low

    if not undercut or not reclaim:
        rationale = "no_undercut" if not undercut else "no_reclaim"
        return UndercutRallyResult(
            score=0.0, detected=False, pivot_low=pivot_low, pivot_age_bars=int(pivot_age),
            today_low=today_low, today_close=today_close,
            undercut_depth_pct=0.0, reclaim_pct=0.0, volume_expansion=0.0,
            trend_ok=False, rationale=rationale,
        )

    undercut_depth_pct = max(0.0, (pivot_low - today_low) / max(pivot_low, 1e-9))
    reclaim_pct = max(0.0, (today_close - pivot_low) / max(pivot_low, 1e-9))

    avg_vol_20 = float(history["Volume"].tail(20).mean()) if len(history) >= 20 else float(history["Volume"].mean())
    vol_expansion = float(today_volume / max(avg_vol_20, 1.0))

    closes = sub["Close"].astype(float)
    ema_50 = closes.ewm(span=50, adjust=False, min_periods=20).mean().iloc[-1] if len(closes) >= 20 else closes.mean()
    trend_drawdown = (today_close - float(ema_50)) / max(float(ema_50), 1e-9)
    trend_ok = (trend_drawdown >= -invalidate_pct)

    if require_trend and not trend_ok:
        return UndercutRallyResult(
            score=0.0, detected=True, pivot_low=pivot_low, pivot_age_bars=int(pivot_age),
            today_low=today_low, today_close=today_close,
            undercut_depth_pct=float(undercut_depth_pct),
            reclaim_pct=float(reclaim_pct),
            volume_expansion=float(vol_expansion),
            trend_ok=bool(trend_ok),
            rationale="trend_broken",
        )

    depth_score = float(np.clip(undercut_depth_pct / 0.03, 0.0, 1.0))
    reclaim_score = float(np.clip(reclaim_pct / 0.02, 0.0, 1.0))
    vol_score = float(np.clip((vol_expansion - 1.0) / max(vol_expand_target - 1.0, 1e-6), 0.0, 1.0))
    trend_bonus = 1.0 if trend_ok else 0.6

    score = trend_bonus * (0.40 * depth_score + 0.40 * reclaim_score + 0.20 * vol_score)
    score = float(np.clip(score, 0.0, 1.0))

    return UndercutRallyResult(
        score=score,
        detected=bool(score > 0.0),
        pivot_low=float(pivot_low),
        pivot_age_bars=int(pivot_age),
        today_low=float(today_low),
        today_close=float(today_close),
        undercut_depth_pct=float(undercut_depth_pct),
        reclaim_pct=float(reclaim_pct),
        volume_expansion=float(vol_expansion),
        trend_ok=bool(trend_ok),
        rationale="undercut_and_rally",
    )
