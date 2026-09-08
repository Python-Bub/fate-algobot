"""Base class for per-industry specialized pipeline logic."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from analytics.industries.macro_playbooks import playbook_tilt
from analytics.industries.pipeline_models import IndustryPipelineResult

if TYPE_CHECKING:
    from analytics.industries.base import BaseIndustryHandler, IndustryContext


class SpecializedLogic:
    """Each of the 50 buckets subclasses this with trade/ML/family/risk hooks."""

    INDUSTRY_ID: str = "unclassified"
    INDUSTRY_NAME: str = "Unclassified"

    def run(self, ctx: IndustryContext, handler: BaseIndustryHandler) -> IndustryPipelineResult:
        res = IndustryPipelineResult()
        self.apply_macro_gates(ctx, handler, res)
        self.apply_news_gates(ctx, handler, res)
        res.score_delta += self.pipeline_score(ctx, handler)
        res.p_up_delta += self.p_up_adjust(ctx, handler)
        res.feature_weights.update(self.feature_weights(ctx, handler))
        res.family_bias = self.family_bias(ctx, handler)
        self.risk_adjust(ctx, handler, res)
        res.playbook_tilt = playbook_tilt(self.INDUSTRY_ID, ctx.news_headlines)
        pb_w = float(__import__("os").getenv("INDUSTRY_PLAYBOOK_WEIGHT", "0.08"))
        res.score_delta += res.playbook_tilt * pb_w
        if res.playbook_tilt != 0.0:
            res.pipeline_notes.append(f"playbook:{res.playbook_tilt:+.3f}")
        return res

    def apply_macro_gates(
        self,
        ctx: IndustryContext,
        handler: BaseIndustryHandler,
        res: IndustryPipelineResult,
    ) -> None:
        return None

    def apply_news_gates(
        self,
        ctx: IndustryContext,
        handler: BaseIndustryHandler,
        res: IndustryPipelineResult,
    ) -> None:
        if not ctx.news_headlines:
            return None
        ns = handler.score_news(ctx.news_headlines)
        if ns.bearish_score >= 0.42 and ns.bullish_score < 0.12:
            res.warn_long = True
            res.pipeline_notes.append("generic_bear_news")
        elif ns.bullish_score >= 0.36 and ns.bearish_score < 0.12:
            res.score_delta += 0.05
            res.p_up_delta += 0.02
            res.pipeline_notes.append("generic_bull_news")
        return None

    def pipeline_score(self, ctx: IndustryContext, handler: BaseIndustryHandler) -> float:
        tilts = handler.compute_factor_tilts(ctx)
        return float(np.tanh(tilts.combined * 0.35) * 0.06)

    def p_up_adjust(self, ctx: IndustryContext, handler: BaseIndustryHandler) -> float:
        return 0.0

    def feature_weights(self, ctx: IndustryContext, handler: BaseIndustryHandler) -> dict[str, float]:
        tilts = handler.compute_factor_tilts(ctx)
        return {
            "fpw_factor_rate": 1.0 + abs(tilts.rate_tilt) * 0.15,
            "fpw_factor_expansion": 1.0 + abs(tilts.expansion_tilt) * 0.12,
            "fpw_industry_sympathy": 1.0 + handler.INTRA_CORR_PRIOR * 0.08,
        }

    def family_bias(self, ctx: IndustryContext, handler: BaseIndustryHandler) -> float:
        return 0.0

    def risk_adjust(
        self,
        ctx: IndustryContext,
        handler: BaseIndustryHandler,
        res: IndustryPipelineResult,
    ) -> None:
        if res.block_long or res.warn_long:
            res.max_hold_mult = min(res.max_hold_mult, 0.75)
            res.position_cap_mult = min(res.position_cap_mult, 0.85)
        return None

    def _macro(self, ctx: IndustryContext, handler: BaseIndustryHandler, key: str, default: float = 0.0) -> float:
        return handler._macro(ctx, key, default)
