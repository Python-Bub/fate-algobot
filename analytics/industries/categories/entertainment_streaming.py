"""
44. Entertainment & Streaming

Internal id: entertainment_streaming
ETF proxy: XLC | Mode: hybrid
Notes: Content ROI; subscriber net adds.

Unified category module — handler, specialized pipeline, enhancement layer, anchor.
Import this file directly: from analytics.industries.categories.entertainment_streaming import CATEGORY
"""

from __future__ import annotations

from typing import Any

from analytics.industries.base import IndustryContext
from analytics.industries.categories._registry import category_slug_for_industry
from analytics.industries.pipeline_models import IndustryPipelineResult


class EntertainmentStreamingCategory:
    CATEGORY_NUMBER = 44
    CATEGORY_SLUG = 'entertainment_streaming'
    DISPLAY_NAME = 'Entertainment & Streaming'
    INDUSTRY_ID = 'entertainment_streaming'
    ETF_PROXY = 'XLC'
    COMOVEMENT_MODE = 'hybrid'

    LEADER_TICKERS = (
        'NFLX', 'DIS', 'WBD', 'PARA', 'SPOT', 'LYV'
    )

    NEWS_BULL_PHRASES = (
    'subscriber add',
    'content hit',
    'pricing tier',
    'box office',
    )

    COMMODITY_KEYS = ('streaming', 'box office', 'subscriber')

    @property
    def handler(self):
        from analytics.industries.registry import get_handler
        return get_handler(self.INDUSTRY_ID)

    @property
    def specialized(self):
        from analytics.industries.specialized import get_specialized
        return get_specialized(self.INDUSTRY_ID)

    @property
    def enhancement(self):
        from analytics.industries.enhancements import get_enhancement
        return get_enhancement(self.INDUSTRY_ID)

    @property
    def anchor(self):
        from analytics.industries.anchors import get_anchor
        return get_anchor(self.INDUSTRY_ID)

    @property
    def spec(self):
        from analytics.industries.categories.specs import get_spec
        return get_spec(self.CATEGORY_SLUG)

    def evaluate_buy_decision(
        self,
        symbol: str,
        row: dict | None = None,
        *,
        macro: dict | None = None,
        headlines: list[str] | None = None,
    ):
        from analytics.industries.category_decision import evaluate_category_decision
        rf = dict(row or {})
        rf.setdefault("industry_id", self.INDUSTRY_ID)
        return evaluate_category_decision(symbol, rf, macro, headlines)

    def build_context(
        self,
        symbol: str,
        *,
        macro: dict | None = None,
        news_headlines: list[str] | None = None,
        row_features: dict | None = None,
    ) -> IndustryContext:
        from analytics.industries.engine import build_context
        return build_context(
            symbol,
            macro_bundle=macro,
            news_headlines=news_headlines,
            row_features=row_features or {},
        )

    def run_pipeline(
        self,
        symbol: str,
        row: dict | None = None,
        *,
        macro_bundle: dict | None = None,
        news_headlines: list[str] | None = None,
    ) -> dict[str, Any]:
        from analytics.industries.pipeline import run_industry_pipeline
        return run_industry_pipeline(symbol, row, macro_bundle=macro_bundle, news_headlines=news_headlines)

    def enhance_row(self, row: dict[str, Any]) -> dict[str, Any]:
        from analytics.industries.project_wiring import wire_paper_sim_row
        out = wire_paper_sim_row(row)
        out["category"] = {
            "number": self.CATEGORY_NUMBER,
            "slug": self.CATEGORY_SLUG,
            "name": self.DISPLAY_NAME,
            "industry_id": self.INDUSTRY_ID,
        }
        return self.anchor.enhance_row(out)

    def enhance_score(self, symbol: str, score: float, p_up: float, row: dict | None = None):
        s, p = float(score), float(p_up)
        ctx = self.build_context(symbol, row_features=row or {})
        base = IndustryPipelineResult()
        part = self.specialized.run(ctx, self.handler)
        part = self.enhancement.enhance(part, ctx, self.handler)
        s += float(part.score_delta) * 0.11
        p = min(1.0, p + float(part.p_up_delta))
        return self.anchor.enhance_score(symbol, s, p, row=row)

    def feature_weights(self, symbol: str) -> dict[str, float]:
        ctx = self.build_context(symbol)
        res = IndustryPipelineResult()
        self.enhancement.enhance(res, ctx, self.handler)
        return dict(res.feature_weights)

    def high_level_test(self) -> dict[str, Any]:
        rep = self.enhancement.high_level_test(self.handler)
        rep["category_slug"] = self.CATEGORY_SLUG
        rep["category_number"] = self.CATEGORY_NUMBER
        rep["display_name"] = self.DISPLAY_NAME
        return rep

    def historical_smoke(self) -> dict[str, Any]:
        rep = self.anchor.historical_smoke()
        rep["category_slug"] = self.CATEGORY_SLUG
        rep["category_number"] = self.CATEGORY_NUMBER
        rep["display_name"] = self.DISPLAY_NAME
        return rep


CATEGORY = EntertainmentStreamingCategory()
INDUSTRY_ID = CATEGORY.INDUSTRY_ID
CATEGORY_SLUG = CATEGORY.CATEGORY_SLUG


def get_category():
    return CATEGORY


def slug_for_symbol(symbol: str) -> str:
    from analytics.industries.integration import get_industry_profile
    prof = get_industry_profile(symbol.strip().upper())
    return category_slug_for_industry(prof.get("primary_industry_id") or "unclassified")
