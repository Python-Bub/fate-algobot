"""Registry of 50 specialized industry handlers."""

from __future__ import annotations

from analytics.industries.base import BaseIndustryHandler
from analytics.industries.handlers import ALL_HANDLERS

_UNCLASSIFIED: BaseIndustryHandler | None = None


def list_industry_ids() -> list[str]:
    return sorted(ALL_HANDLERS.keys())


def get_handler(industry_id: str) -> BaseIndustryHandler:
    hid = (industry_id or "unclassified").strip().lower()
    if hid in ALL_HANDLERS:
        return ALL_HANDLERS[hid]
    return get_unclassified_handler()


def get_unclassified_handler() -> BaseIndustryHandler:
    global _UNCLASSIFIED
    if _UNCLASSIFIED is None:
        from analytics.industries.handlers.unclassified import HANDLER

        _UNCLASSIFIED = HANDLER
    return _UNCLASSIFIED


def all_handlers() -> list[BaseIndustryHandler]:
    return list(ALL_HANDLERS.values())


def handler_for_symbol_meta(industry_id: str) -> BaseIndustryHandler:
    return get_handler(industry_id)
