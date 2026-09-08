"""Cancel→resubmit fingerprint.

The same symbol/side was being cancelled then fired again on the next pass
(HFT IOC miss, fortress offlist cancel). Block that exact repeat for a window
without shrinking the universe or disabling sleeves.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _path() -> Path:
    return Path(os.getenv("CANCEL_FINGERPRINT_FILE", str(ROOT / "data" / "ops" / "cancel_fingerprint.json")))


def _ttl_sec() -> float:
    try:
        return max(30.0, float(os.getenv("REBUY_AFTER_CANCEL_SEC", "900")))
    except (TypeError, ValueError):
        return 900.0


def _load() -> dict[str, Any]:
    p = _path()
    if not p.is_file():
        return {"cancels": []}
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"cancels": []}
    if not isinstance(doc, dict):
        return {"cancels": []}
    rows = doc.get("cancels")
    if not isinstance(rows, list):
        doc["cancels"] = []
    return doc


def _save(doc: dict[str, Any]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def record_cancel(symbol: str, *, side: str = "buy", reason: str = "") -> None:
    sym = str(symbol or "").strip().upper()
    if not sym:
        return
    now = time.time()
    ttl = _ttl_sec()
    doc = _load()
    rows = [r for r in (doc.get("cancels") or []) if isinstance(r, dict)]
    rows = [r for r in rows if now - float(r.get("ts") or 0) < ttl * 4]
    rows.append(
        {
            "symbol": sym,
            "side": str(side or "buy").lower(),
            "reason": str(reason or "")[:80],
            "ts": now,
        }
    )
    doc["cancels"] = rows[-400:]
    _save(doc)


def recently_cancelled(symbol: str, *, side: str = "buy", seconds: float | None = None) -> bool:
    sym = str(symbol or "").strip().upper()
    if not sym:
        return False
    ttl = float(seconds) if seconds is not None else _ttl_sec()
    now = time.time()
    side_l = str(side or "buy").lower()
    for r in _load().get("cancels") or []:
        if not isinstance(r, dict):
            continue
        if str(r.get("symbol") or "").upper() != sym:
            continue
        if str(r.get("side") or "buy").lower() != side_l:
            continue
        if now - float(r.get("ts") or 0) <= ttl:
            return True
    return False
