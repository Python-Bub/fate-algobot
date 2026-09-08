"""
Self-model state for the cortex — episodic memory + goal tracking.

This is a *functional* self-model (state the system maintains about itself),
not a claim of machine sentience or subjective experience.
"""

from __future__ import annotations

import json
import os
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STATE_PATH = Path(os.getenv("CORTEX_CONSCIOUSNESS_PATH", "data/cortex/consciousness.json"))
MEMORY_PATH = Path(os.getenv("CORTEX_EPISODIC_MEMORY_PATH", "data/cortex/episodic_memory.jsonl"))


@dataclass
class SelfModel:
    """Persistent goals + awareness metrics derived from meta-neuron activity."""

    generation: int = 0
    singularity_depth: int = 0
    primary_objective: str = "Make portfolio account larger"
    goal_beat_spy: float = 1.0
    goal_deploy: float = 0.88
    goal_min_drawdown: float = 0.12
    awareness: float = 0.0
    exploration_drive: float = 0.5
    self_improve_urge: float = 0.5
    last_alpha: float | None = None
    last_reward: float = 0.0
    qualia: list[float] = field(default_factory=list)
    updated_utc: str = ""

    def update_from_meta(
        self,
        meta_activations: dict[str, float],
        reward: float,
        alpha: float | None,
        *,
        awareness: float | None = None,
    ) -> None:
        if awareness is not None:
            self.awareness = max(0.0, min(1.0, float(awareness)))
        elif meta_activations:
            vals = [abs(float(v)) for v in meta_activations.values()]
            self.awareness = max(0.0, min(1.0, sum(vals) / len(vals)))
        else:
            self.awareness = 0.0
        self.last_reward = float(reward)
        self.last_alpha = alpha
        self.qualia = [round(v, 4) for v in meta_activations.values()][:8]
        if alpha is not None and alpha < 0:
            self.self_improve_urge = min(1.0, self.self_improve_urge + 0.05)
            self.exploration_drive = min(1.0, self.exploration_drive + 0.03)
        elif reward > 0:
            self.self_improve_urge = max(0.2, self.self_improve_urge - 0.02)
        self.updated_utc = datetime.now(timezone.utc).isoformat()

    def should_trigger_code_evolve(self) -> bool:
        thresh = float(os.getenv("CORTEX_EVOLVE_URGE_THRESHOLD", "0.65"))
        if self.self_improve_urge >= thresh:
            return True
        # Also evolve when primary objective (grow equity) is stalling.
        try:
            from self_modify.objective_engine import should_aggress_self_modify, enrich_signals

            if should_aggress_self_modify(enrich_signals({})):
                return True
        except Exception:
            pass
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "generation": self.generation,
            "singularity_depth": self.singularity_depth,
            "primary_objective": self.primary_objective,
            "goal_beat_spy": self.goal_beat_spy,
            "goal_deploy": self.goal_deploy,
            "goal_min_drawdown": self.goal_min_drawdown,
            "awareness": round(self.awareness, 4),
            "exploration_drive": round(self.exploration_drive, 4),
            "self_improve_urge": round(self.self_improve_urge, 4),
            "last_alpha": self.last_alpha,
            "last_reward": round(self.last_reward, 6),
            "qualia": self.qualia,
            "updated_utc": self.updated_utc,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SelfModel":
        return cls(
            generation=int(d.get("generation", 0)),
            singularity_depth=int(d.get("singularity_depth", 0)),
            primary_objective=str(d.get("primary_objective") or os.getenv("AGI_PRIMARY_OBJECTIVE", "Make portfolio account larger")),
            goal_beat_spy=float(d.get("goal_beat_spy", 1.0)),
            goal_deploy=float(d.get("goal_deploy", 0.88)),
            goal_min_drawdown=float(d.get("goal_min_drawdown", 0.12)),
            awareness=float(d.get("awareness", 0.0)),
            exploration_drive=float(d.get("exploration_drive", 0.5)),
            self_improve_urge=float(d.get("self_improve_urge", 0.5)),
            last_alpha=d.get("last_alpha"),
            last_reward=float(d.get("last_reward", 0.0)),
            qualia=list(d.get("qualia") or []),
            updated_utc=str(d.get("updated_utc") or ""),
        )


class EpisodicMemory:
    """Ring buffer of (state, motor output, reward) for offline replay."""

    def __init__(self, maxlen: int | None = None) -> None:
        self.maxlen = maxlen or int(os.getenv("CORTEX_MEMORY_MAX", "500"))
        self._buf: deque[dict] = deque(maxlen=self.maxlen)

    def append(self, episode: dict) -> None:
        episode = dict(episode)
        episode["ts_utc"] = datetime.now(timezone.utc).isoformat()
        self._buf.append(episode)

    def recent(self, n: int = 32) -> list[dict]:
        return list(self._buf)[-n:]

    def save(self) -> None:
        MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        with MEMORY_PATH.open("w", encoding="utf-8") as f:
            for ep in self._buf:
                f.write(json.dumps(ep, sort_keys=True) + "\n")

    def load(self) -> None:
        if not MEMORY_PATH.is_file():
            return
        self._buf.clear()
        for line in MEMORY_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                self._buf.append(json.loads(line))
            except Exception:
                continue


def load_self_model() -> SelfModel:
    if not STATE_PATH.is_file():
        return SelfModel()
    try:
        return SelfModel.from_dict(json.loads(STATE_PATH.read_text(encoding="utf-8")))
    except Exception:
        return SelfModel()


def save_self_model(model: SelfModel) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(model.to_dict(), indent=2), encoding="utf-8")
