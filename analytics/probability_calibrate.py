"""Probability display + conservative gates.

Display (family forecast, reports): raw model % by default — preserves cross-symbol spread.
Gates (asymmetric filter): optional linear shrink into [CHANCE_PCT_MIN, CHANCE_PCT_MAX].

Env:
- CHANCE_DISPLAY_MODE=raw|calibrated  (default raw)
- CHANCE_PCT_FLOOR=5  CHANCE_PCT_CEIL=95  (display clip)
- CHANCE_PCT_MIN=8  CHANCE_PCT_MAX=92  (gate calibration band)
- USE_PROB_CALIBRATION=true
"""

from __future__ import annotations

import os
from typing import Any

import numpy as np


def calibration_enabled() -> bool:
    return os.getenv("USE_PROB_CALIBRATION", "true").lower() in ("1", "true", "yes")


def display_mode() -> str:
    return os.getenv("CHANCE_DISPLAY_MODE", "raw").strip().lower()


def _bounds() -> tuple[float, float]:
    lo = float(os.getenv("CHANCE_PCT_MIN", "8")) / 100.0
    hi = float(os.getenv("CHANCE_PCT_MAX", "92")) / 100.0
    if hi <= lo:
        hi = lo + 0.01
    return lo, hi


def _display_bounds() -> tuple[int, int]:
    lo = int(os.getenv("CHANCE_PCT_FLOOR", "5"))
    hi = int(os.getenv("CHANCE_PCT_CEIL", "95"))
    if hi <= lo:
        hi = lo + 1
    return lo, hi


def display_chance_pct(raw: float) -> int:
    """Integer % for humans — raw model output by default (not compressed toward 50%)."""
    r = float(np.clip(raw, 0.0, 1.0))
    if display_mode() == "calibrated":
        p_min, p_max = _bounds()
        if not calibration_enabled():
            cal = r
        else:
            cal = p_min + r * (p_max - p_min)
        return int(round(float(np.clip(cal, p_min, p_max)) * 100))
    lo, hi = _display_bounds()
    return int(np.clip(round(r * 100), lo, hi))


def calibrate_probability(raw: float) -> dict[str, Any]:
    """Gate calibration + display chance_pct (mode-dependent)."""
    r = float(np.clip(raw, 0.0, 1.0))
    p_min, p_max = _bounds()
    if not calibration_enabled():
        cal = r
    else:
        cal = p_min + r * (p_max - p_min)
    cal = float(np.clip(cal, p_min, p_max))
    return {
        "raw": r,
        "calibrated": cal,
        "chance_pct": display_chance_pct(r),
    }


def calibrate_horizon_probs(
    *,
    p_daily: float | None = None,
    p_short: float | None = None,
    p_long: float | None = None,
    p_xlong: float | None = None,
    p_daily_head: str | None = None,
    p_short_head: str | None = None,
    p_long_head: str | None = None,
    p_xlong_head: str | None = None,
) -> dict[str, Any]:
    """Per-horizon raw + gate-calibrated probs; display % from each head's raw output."""
    out: dict[str, Any] = {}
    for name, val, head in (
        ("p_daily", p_daily, p_daily_head),
        ("p_short", p_short, p_short_head),
        ("p_long", p_long, p_long_head),
        ("p_xlong", p_xlong, p_xlong_head),
    ):
        if val is None:
            continue
        c = calibrate_probability(float(val))
        out[f"{name}_model_raw"] = c["raw"]
        out[f"{name}_model"] = c["calibrated"]
        out[f"{name}_chance_pct"] = c["chance_pct"]
        if head:
            out[f"{name}_head"] = head
    return out
