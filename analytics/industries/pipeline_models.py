"""Datatypes for industry-specific pipeline actions (trade gates, ML weights, family bias)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class IndustryPipelineResult:
    """Output of one industry bucket's specialized pipeline logic."""

    score_delta: float = 0.0
    p_up_delta: float = 0.0
    block_long: bool = False
    block_short: bool = False
    warn_long: bool = False
    warn_short: bool = False
    block_reason: str = ""
    family_bias: float = 0.0
    max_hold_mult: float = 1.0
    position_cap_mult: float = 1.0
    feature_weights: dict[str, float] = field(default_factory=dict)
    pipeline_notes: list[str] = field(default_factory=list)
    playbook_tilt: float = 0.0
    macro_gates: list[str] = field(default_factory=list)

    def merge_weighted(self, other: IndustryPipelineResult, weight: float) -> None:
        w = float(weight)
        self.score_delta += other.score_delta * w
        self.p_up_delta += other.p_up_delta * w
        self.family_bias += other.family_bias * w
        self.playbook_tilt += other.playbook_tilt * w
        if other.block_long and w >= 0.45:
            self.block_long = True
            if not self.block_reason:
                self.block_reason = other.block_reason
        if other.block_short and w >= 0.45:
            self.block_short = True
        if other.warn_long:
            self.warn_long = True
        if other.warn_short:
            self.warn_short = True
        if other.max_hold_mult > 1.0:
            self.max_hold_mult = max(self.max_hold_mult, other.max_hold_mult)
        else:
            self.max_hold_mult = min(self.max_hold_mult, other.max_hold_mult)
        if other.position_cap_mult > 1.0:
            self.position_cap_mult = max(self.position_cap_mult, other.position_cap_mult)
        else:
            self.position_cap_mult = min(self.position_cap_mult, other.position_cap_mult)
        for k, v in other.feature_weights.items():
            self.feature_weights[k] = self.feature_weights.get(k, 0.0) + float(v) * w
        self.pipeline_notes.extend(other.pipeline_notes[:6])
        self.macro_gates.extend(other.macro_gates[:4])

    def to_dict(self) -> dict[str, Any]:
        return {
            "score_delta": self.score_delta,
            "p_up_delta": self.p_up_delta,
            "block_long": self.block_long,
            "block_short": self.block_short,
            "warn_long": self.warn_long,
            "warn_short": self.warn_short,
            "block_reason": self.block_reason,
            "family_bias": self.family_bias,
            "max_hold_mult": self.max_hold_mult,
            "position_cap_mult": self.position_cap_mult,
            "feature_weights": dict(self.feature_weights),
            "pipeline_notes": list(self.pipeline_notes),
            "playbook_tilt": self.playbook_tilt,
            "macro_gates": list(self.macro_gates),
        }
