"""First time we see an open lot. Later adds must not restart the hold clock."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _path() -> Path:
    return Path(os.getenv("POSITION_CLOCK_PATH", "data/ops/position_clock.json"))


def _load() -> dict[str, Any]:
    p = _path()
    if not p.is_file():
        return {}
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return doc if isinstance(doc, dict) else {}


def _save(doc: dict[str, Any]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def note_open(symbol: str, qty: float) -> None:
    """Remember the first open sight. qty<=0 clears the name. Adds keep the original since."""
    sym = str(symbol or "").strip().upper()
    if not sym:
        return
    doc = _load()
    try:
        q = float(qty or 0)
    except (TypeError, ValueError):
        q = 0.0
    if q <= 0:
        if sym in doc:
            doc.pop(sym, None)
            _save(doc)
        return
    row = doc.get(sym) if isinstance(doc.get(sym), dict) else None
    if not row or not row.get("since"):
        doc[sym] = {
            "since": datetime.now(timezone.utc).isoformat(),
            "qty": q,
        }
    else:
        row["qty"] = q
        doc[sym] = row
    _save(doc)


def age_minutes(symbol: str, *, now: datetime | None = None) -> float | None:
    sym = str(symbol or "").strip().upper()
    row = _load().get(sym)
    if not isinstance(row, dict) or not row.get("since"):
        return None
    try:
        since = datetime.fromisoformat(str(row["since"]).replace("Z", "+00:00"))
    except ValueError:
        return None
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    cur = now or datetime.now(timezone.utc)
    if cur.tzinfo is None:
        cur = cur.replace(tzinfo=timezone.utc)
    return max(0.0, (cur - since).total_seconds() / 60.0)
