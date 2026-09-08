"""Pure-math rank pivot — boost formulas/factors; score news as z, don't delete it.

When PURE_MATH_PIVOT=true (default), remaps rank component weights toward
hedge_fund / hidden_anomaly / cross_company / value / structure / ML and
softens raw narrative (RANK_W_SENT, Cramer chatter) while keeping news→z path.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OVERRIDES_PATH = ROOT / "data" / "intel" / "operator_math_overrides.json"


def pivot_enabled() -> bool:
    raw = os.getenv("PURE_MATH_PIVOT", "true")
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def load_operator_overrides() -> dict[str, float]:
    if not OVERRIDES_PATH.is_file():
        return {}
    try:
        data = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
        return {k: float(v) for k, v in (data.get("weight_mults") or {}).items()}
    except Exception:
        return {}


def save_operator_overrides(weight_mults: dict[str, float], *, note: str = "") -> None:
    """Operator AI may tune math weight multipliers here (optimize, never remove)."""
    OVERRIDES_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "weight_mults": {k: float(v) for k, v in weight_mults.items()},
        "note": note[:500],
    }
    OVERRIDES_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


# Components that are "math-first" vs "narrative"
_MATH_KEYS = frozenset(
    {
        "hedge_fund",
        "hidden_anomaly",
        "cross_company",
        "value_investing",
        "investing_book",
        "structure",
        "core",  # ML p_up dominated
        "exec_conf",
        "fund",
        "hmm",
        "bottom_fisher",
        "event_calendar",
        "event_learn",
        "event_ingenuity",
        "proven_online",
    }
)
_NEWS_KEYS = frozenset({"news", "transcript", "sent", "cramer", "social"})


def weight_multiplier(component: str) -> float:
    if not pivot_enabled():
        return 1.0
    math_m = _f("MATH_PIVOT_MATH_MULT", 1.35)
    news_m = _f("MATH_PIVOT_NEWS_MULT", 0.55)
    overrides = load_operator_overrides()
    key = component.strip().lower()
    if key in overrides:
        return float(overrides[key])
    if key in _MATH_KEYS:
        return math_m
    if key in _NEWS_KEYS:
        return news_m
    return 1.0


def apply_pivot_to_components(comps: dict[str, float]) -> dict[str, float]:
    """Scale component contributions in-place-friendly copy."""
    if not pivot_enabled():
        return dict(comps)
    out: dict[str, float] = {}
    for k, v in comps.items():
        out[k] = float(v) * weight_multiplier(k)
    return out


def fortress_news_rank_w() -> float:
    """Softer fortress news impulse under math pivot; still present."""
    base = _f("FORTRESS_NEWS_RANK_W", 0.10)
    if not pivot_enabled():
        return base
    return base * _f("MATH_PIVOT_NEWS_MULT", 0.55)


def sent_weight() -> float:
    base = _f("RANK_W_SENT", 0.15)
    if not pivot_enabled():
        return base
    return base * _f("MATH_PIVOT_NEWS_MULT", 0.55)


def pivot_status() -> dict[str, Any]:
    return {
        "pure_math_pivot": pivot_enabled(),
        "math_mult": _f("MATH_PIVOT_MATH_MULT", 1.35),
        "news_mult": _f("MATH_PIVOT_NEWS_MULT", 0.55),
        "overrides": load_operator_overrides(),
        "manifest": "analytics/math_manifest.md",
        "catalog": "analytics/math_catalog.py",
    }
