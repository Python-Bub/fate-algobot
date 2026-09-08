"""Fallback specialized logic for unclassified symbols."""

from __future__ import annotations

from analytics.industries.specialized.base import SpecializedLogic


class UnclassifiedSpecialized(SpecializedLogic):
    INDUSTRY_ID = "unclassified"
    INDUSTRY_NAME = "Unclassified"


LOGIC = UnclassifiedSpecialized()
