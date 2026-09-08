"""Persist per-symbol execution constraints from algo risk warnings (sympathy trap, panic limit entry)."""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "data" / "trade_constraints.json"
ET = ZoneInfo("America/New_York")


def _path() -> Path:
    return Path(os.getenv("TRADE_CONSTRAINTS_PATH", str(DEFAULT_PATH)))


def _load() -> dict[str, Any]:
    p = _path()
    if not p.is_file():
        return {"version": 1, "symbols": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "symbols": {}}


def _save(doc: dict[str, Any]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    doc["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    p.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def save_constraints(symbol: str, constraints: dict[str, Any]) -> dict[str, Any]:
    sym = symbol.strip().upper()
    doc = _load()
    symbols = dict(doc.get("symbols") or {})
    payload = dict(constraints)
    payload["symbol"] = sym
    payload["saved_at_utc"] = datetime.now(timezone.utc).isoformat()
    symbols[sym] = payload
    doc["symbols"] = symbols
    _save(doc)
    return payload


def get_constraints(symbol: str) -> dict[str, Any]:
    sym = symbol.strip().upper()
    return dict((_load().get("symbols") or {}).get(sym) or {})


def load_constraints(symbol: str) -> dict[str, Any]:
    """Alias for get_constraints (legacy callers)."""
    return get_constraints(symbol)


def clear_constraints(symbol: str | None = None) -> None:
    doc = _load()
    if symbol is None:
        doc["symbols"] = {}
    else:
        symbols = dict(doc.get("symbols") or {})
        symbols.pop(symbol.strip().upper(), None)
        doc["symbols"] = symbols
    _save(doc)


def should_force_exit(symbol: str, *, now: datetime | None = None) -> tuple[bool, str]:
    """True when sympathy/time constraint requires flatten before peer earnings."""
    c = get_constraints(symbol)
    if not c:
        return False, ""
    now_et = (now or datetime.now(timezone.utc)).astimezone(ET)
    exit_date_s = c.get("force_exit_before_date")
    if exit_date_s:
        try:
            exit_d = date.fromisoformat(str(exit_date_s)[:10])
            if now_et.date() >= exit_d:
                hour = int(os.getenv("SYMPATHY_FORCE_EXIT_HOUR_ET", "15"))
                minute = int(os.getenv("SYMPATHY_FORCE_EXIT_MINUTE_ET", "45"))
                if now_et.date() > exit_d or (
                    now_et.hour > hour or (now_et.hour == hour and now_et.minute >= minute)
                ):
                    peer = c.get("sympathy_peer") or "peer"
                    return True, f"Sympathy trap exit — flatten before {peer} earnings ({exit_d})"
        except Exception:
            pass
    max_hold = c.get("max_hold_days")
    opened_s = c.get("opened_at_utc")
    if max_hold and opened_s:
        try:
            opened = datetime.fromisoformat(str(opened_s).replace("Z", "+00:00"))
            age_days = (now_et.date() - opened.astimezone(ET).date()).days
            if age_days >= int(max_hold):
                return True, f"Max hold {max_hold}d reached (sympathy trap)"
        except Exception:
            pass
    return False, ""


def take_profit_pct_for(symbol: str, default: float) -> float:
    c = get_constraints(symbol)
    if c.get("take_profit_pct") is not None:
        try:
            return float(c["take_profit_pct"])
        except Exception:
            pass
    return default
