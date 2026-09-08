"""Fallback enhancement for unclassified symbols."""

from __future__ import annotations

from analytics.industries.enhancements._base import IndustryEnhancement, ENHANCEMENT_FEATURES


class UnclassifiedEnhancement(IndustryEnhancement):
    INDUSTRY_ID = "unclassified"
    INDUSTRY_NAME = "Unclassified"
    IMPLEMENTED_FEATURES = ENHANCEMENT_FEATURES


ENHANCEMENT = UnclassifiedEnhancement()
