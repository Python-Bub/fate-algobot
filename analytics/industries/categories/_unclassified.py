"""Fallback category for unclassified symbols."""

from __future__ import annotations

from analytics.industries.categories._registry import USER_CATEGORIES


class UnclassifiedCategory:
    CATEGORY_NUMBER = 0
    CATEGORY_SLUG = "unclassified"
    DISPLAY_NAME = "Unclassified"
    INDUSTRY_ID = "unclassified"
    ETF_PROXY = "SPY"
    LEADER_TICKERS = ("SPY",)

    @property
    def handler(self):
        from analytics.industries.registry import get_unclassified_handler
        return get_unclassified_handler()

    def run_pipeline(self, symbol, row=None, *, macro_bundle=None, news_headlines=None):
        return {"enabled": False, "score_delta": 0.0}

    def enhance_row(self, row):
        return dict(row)

    def enhance_score(self, symbol, score, p_up, row=None):
        return float(score), float(p_up)

    def high_level_test(self):
        return {"category_slug": "unclassified", "net_positive": True, "score_delta": 0.0}

    def historical_smoke(self):
        return {"category_slug": "unclassified", "ok": True, "checks": []}


CATEGORY = UnclassifiedCategory()
