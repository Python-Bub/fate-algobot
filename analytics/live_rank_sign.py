"""Live rank sign — fade 1d heads when they keep going red after the open.

The 1d model is trained on next-close direction. Premarket/open can print a
green spike; the rest of RTH then mean-reverts those same names. After the
open window (default 10:15 ET) invert p_up for NEW buys only. Holdings still
use the raw model score so we never dump a long just because we flipped sign.
"""

from __future__ import annotations

import json
import os
import time
from datetime import time as dtime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "ops" / "live_rank_sign.json"

_CACHE: dict[str, Any] = {"t": 0.0, "invert": False, "raw": ""}


def _truthy(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() in ("1", "true", "yes", "on")


def reset_invert_cache() -> None:
    _CACHE.update(t=0.0, invert=False, raw="")


def invert_p_up_enabled() -> bool:
    # Idle cash: follow the 1d head. Invert parks 40%+ cash in a bull tape.
    if os.getenv("FORTRESS_FILL_NO_INVERT", "true").lower() in (
        "1",
        "true",
        "yes",
        "on",
    ) and os.getenv("DOWNPRESS_SOFT_OK_WHEN_UNDERDEPLOY", "false").lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return False
    raw = os.getenv("FORTRESS_INVERT_P_UP", "auto").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    now = time.time()
    try:
        ttl = float(os.getenv("FORTRESS_INVERT_CACHE_SEC", "15"))
    except (TypeError, ValueError):
        ttl = 15.0
    if _CACHE.get("raw") == raw and now - float(_CACHE["t"]) < max(0.0, ttl):
        return bool(_CACHE["invert"])
    inv = _auto_invert()
    _CACHE.update(t=now, invert=inv, raw=raw)
    return inv


def _rth_after_open_fade() -> bool:
    """After the open spike, 1d heads mean-revert — fade new buys.

    Opt-in: flipping EVERY name after 10:15 ET inverts a working 1d head and
    is a common reason the book never earns. Keep the hook; default off.
    Set FORTRESS_INVERT_AFTER_OPEN=true to restore the old always-on fade.
    """
    if os.getenv("FORTRESS_INVERT_AFTER_OPEN", "false").lower() not in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return False
    try:
        from analytics.market_session import Session, current_session, now_et

        dt = now_et()
        if current_session(dt) != Session.REGULAR:
            return False
        raw = os.getenv("FORTRESS_INVERT_AFTER_ET", "10:15").strip() or "10:15"
        parts = raw.split(":")
        after = dtime(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
        return dt.time() >= after
    except Exception:
        return False


def _auto_invert() -> bool:
    """Invert after the open fade window, or when the live book is mostly red."""
    if _rth_after_open_fade():
        _write_state({"invert": True, "reason": "rth_after_open"})
        return True

    min_n = int(os.getenv("FORTRESS_INVERT_MIN_NAMES", "4"))
    red_frac = float(os.getenv("FORTRESS_INVERT_RED_FRAC", "0.55"))
    try:
        from alpaca_broker import list_positions

        pos = [
            p
            for p in (list_positions() or [])
            if abs(float(p.get("qty") or 0)) > 1e-8
        ]
    except Exception:
        pos = []
        try:
            if STATE_PATH.is_file():
                st = json.loads(STATE_PATH.read_text(encoding="utf-8"))
                return bool(st.get("invert"))
        except Exception:
            return False
    from analytics.position_gain import sane_unrealized_gain

    judged = []
    for p in pos:
        g = sane_unrealized_gain(p)
        if g is None:
            continue
        judged.append(g)
    n = len(judged)
    if n < min_n:
        _write_state({"invert": False, "n": n, "red": 0, "red_frac": 0.0, "reason": "too_few"})
        return False
    red = sum(1 for g in judged if g < 0)
    invert = (red / n) >= red_frac
    _write_state(
        {
            "invert": invert,
            "n": n,
            "red": red,
            "red_frac": round(red / n, 3),
            "reason": "book_red" if invert else "book_ok",
        }
    )
    return invert


def _write_state(st: dict[str, Any]) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(st, indent=2), encoding="utf-8")
    except Exception:
        pass


def apply_live_sign(p_up: float) -> float:
    """Map score used for NEW buys. Holdings still use the raw model score."""
    p = float(p_up)
    if not invert_p_up_enabled():
        return p
    return max(0.0, min(1.0, 1.0 - p))


def entry_confidence_ok(
    p_entry: float,
    exec_c: float,
    min_p: float,
    min_exec: float,
) -> bool:
    """Fade names sit near 0.5, so exec-certainty (abs(p-0.5)) would zero every fill.

    When the 1d head is inverted, require p_entry >= FORTRESS_FADE_MIN_P (default 0.50)
    and skip the execution-confidence chase bar.
    """
    if invert_p_up_enabled():
        try:
            floor = float(os.getenv("FORTRESS_FADE_MIN_P", os.getenv("MATH_P_UP_FLOOR", "0.50")))
        except (TypeError, ValueError):
            floor = 0.50
        # Fade still has to clear the live confidence bar — 0.50 inverted junk is how the book bled.
        return float(p_entry) >= max(float(floor), float(min_p))
    try:
        from analytics.execution_confidence import (
            passes_confidence_gates,
            use_execution_confidence_gate,
        )

        if use_execution_confidence_gate():
            return passes_confidence_gates(p_entry, exec_c, min_p, min_exec)
    except Exception:
        pass
    return float(p_entry) >= float(min_p)


def exit_p_up(p_up: float) -> float:
    """Exits never invert — selling on a flipped score dumped ORCL."""
    return float(p_up)
