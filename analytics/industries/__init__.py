"""50-industry specialized handler framework — classification, factors, news, co-movement."""

from analytics.industries.classifier import classify_ticker, classify_universe
from analytics.industries.registry import get_handler, list_industry_ids

__all__ = [
    "classify_ticker",
    "classify_universe",
    "get_handler",
    "list_industry_ids",
]
