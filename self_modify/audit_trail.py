"""Immutable-ish audit trail for adaptive policy changes."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


AUDIT_PATH = Path("data/policy/audit_trail.jsonl")


def _last_hash(path: Path) -> str:
    if not path.is_file():
        return ""
    last = ""
    with open(path, encoding="utf-8") as f:
        for ln in f:
            last = ln.strip()
    if not last:
        return ""
    try:
        obj = json.loads(last)
        return str(obj.get("hash", ""))
    except Exception:
        return ""


def log_audit(event_type: str, payload: dict) -> dict:
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    prev = _last_hash(AUDIT_PATH)
    body = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "payload": payload,
        "prev_hash": prev,
    }
    digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest()
    body["hash"] = digest
    with open(AUDIT_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(body, sort_keys=True) + "\n")
    return body

