"""Guarded policy adaptation for bottom-fisher weights (extends self_modify pattern)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from utils import log

STATE_PATH = Path(os.getenv("BOTTOM_FISHER_POLICY_STATE", "data/bottom_fisher/policy_state.json"))
OVERRIDE_PATH = Path(os.getenv("BOTTOM_FISHER_POLICY_OVERRIDES", "data/bottom_fisher/policy_overrides.json"))

_BOUNDS = {
    "RANK_W_BOTTOM_FISHER": (0.0, 1.2),
    "BOTTOM_FISHER_MIN_RECOVERY": (0.25, 0.75),
    "BOTTOM_FISHER_W_RECOVERY": (0.2, 0.7),
    "BOTTOM_FISHER_W_NEWS": (0.05, 0.5),
    "BOTTOM_FISHER_W_AI": (0.05, 0.5),
}


def _load(path: Path, default: dict) -> dict:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


@dataclass
class BottomFisherPolicyAgent:
    """Tune bottom-fisher blend weights from recent pick outcomes."""

    enabled: bool = True

    def __post_init__(self) -> None:
        self.enabled = os.getenv("BOTTOM_FISHER_POLICY_ENABLED", "true").lower() in ("1", "true", "yes")

    def propose(self, metrics: dict) -> dict[str, float]:
        """metrics: hit_rate, avg_return, n_picks from last scan cycle."""
        hit = float(metrics.get("hit_rate", 0.5))
        avg_ret = float(metrics.get("avg_return", 0.0))
        changes: dict[str, float] = {}
        cur_w = float(os.getenv("RANK_W_BOTTOM_FISHER", "0.55"))
        cur_min = float(os.getenv("BOTTOM_FISHER_MIN_RECOVERY", "0.42"))
        if hit > 0.58 and avg_ret > 0.002:
            changes["RANK_W_BOTTOM_FISHER"] = min(0.85, cur_w + 0.04)
            changes["BOTTOM_FISHER_MIN_RECOVERY"] = max(0.35, cur_min - 0.02)
        elif hit < 0.42 or avg_ret < -0.005:
            changes["RANK_W_BOTTOM_FISHER"] = max(0.15, cur_w - 0.06)
            changes["BOTTOM_FISHER_MIN_RECOVERY"] = min(0.65, cur_min + 0.03)
        return changes

    def apply_if_valid(self, changes: dict[str, float], metrics: dict) -> dict:
        if not self.enabled or not changes:
            return {"applied": False, "reason": "disabled"}
        accepted: dict[str, float] = {}
        for k, v in changes.items():
            lo, hi = _BOUNDS.get(k, (0.0, 10.0))
            if lo <= v <= hi:
                accepted[k] = float(v)
        if not accepted:
            return {"applied": False, "reason": "no_valid_changes"}
        cur = _load(OVERRIDE_PATH, {})
        cur.update(accepted)
        cur["updated_at"] = datetime.now(timezone.utc).isoformat()
        cur["metrics"] = metrics
        _save(OVERRIDE_PATH, cur)
        st = _load(STATE_PATH, {})
        st["last_apply"] = cur["updated_at"]
        st["accepted"] = accepted
        _save(STATE_PATH, st)
        log.info("[BOTTOM_FISHER] policy applied %s", accepted)
        return {"applied": True, "accepted": accepted}

    def observe_and_adapt(self, metrics: dict) -> dict:
        return self.apply_if_valid(self.propose(metrics), metrics)


def runtime_env_overrides() -> dict[str, str]:
    """Merge policy overrides into subprocess env."""
    data = _load(OVERRIDE_PATH, {})
    out = {}
    for k in _BOUNDS:
        if k in data:
            out[k] = str(data[k])
    return out
