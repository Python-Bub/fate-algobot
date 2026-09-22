"""Runtime-generated subtle-tie detectors. Archived, never deleted."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

DIR = Path(__file__).resolve().parent
REGISTRY = DIR / "_registry.json"
ARCHIVE = DIR / "archive"

_CACHE: list[object] = []


def register_detector(
    *,
    file_stem: str,
    detector_id: str,
    kind: str,
    symbols: list[str],
    score: float,
    rationale: str,
    path: str,
) -> None:
    """Upsert a detector into the on-disk registry. Never deletes old entries."""
    doc: dict[str, Any] = {"detectors": []}
    if REGISTRY.is_file():
        try:
            loaded = json.loads(REGISTRY.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                doc = loaded
        except Exception:
            pass
    rows = list(doc.get("detectors") or [])
    entry = {
        "file_stem": file_stem,
        "detector_id": detector_id,
        "kind": kind,
        "symbols": list(symbols),
        "score": float(score),
        "rationale": rationale,
        "path": path,
        "enabled": True,
    }
    out = [r for r in rows if str(r.get("detector_id") or "") != detector_id]
    out.append(entry)
    doc["detectors"] = out
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def load_generated_detectors(*, force: bool = False) -> list[object]:
    """Import every ``pat_*.py`` detector. ``force=True`` busts the process cache."""
    global _CACHE
    if _CACHE and not force:
        return list(_CACHE)
    mods: list[object] = []
    if not DIR.is_dir():
        _CACHE = []
        return []
    for path in sorted(DIR.glob("pat_*.py")):
        spec = importlib.util.spec_from_file_location(
            f"analytics.generated_patterns.{path.stem}", path
        )
        if spec is None or spec.loader is None:
            continue
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except Exception:
            continue
        mods.append(mod)
    _CACHE = mods
    return list(_CACHE)
