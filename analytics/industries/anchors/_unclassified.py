"""Fallback anchor for unclassified symbols."""

from __future__ import annotations

from analytics.industries.anchors._base import IndustryAnchor


class UnclassifiedAnchor(IndustryAnchor):
    INDUSTRY_ID = "unclassified"
    ANCHOR_TICKER = "SPY"
    SMOKE_TICKERS = ("SPY",)


ANCHOR = UnclassifiedAnchor()
