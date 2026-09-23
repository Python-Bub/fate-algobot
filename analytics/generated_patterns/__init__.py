"""Hot-load auto-written subtle pattern detectors (never delete modules).

Each `pat_*.py` must define:
  DETECTOR_ID: str
  FAMILY: str   # usually "gen"
  SYMBOLS: tuple[str, ...]
  def detect(ctx) -> tuple[float, int, str, dict]
"""

from __future__ import annotations

import importlib.util
import json
import os
import time
from pathlib import Path
from typing import Any, Callable

DIR = Path(__file__).resolve().parent
REGISTRY = DIR / "_registry.json"
ARCHIVE = DIR / "archive"

_CACHE: dict[str, Any] = {"mtime": 0.0, "mods": []}


def _b(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in ("1", "true", "yes", "on")


def load_registry() -> dict[str, Any]:
    if not REGISTRY.is_file():
        return {"detectors": {}, "updated": 0}
    try:
        return json.loads(REGISTRY.read_text(encoding="utf-8"))
    except Exception:
        return {"detectors": {}, "updated": 0}


def save_registry(doc: dict[str, Any]) -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    doc["updated"] = time.time()
    tmp = REGISTRY.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, REGISTRY)


def _module_mtime_max() -> float:
    mt = REGISTRY.stat().st_mtime if REGISTRY.is_file() else 0.0
    for p in DIR.glob("pat_*.py"):
        try:
            mt = max(mt, p.stat().st_mtime)
        except OSError:
            pass
    return mt


def load_generated_detectors(*, force: bool = False) -> list[Any]:
    """Return loaded modules (enabled only). Cached by directory mtime."""
    if not _b("USE_GENERATED_PATTERNS", True):
        return []
    mt = _module_mtime_max()
    if not force and _CACHE["mods"] and abs(mt - float(_CACHE["mtime"])) < 1e-6:
        return list(_CACHE["mods"])

    reg = load_registry()
    det_meta = reg.get("detectors") or {}
    mods: list[Any] = []
    for path in sorted(DIR.glob("pat_*.py")):
        did = path.stem  # pat_xxx
        meta = det_meta.get(did) or det_meta.get(path.name) or {}
        if meta.get("disabled") is True:
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"analytics.generated_patterns.{path.stem}", path)
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if not hasattr(mod, "detect") or not hasattr(mod, "DETECTOR_ID"):
                continue
            mods.append(mod)
        except Exception:
            continue
    _CACHE["mtime"] = mt
    _CACHE["mods"] = mods
    return list(mods)


def detectors_for_symbol(symbol: str) -> list[Any]:
    sym = symbol.strip().upper()
    out = []
    for mod in load_generated_detectors():
        symbols = tuple(str(s).upper() for s in (getattr(mod, "SYMBOLS", ()) or ()))
        if not symbols or sym in symbols:
            out.append(mod)
    return out


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
    """Append/update registry — never deletes prior entries."""
    doc = load_registry()
    dets = doc.setdefault("detectors", {})
    # Keep history of prior versions under same id
    hist = list(doc.setdefault("history", []))
    if file_stem in dets:
        hist.append({**dets[file_stem], "superseded_at": time.time()})
    dets[file_stem] = {
        "detector_id": detector_id,
        "kind": kind,
        "symbols": [s.upper() for s in symbols],
        "score": float(score),
        "rationale": rationale[:400],
        "path": path,
        "created": time.time(),
        "disabled": False,
    }
    doc["history"] = hist[-500:]
    doc["n_detectors"] = len(dets)
    save_registry(doc)
    _CACHE["mtime"] = 0.0  # force reload
