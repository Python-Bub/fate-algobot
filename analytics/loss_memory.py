"""Names that just lost get a smaller next clip and a higher conviction bar.

A win clears the penalty. The name stays in the universe.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


def _path() -> Path:
    return Path(os.getenv("LOSS_MEMORY_PATH", "data/intel/loss_memory.json"))


def _load() -> dict[str, Any]:
    p = _path()
    if not p.is_file():
        return {"symbols": {}}
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"symbols": {}}
    if not isinstance(doc, dict):
        return {"symbols": {}}
    if not isinstance(doc.get("symbols"), dict):
        doc["symbols"] = {}
    return doc


def _save(doc: dict[str, Any]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def record_outcome(symbol: str, realized_return: float, *, source: str = "") -> None:
    sym = str(symbol or "").strip().upper()
    if not sym:
        return
    try:
        ret = float(realized_return)
    except (TypeError, ValueError):
        return
    doc = _load()
    rows = list((doc["symbols"].get(sym) or {}).get("trades") or [])
    rows.append(
        {
            "ret": ret,
            "ts": datetime.now(timezone.utc).isoformat(),
            "source": str(source or ""),
        }
    )
    doc["symbols"][sym] = {"trades": rows[-12:]}
    _save(doc)


def _et_day(ts: datetime) -> str:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(ZoneInfo("America/New_York")).date().isoformat()


def advise(symbol: str, *, now: datetime | None = None) -> dict[str, Any]:
    """size_mult 1 and extra_conviction 0 when the last close was not a loss.

    A loss closed today is not reopened today. The name is still tradable tomorrow, smaller.
    """
    sym = str(symbol or "").strip().upper()
    neutral = {
        "size_mult": 1.0,
        "extra_conviction": 0.0,
        "losses": 0,
        "same_day": False,
        "reason": "",
    }
    rows = list((_load()["symbols"].get(sym) or {}).get("trades") or [])
    if not rows:
        return neutral
    last = float(rows[-1].get("ret") or 0)
    if last >= 0:
        return neutral
    cur = now or datetime.now(timezone.utc)
    same_day = False
    try:
        closed = datetime.fromisoformat(str(rows[-1].get("ts") or "").replace("Z", "+00:00"))
        same_day = _et_day(closed) == _et_day(cur)
    except ValueError:
        same_day = False
    losses = sum(1 for r in rows[-5:] if float(r.get("ret") or 0) < 0)
    if same_day:
        return {
            "size_mult": 0.0,
            "extra_conviction": 1.0,
            "losses": losses,
            "same_day": True,
            "reason": "loss already closed today",
        }
    if losses >= 2:
        return {
            "size_mult": 0.25,
            "extra_conviction": 0.10,
            "losses": losses,
            "same_day": False,
            "reason": f"{losses} recent losses",
        }
    return {
        "size_mult": 0.45,
        "extra_conviction": 0.06,
        "losses": losses,
        "same_day": False,
        "reason": "last close was a loss",
    }
