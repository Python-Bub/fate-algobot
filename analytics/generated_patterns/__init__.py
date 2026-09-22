"""Runtime package for auto-written subtle-tie detectors.

Generated ``pat_*.py`` files live here (gitignored). This ``__init__.py`` is
kept in git so imports never fail on a fresh clone.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

DIR = Path(__file__).resolve().parent
REGISTRY = DIR / "_registry.json"
ARCHIVE = DIR / "archive"

_CACHE: list[Any] | None = None


def _load_registry() -> dict[str, Any]:
    if not REGISTRY.is_file():
        return {"detectors": []}
    try:
        return json.loads(REGISTRY.read_text(encoding="utf-8"))
    except Exception:
        return {"detectors": []}


def _save_registry(doc: dict[str, Any]) -> None:
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY.write_text(json.dumps(doc, indent=2), encoding="utf-8")


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
    doc = _load_registry()
    rows = [r for r in (doc.get("detectors") or []) if str(r.get("file_stem")) != file_stem]
    rows.append(
        {
            "file_stem": file_stem,
            "detector_id": detector_id,
            "kind": kind,
            "symbols": [str(s).upper() for s in symbols],
            "score": float(score),
            "rationale": rationale,
            "path": path,
            "enabled": True,
        }
    )
    doc["detectors"] = rows
    _save_registry(doc)
    global _CACHE
    _CACHE = None


def _load_module(path: Path):
    name = f"analytics.generated_patterns.{path.stem}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def load_generated_detectors(*, force: bool = False) -> list[Any]:
    global _CACHE
    if _CACHE is not None and not force:
        return list(_CACHE)
    out: list[Any] = []
    if DIR.is_dir():
        for p in sorted(DIR.glob("pat_*.py")):
            try:
                mod = _load_module(p)
                if mod is not None:
                    out.append(mod)
            except Exception:
                continue
    _CACHE = out
    return list(out)


def detectors_for_symbol(symbol: str) -> list[Any]:
    sym = str(symbol or "").strip().upper()
    rows = _load_registry().get("detectors") or []
    stems = {
        str(r.get("file_stem") or "")
        for r in rows
        if r.get("enabled", True) and sym in {str(s).upper() for s in (r.get("symbols") or [])}
    }
    mods = load_generated_detectors()
    if not stems:
        return mods
    return [m for m in mods if getattr(m, "__name__", "").rsplit(".", 1)[-1] in stems]
