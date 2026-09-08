"""Types for user-facing 50-category specifications."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CategorySpec:
    number: int
    slug: str
    display_name: str
    industry_id: str
    sector_group: str
    definition: str
    algo_key_metric: str
    prediction_feature: str
    correlation: str
    whole_group_movement: str
    metric_type: str
    correlation_type: str
    group_keywords: tuple[str, ...] = ()
    bull_keywords: tuple[str, ...] = ()
    bear_keywords: tuple[str, ...] = ()


@dataclass
class CategoryDecisionResult:
    score_delta: float = 0.0
    p_up_delta: float = 0.0
    family_bias: float = 0.0
    block_buy: bool = False
    warn_buy: bool = False
    block_reason: str = ""
    metric_proxy: float = 0.0
    macro_alignment: float = 0.0
    group_signal: float = 0.0
    buy_quality: float = 0.0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "score_delta": self.score_delta,
            "p_up_delta": self.p_up_delta,
            "family_bias": self.family_bias,
            "block_buy": self.block_buy,
            "warn_buy": self.warn_buy,
            "block_reason": self.block_reason,
            "metric_proxy": self.metric_proxy,
            "macro_alignment": self.macro_alignment,
            "group_signal": self.group_signal,
            "buy_quality": self.buy_quality,
            "notes": self.notes[:8],
        }
