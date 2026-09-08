"""Morning sweet-spot timing — lean into ~06:00–07:15 ET, cut the bleed elsewhere.

Observed pattern (paper):
  • before ~06:00 ET — book goes negative (noisy thin premarket)
  • ~06:00–07:00/07:15 — strong picks / equity rises
  • after that window (late pre + post-open fade) — soft exits / fade chop

This module:
  1) Gates new buys before the sweet spot
  2) Size-boosts during the sweet spot
  3) Protects soft exits on strong premarket names through open (hard stops still fire)
"""

from __future__ import annotations

import os
from datetime import datetime, time
from typing import Any  # noqa: F401 — kept for callers typing snapshots

from analytics.after_hours_intel import fetch_after_hours_snapshot


def _parse_hhmm(raw: str, default: time) -> time:
    s = (raw or "").strip()
    if not s:
        return default
    try:
        parts = s.split(":")
        return time(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
    except (TypeError, ValueError, IndexError):
        return default


def _now_et(dt: datetime | None = None) -> datetime:
    from analytics.market_session import now_et

    return dt or now_et()


def sweet_spot_enabled() -> bool:
    return os.getenv("MORNING_SWEET_SPOT", "true").lower() in ("1", "true", "yes")


def sweet_spot_bounds() -> tuple[time, time]:
    start = _parse_hhmm(os.getenv("MORNING_SWEET_START_ET", "06:00"), time(6, 0))
    end = _parse_hhmm(os.getenv("MORNING_SWEET_END_ET", "07:15"), time(7, 15))
    return start, end


def morning_phase(dt: datetime | None = None) -> str:
    """
    Return one of: weekend | pre_sweet | sweet | post_sweet | rth | post | closed

    pre_sweet  = before 06:00 (bleed zone — block/slow new buys)
    sweet      = 06:00–07:15 (focus / size up)
    post_sweet = 07:15–09:30 (caution — smaller size, stricter)
    rth        = regular hours
    """
    from analytics.market_session import Session, current_session, is_trading_day

    dt = _now_et(dt)
    if not is_trading_day(dt):
        return "weekend"
    sess = current_session(dt)
    t = dt.time()
    start, end = sweet_spot_bounds()
    if sess == Session.PRE_MARKET:
        if t < start:
            return "pre_sweet"
        if start <= t < end:
            return "sweet"
        return "post_sweet"
    if sess == Session.REGULAR:
        return "rth"
    if sess == Session.POST_MARKET:
        return "post"
    return "closed"


def morning_buy_allowed(*, for_hft: bool = False, dt: datetime | None = None) -> tuple[bool, str]:
    """Block new buys in the pre-6am bleed zone (HFT optional via env)."""
    if not sweet_spot_enabled():
        return True, "sweet_spot_off"
    phase = morning_phase(dt)
    if phase != "pre_sweet":
        return True, f"phase={phase}"
    if for_hft and os.getenv("HFT_ALLOW_PRE_SWEET", "false").lower() in ("1", "true", "yes"):
        return True, "hft_pre_sweet_allowed"
    return False, "pre_sweet_bleed_zone (wait until MORNING_SWEET_START_ET)"


def morning_entry_size_mult(*, for_hft: bool = False, dt: datetime | None = None) -> float:
    """Size tilt by morning phase — boost sweet spot, cut post-sweet caution."""
    if not sweet_spot_enabled():
        return 1.0
    phase = morning_phase(dt)
    if phase == "sweet":
        return float(os.getenv("MORNING_SWEET_SIZE_MULT", "1.20"))
    if phase == "post_sweet":
        return float(os.getenv("MORNING_POST_SWEET_SIZE_MULT", "0.65"))
    if phase == "pre_sweet":
        return float(os.getenv("MORNING_PRE_SWEET_SIZE_MULT", "0.0"))
    if phase == "rth":
        # Mild cut early RTH fade hour unless name is protected strong-PM.
        try:
            from analytics.market_session import rth_open_protect_window

            in_win, _ = rth_open_protect_window(dt)
            if in_win:
                return float(os.getenv("MORNING_RTH_OPEN_SIZE_MULT", "0.85"))
        except Exception:
            pass
    return 1.0


def premarket_protect_enabled() -> bool:
    return os.getenv("PREMARKET_OPEN_PROTECT", "true").lower() in ("1", "true", "yes")


def premarket_strong_pct() -> float:
    try:
        return float(os.getenv("PREMARKET_STRONG_PCT", "0.012"))
    except (TypeError, ValueError):
        return 0.012


def premarket_hold_bias(symbol: str) -> float:
    """[0,1] strength of premarket/AH green lean."""
    if not symbol:
        return 0.0
    try:
        snap = fetch_after_hours_snapshot(symbol)
    except Exception:
        return 0.0
    if not snap.get("ok"):
        return 0.0
    ret = float(snap.get("ah_return_pct") or 0.0)
    thresh = premarket_strong_pct()
    if ret < thresh:
        return 0.0
    span = max(thresh, 0.03)
    return max(0.0, min(1.0, (ret - thresh) / span * 0.45 + 0.55))


def should_protect_premarket_long(symbol: str) -> tuple[bool, str]:
    """Soft-exit protect for strong PM names during sweet→early RTH (not hard stops)."""
    if not premarket_protect_enabled():
        return False, "protect_off"
    phase = morning_phase()
    # Protect through sweet + post_sweet + early RTH open window.
    if phase in ("sweet", "post_sweet"):
        bias = premarket_hold_bias(symbol)
        min_bias = float(os.getenv("PREMARKET_PROTECT_MIN_BIAS", "0.45"))
        if bias < min_bias and phase == "post_sweet":
            # In sweet spot protect even mild greens; post-sweet needs clearer strength.
            return False, f"bias={bias:.2f}<{min_bias}"
        if bias < 0.35 and phase == "sweet":
            return False, f"bias={bias:.2f}"
        return True, f"phase={phase} bias={bias:.2f}"
    try:
        from analytics.market_session import rth_open_protect_window

        in_win, why = rth_open_protect_window()
    except Exception:
        return False, "session_err"
    if not in_win:
        return False, why
    bias = premarket_hold_bias(symbol)
    min_bias = float(os.getenv("PREMARKET_PROTECT_MIN_BIAS", "0.55"))
    if bias < min_bias:
        return False, f"bias={bias:.2f}<{min_bias}"
    return True, f"premarket_protect bias={bias:.2f} {why}"


def premarket_entry_size_mult(symbol: str = "", *, for_hft: bool = False) -> float:
    """Combine morning-phase size with optional strong-name bump."""
    base = morning_entry_size_mult(for_hft=for_hft)
    if base <= 0:
        return 0.0
    if not symbol or not premarket_protect_enabled():
        return base
    if os.getenv("PREMARKET_SIZE_BOOST", "true").lower() not in ("1", "true", "yes"):
        return base
    bias = premarket_hold_bias(symbol)
    if bias < 0.55:
        return base
    max_m = float(os.getenv("PREMARKET_SIZE_MULT", "1.12"))
    bump = 1.0 + (max_m - 1.0) * min(1.0, (bias - 0.55) / 0.45)
    return base * bump
