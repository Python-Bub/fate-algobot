"""Reinforcement learning layer for soft industry blend weights.

Learns from realized trade outcomes which industry neighbors best explain
each symbol's co-movement — updates affinity offsets without requiring
exact bucket membership.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RL_STATE_PATH = ROOT / "data" / "industry" / "industry_rl_state.json"
_MEM: dict[str, Any] | None = None


def _enabled() -> bool:
    return os.getenv("USE_INDUSTRY_RL", "true").lower() in ("1", "true", "yes")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_state(*, reload: bool = False) -> dict[str, Any]:
    global _MEM
    if _MEM is not None and not reload:
        return _MEM
    if not RL_STATE_PATH.is_file():
        _MEM = {"version": 1, "symbols": {}, "global": {}}
        return _MEM
    try:
        _MEM = json.loads(RL_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        _MEM = {"version": 1, "symbols": {}, "global": {}}
    return _MEM


def _save_state(doc: dict[str, Any]) -> None:
    global _MEM
    doc["updated_at_utc"] = _now()
    RL_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = RL_STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    os.replace(tmp, RL_STATE_PATH)
    _MEM = doc


def affinity_offsets(symbol: str) -> dict[str, float]:
    """Per-industry affinity adjustment learned from trade feedback."""
    if not _enabled():
        return {}
    sym = symbol.strip().upper()
    doc = _load_state()
    row = (doc.get("symbols") or {}).get(sym) or {}
    aff = row.get("affinities") or {}
    return {str(k): float(v) for k, v in aff.items()}


def apply_rl_to_blend(symbol: str, blend: dict[str, float]) -> dict[str, float]:
    """Scale blend weights by learned affinities; renormalize."""
    if not _enabled() or not blend:
        return dict(blend)
    aff = affinity_offsets(symbol)
    if not aff:
        return dict(blend)
    scale = float(os.getenv("INDUSTRY_RL_AFFINITY_SCALE", "0.35"))
    out: dict[str, float] = {}
    for iid, w in blend.items():
        adj = 1.0 + scale * aff.get(iid, 0.0)
        out[iid] = max(0.001, float(w) * adj)
    total = sum(out.values()) or 1.0
    return {k: round(v / total, 4) for k, v in out.items()}


def _clamp(v: float, lo: float = -0.45, hi: float = 0.45) -> float:
    return float(np.clip(v, lo, hi))


def update_from_trade(
    symbol: str,
    realized_return: float,
    side: str,
    *,
    blend_weights: dict[str, float] | None = None,
    reward: float | None = None,
    bars_held: int = 1,
) -> dict[str, Any]:
    """Contextual bandit update: reward industries that were active during the trade."""
    if not _enabled():
        return {"applied": False, "reason": "disabled"}
    sym = symbol.strip().upper()
    if not sym:
        return {"applied": False, "reason": "empty_symbol"}

    if reward is None:
        try:
            from analytics.asymmetric_loss import asymmetric_reward

            rw = asymmetric_reward(side, float(realized_return), bars_held=bars_held)
            reward = float(rw.reward)
        except Exception:
            reward = float(np.tanh(float(realized_return) * 8.0))

    blend = dict(blend_weights or {})
    if not blend:
        try:
            from analytics.industries.integration import get_industry_profile

            prof = get_industry_profile(sym, use_cache=True)
            blend = dict(prof.get("blend_weights") or {})
            if not blend:
                iid = prof.get("primary_industry_id")
                if iid and iid != "unclassified":
                    blend = {str(iid): 1.0}
        except Exception:
            blend = {}

    if not blend:
        return {"applied": False, "reason": "no_blend"}

    lr = float(os.getenv("INDUSTRY_RL_LEARNING_RATE", "0.06"))
    doc = _load_state(reload=True)
    symbols = doc.setdefault("symbols", {})
    row = symbols.setdefault(sym, {"affinities": {}, "updates": 0})
    aff: dict[str, float] = dict(row.get("affinities") or {})

    primary = max(blend.items(), key=lambda x: x[1])[0]
    for iid, w in blend.items():
        # Weighted policy gradient: industries with higher blend share get larger update
        delta = lr * float(reward) * float(w)
        if float(reward) < 0 and iid == primary:
            delta *= 1.35
        aff[iid] = _clamp(aff.get(iid, 0.0) + delta)

    row["affinities"] = {k: round(v, 5) for k, v in aff.items()}
    row["updates"] = int(row.get("updates") or 0) + 1
    row["last_reward"] = round(float(reward), 5)
    row["last_return"] = round(float(realized_return), 5)
    row["last_blend"] = blend
    row["updated_at_utc"] = _now()
    symbols[sym] = row

    glob = doc.setdefault("global", {})
    glob["total_updates"] = int(glob.get("total_updates") or 0) + 1
    glob["last_symbol"] = sym

    _save_state(doc)
    return {
        "applied": True,
        "symbol": sym,
        "reward": float(reward),
        "primary": primary,
        "affinities": aff,
        "updates": row["updates"],
    }


def global_industry_prior(industry_id: str) -> float:
    """Optional global affinity prior across all symbols."""
    doc = _load_state()
    g = (doc.get("global") or {}).get("industry_priors") or {}
    return float(g.get(industry_id, 0.0))
