"""Rest fillable DAY tickets. Do not cancel→reissue.

IOC + TTL-cancel burned Alpaca slots without ever approaching the 200/min
cap. Working DAY limits stay until they fill; unfillable buys are PATCH
repriced to the bid instead of DELETE+POST.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "intel" / "fill_persist_state.json"


def _b(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def enabled() -> bool:
    return _b("FILL_PERSIST", True)


def _load() -> dict[str, Any]:
    empty = {"fills": 0, "cancels": 0, "reprices": 0, "rests": 0, "updated": 0.0}
    if not STATE_PATH.is_file():
        return empty
    try:
        doc = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return empty
    if not isinstance(doc, dict):
        return empty
    empty.update({k: doc.get(k, v) for k, v in empty.items()})
    return empty


def _save(st: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    st["updated"] = time.time()
    STATE_PATH.write_text(json.dumps(st, indent=2), encoding="utf-8")


def record(kind: str) -> None:
    st = _load()
    key = {"fill": "fills", "cancel": "cancels", "reprice": "reprices", "rest": "rests"}.get(kind, "")
    if key:
        st[key] = int(st.get(key) or 0) + 1
        _save(st)


def fill_rate() -> float:
    st = _load()
    fills = float(st.get("fills") or 0)
    cancels = float(st.get("cancels") or 0)
    den = fills + cancels
    if den < 1:
        return 0.5
    return fills / den


def reprice_buy_limit(limit_px: float, bid: float, ask: float) -> float | None:
    """If the resting buy cannot lift, move it to the bid (maker, fillable).

    Never chase through a wide ask. None = leave the ticket.
    """
    from analytics.limit_pricing import buy_limit_unfillable, quote_is_sane, round_limit

    try:
        lim = float(limit_px)
        bp = float(bid)
        ap = float(ask)
    except (TypeError, ValueError):
        return None
    if not (lim > 0 and bp > 0 and ap >= bp):
        return None
    if not buy_limit_unfillable(lim, bp, ap):
        return None
    if not quote_is_sane(bp, ap):
        return None
    target = round_limit(bp)
    if target <= 0:
        return None
    if abs(target - lim) / max(lim, 1e-9) < 5e-4:
        return None
    return float(target)


def may_cancel_stale_buy(*, unfillable: bool, held_no_addon: bool) -> bool:
    """True only when the ticket must leave the book.

    Held + add-on off → cancel (don't stack). Unfillable + persist → reprice, don't cancel.
    """
    if held_no_addon:
        return True
    if enabled() and unfillable:
        return False
    return bool(unfillable)
