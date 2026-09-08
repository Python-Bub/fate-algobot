"""Load and apply auto-evolved strategy overlay (data/self_improve/strategy_overlay.py)."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType

OVERLAY_PATH = Path(os.getenv("SELF_IMPROVE_OVERLAY_PATH", "data/self_improve/strategy_overlay.py"))
_CACHE: ModuleType | None = None
_CACHE_MTIME: float = 0.0


def overlay_enabled() -> bool:
    return os.getenv("SELF_IMPROVE_ENABLED", "true").lower() in ("1", "true", "yes")


def _load_module() -> ModuleType | None:
    global _CACHE, _CACHE_MTIME
    if not overlay_enabled() or not OVERLAY_PATH.is_file():
        return None
    try:
        mtime = OVERLAY_PATH.stat().st_mtime
    except OSError:
        return None
    if _CACHE is not None and mtime == _CACHE_MTIME:
        return _CACHE
    spec = importlib.util.spec_from_file_location("fate_strategy_overlay", OVERLAY_PATH)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception:
        return None
    _CACHE = mod
    _CACHE_MTIME = mtime
    return mod


def hf_weight_deltas() -> dict[str, float]:
    mod = _load_module()
    if mod is None or not hasattr(mod, "hf_weight_deltas"):
        return {}
    try:
        raw = mod.hf_weight_deltas()
        if not isinstance(raw, dict):
            return {}
        out: dict[str, float] = {}
        for k, v in raw.items():
            if str(k).startswith("HF_W_"):
                dv = float(v)
                # Overlay may only nudge — never invert a sleeve factor sign.
                out[str(k)] = float(max(-0.08, min(0.08, dv)))
        return out
    except Exception:
        return {}


def rank_tilt(symbol: str, p_up: float, metrics: dict | None = None) -> float:
    mod = _load_module()
    if mod is None or not hasattr(mod, "rank_tilt"):
        return 0.0
    try:
        return float(mod.rank_tilt(str(symbol).upper(), float(p_up), dict(metrics or {})))
    except Exception:
        return 0.0


def policy_hints(metrics: dict | None = None) -> dict:
    mod = _load_module()
    if mod is None or not hasattr(mod, "policy_hints"):
        return {}
    try:
        raw = mod.policy_hints(dict(metrics or {}))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def paper_score_boost(symbol: str, score: float, metrics: dict | None = None) -> float:
    mod = _load_module()
    if mod is None or not hasattr(mod, "paper_score_boost"):
        return 0.0
    try:
        return float(mod.paper_score_boost(str(symbol).upper(), float(score), dict(metrics or {})))
    except Exception:
        return 0.0


def hft_confidence_delta(metrics: dict | None = None) -> float:
    mod = _load_module()
    if mod is None or not hasattr(mod, "hft_confidence_delta"):
        return 0.0
    try:
        return float(mod.hft_confidence_delta(dict(metrics or {})))
    except Exception:
        return 0.0


def beat_market_mode(metrics: dict | None = None) -> bool:
    mod = _load_module()
    if mod is None or not hasattr(mod, "beat_market_mode"):
        return False
    try:
        return bool(mod.beat_market_mode(dict(metrics or {})))
    except Exception:
        return False


def invalidate_cache() -> None:
    global _CACHE, _CACHE_MTIME
    _CACHE = None
    _CACHE_MTIME = 0.0
    name = "fate_strategy_overlay"
    if name in sys.modules:
        del sys.modules[name]
