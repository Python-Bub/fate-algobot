"""
Investing book formulas and catalog for FATE_AlgoBot.

Taxonomy: investing.catalog (+ sectors_extended)
Formulas: investing.formulas.*
Live rank: investing.integrate.book_rank_boost
"""

from __future__ import annotations

from typing import Any

from investing.catalog import (
    ALL_TOPICS,
    ANALYSIS_TOPICS,
    ASSET_CLASS_TOPICS,
    SECTOR_TOPICS,
    STRATEGY_TOPICS,
    Status,
    Topic,
    all_topics,
    by_family,
    by_status,
    topic_count,
)

__all__ = [
    "ALL_TOPICS",
    "ANALYSIS_TOPICS",
    "ASSET_CLASS_TOPICS",
    "SECTOR_TOPICS",
    "STRATEGY_TOPICS",
    "Status",
    "Topic",
    "all_topics",
    "by_family",
    "by_status",
    "topic_count",
    "book_rank_boost",
]


def book_rank_boost(symbol: str) -> tuple[float, dict[str, Any]]:
    """Multi-family investing-book rank bias (see investing.integrate)."""
    from investing.integrate import book_rank_boost as _boost

    return _boost(symbol)
