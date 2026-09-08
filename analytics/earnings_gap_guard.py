"""Earnings print gap kill / pre-print size cap / STICK add-block.

WMT 2026-08-20: overnight STICK held 9% of equity into a BMO dump (−9% / −$632).
Thesis-death ran after the cash close; the forced sell sat above the live ask.

This module does not flatten the book and does not disable overnight STICK.
It kills a held name only when the print is live and the session gap is a dump,
and clips oversized names into dte≤1 down to the event cap (not to zero).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _b(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _i(val: Any) -> int | None:
    if val is None or val == "":
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _now_et(now_et: datetime | None = None) -> datetime:
    if now_et is not None:
        if now_et.tzinfo is None:
            return now_et.replace(tzinfo=ET)
        return now_et.astimezone(ET)
    return datetime.now(ET)


def guard_enabled() -> bool:
    return _b("EARNINGS_GAP_GUARD", True)


def gap_kill_pct() -> float:
    """Negative fraction (default −3.5%)."""
    raw = _f("EARNINGS_GAP_KILL_PCT", -0.035)
    return -abs(raw) if raw != 0 else -0.035


def event_max_equity_frac() -> float:
    return max(0.01, min(0.20, _f("EARNINGS_EVENT_MAX_EQUITY_FRAC", 0.045)))


def severe_abort_pct() -> float:
    return -abs(_f("FORTRESS_EARNINGS_SEVERE_ABORT_LOSS", 0.045))


def session_gap_from_pos(
    pos: dict[str, Any] | None,
    *,
    last: float | None = None,
    prev_close: float | None = None,
) -> float | None:
    """Session gap vs prior close (not vs cost). Alpaca `change_today` / last vs lastday."""
    if prev_close is not None and float(prev_close) > 0:
        px = last
        if px is None and pos:
            try:
                px = float(pos.get("current_price") or 0) or None
            except (TypeError, ValueError):
                px = None
        if px is not None and float(px) > 0:
            return float(px) / float(prev_close) - 1.0
    if not pos:
        return None
    for k in ("unrealized_intraday_plpc", "change_today"):
        v = pos.get(k)
        if v is None or v == "":
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    try:
        prev = float(pos.get("lastday_price") or 0)
        cur = float(last if last is not None else pos.get("current_price") or 0)
        if prev > 0 and cur > 0:
            return cur / prev - 1.0
    except (TypeError, ValueError):
        pass
    return None


def in_print_window(dte: Any, dse: Any) -> bool:
    """Calendar print neighborhood (dte=0 or 0≤dse≤1). Not the same as 'print is out'."""
    dte_i = _i(dte)
    dse_i = _i(dse)
    if dte_i == 0:
        return True
    if dse_i is not None and 0 <= dse_i <= 1:
        return True
    return False


def print_has_released(
    hour: str | None,
    dte: Any,
    dse: Any,
    *,
    now_et: datetime | None = None,
) -> bool:
    """True after the scheduled print — STICK / FORCE add is over.

    BMO: 08:00 ET. AMC: 16:05 ET. Unknown hour treated as AMC so daytime
    SBUX-style STICK still works until the close.
    """
    dte_i = _i(dte)
    dse_i = _i(dse)
    if dse_i is not None and dse_i >= 0 and (dte_i is None or dte_i > 0):
        return True
    if dte_i is None or dte_i > 0:
        return False
    t = _now_et(now_et).time()
    h = str(hour or "").strip().lower()
    if h == "bmo":
        return t >= time(8, 0)
    return t >= time(16, 5)


def print_gap_is_live(
    hour: str | None,
    dte: Any,
    dse: Any,
    *,
    now_et: datetime | None = None,
) -> bool:
    """True when a session gap is the earnings print, not a pre-AMC red day.

    BMO dte=0 from 04:00 ET (premarket print). AMC dte=0 only after 16:00 ET.
    Unknown hour: BMO-risk in premarket, AMC-safe in RTH, live after 16:00.
    """
    dse_i = _i(dse)
    if dse_i is not None and 0 <= dse_i <= 1:
        return True
    dte_i = _i(dte)
    if dte_i is None or dte_i > 0:
        return False
    t = _now_et(now_et).time()
    h = str(hour or "").strip().lower()
    if h == "bmo":
        return t >= time(4, 0)
    if h == "amc":
        return t >= time(16, 0)
    if t < time(9, 30):
        return t >= time(4, 0)
    return t >= time(16, 0)


def should_kill_gap(
    *,
    dte: Any,
    dse: Any,
    hour: str | None = None,
    gap: float | None = None,
    gain_vs_entry: float | None = None,
    now_et: datetime | None = None,
) -> bool:
    """Independent of 5d pressure / p_adj. One vote is enough."""
    if not guard_enabled():
        return False
    kill_at = gap_kill_pct()
    severe = severe_abort_pct()
    live = print_gap_is_live(hour, dte, dse, now_et=now_et)
    dte_i = _i(dte)
    dse_i = _i(dse)
    day_of = dte_i == 0 or (dse_i is not None and 0 <= dse_i <= 1)
    if gap is not None:
        g = float(gap)
        if live and g <= kill_at:
            return True
        # Missing hour / AMC still in RTH: still cut a WMT-class (−4.5%+) day-of dump.
        if day_of and g <= severe:
            return True
        return False
    if gain_vs_entry is not None:
        # No session quote: only the severe vs-entry abort (do not confuse drift with a print gap).
        return day_of and float(gain_vs_entry) <= severe
    return False


def pre_print_trim_frac(mv: float, equity: float, dte: Any) -> float:
    """Fraction of the *position* to sell so leftover ≈ event cap. Never 1.0."""
    if equity <= 0 or mv <= 0:
        return 0.0
    dte_i = _i(dte)
    if dte_i not in (0, 1):
        return 0.0
    cap = event_max_equity_frac()
    frac = float(mv) / float(equity)
    if frac <= cap:
        return 0.0
    return min(0.95, 1.0 - (cap / frac))


def block_stick_buy(
    *,
    dte: Any,
    dse: Any,
    hour: str | None = None,
    gap: float | None = None,
    now_et: datetime | None = None,
) -> bool:
    """No FORCE/STICK add after the print, or on a live red print gap."""
    if not guard_enabled():
        return False
    if print_has_released(hour, dte, dse, now_et=now_et):
        return True
    if print_gap_is_live(hour, dte, dse, now_et=now_et) and gap is not None and float(gap) < 0:
        return True
    if should_kill_gap(dte=dte, dse=dse, hour=hour, gap=gap, now_et=now_et):
        return True
    return False


@dataclass
class GapDecision:
    kill: bool
    trim_frac: float
    block_add: bool
    watch: bool
    reason: str


def decide(
    *,
    dte: Any,
    dse: Any,
    hour: str | None = None,
    gap: float | None = None,
    gain_vs_entry: float | None = None,
    mv: float = 0.0,
    equity: float = 0.0,
    now_et: datetime | None = None,
    fear_dump: bool = False,
) -> GapDecision:
    """Pure decision for one holding. No network."""
    if not guard_enabled():
        return GapDecision(False, 0.0, False, False, "disabled")
    watch = bool(fear_dump) or in_print_window(dte, dse) or print_gap_is_live(
        hour, dte, dse, now_et=now_et
    )
    kill = should_kill_gap(
        dte=dte,
        dse=dse,
        hour=hour,
        gap=gap,
        gain_vs_entry=gain_vs_entry,
        now_et=now_et,
    )
    block = block_stick_buy(dte=dte, dse=dse, hour=hour, gap=gap, now_et=now_et)
    if kill:
        why = f"gap_kill gap={gap} dte={dte} dse={dse} hour={hour}"
        return GapDecision(True, 1.0, True, True, why)
    trim = pre_print_trim_frac(mv, equity, dte)
    if trim > 0:
        why = f"pre_print_trim frac={trim:.3f} mv={mv:.0f} eq={equity:.0f} dte={dte}"
        return GapDecision(False, trim, block, watch, why)
    if block:
        return GapDecision(False, 0.0, True, watch, "block_stick_add")
    if watch:
        return GapDecision(False, 0.0, False, True, "print_window_watch")
    return GapDecision(False, 0.0, False, False, "ok")


def prioritize_print_window_holdings(
    syms: list[str],
    held: list[str],
    watch: list[str],
) -> list[str]:
    """Print-window holdings tick 1..n; keep the rest of the scan order (underdeploy fill)."""
    watch_u: list[str] = []
    seen_w: set[str] = set()
    for s in watch:
        u = str(s or "").strip().upper()
        if u and u not in seen_w:
            seen_w.add(u)
            watch_u.append(u)
    rest: list[str] = []
    seen_r: set[str] = set(seen_w)
    for s in list(syms) + list(held):
        u = str(s or "").strip().upper()
        if u and u not in seen_r:
            seen_r.add(u)
            rest.append(u)
    return watch_u + rest
