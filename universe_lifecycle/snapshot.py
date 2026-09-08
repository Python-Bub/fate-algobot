"""Persist and diff the tradable US equity universe for new/delisted detection."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from universe_lifecycle.paths import SNAPSHOT_PATH


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_snapshot(path: Path | None = None) -> dict:
    p = path or SNAPSHOT_PATH
    if not p.is_file():
        return {"symbols": [], "updated_at_utc": None}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"symbols": [], "updated_at_utc": None}


def save_snapshot(symbols: list[str], path: Path | None = None) -> dict:
    p = path or SNAPSHOT_PATH
    doc = {
        "updated_at_utc": _now(),
        "count": len(symbols),
        "symbols": sorted({s.strip().upper() for s in symbols if s}),
    }
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return doc


def diff_universe(
    previous: list[str] | set[str],
    current: list[str] | set[str],
) -> dict[str, list[str]]:
    prev = {s.strip().upper() for s in previous if s}
    cur = {s.strip().upper() for s in current if s}
    return {
        "added": sorted(cur - prev),
        "removed": sorted(prev - cur),
        "unchanged_count": len(prev & cur),
    }
