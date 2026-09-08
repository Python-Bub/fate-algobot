"""Industry-specific news routing and headline scoring across all 50 buckets."""

from __future__ import annotations

import re
from typing import Any

from analytics.industries.classifier import classify_ticker
from analytics.industries.registry import get_handler

_FOOD_COMMODITY_RE = re.compile(
    r"\b(beef|wheat|corn|coffee|cocoa|sugar|dairy|pork|chicken|grain|rice|soy|barley)\b",
    re.I,
)
_RATE_RE = re.compile(r"\b(fed|fomc|rate hike|rate cut|treasury yield|10-year|basis points)\b", re.I)
_OIL_RE = re.compile(r"\b(opec|crude|wti|brent|oil price|barrel|natural gas)\b", re.I)
_FDA_RE = re.compile(r"\b(fda|phase [123]|clinical trial|biotech|approval|complete response)\b", re.I)
_TECH_RE = re.compile(r"\b(nvidia|ai chip|semiconductor|cloud capex|nasdaq|rally)\b", re.I)


def route_headlines(symbol: str, headlines: list[str]) -> dict[str, Any]:
    """Score headlines using the symbol's industry-specific handler."""
    row = classify_ticker(symbol, use_cache=True, use_yfinance=False)
    handler = get_handler(str(row.get("industry_id")))
    ns = handler.score_news(headlines)
    macro_tags = _macro_tags(headlines)
    return {
        "symbol": symbol.upper(),
        "industry_id": handler.INDUSTRY_ID,
        "industry_name": handler.INDUSTRY_NAME,
        "bullish_score": ns.bullish_score,
        "bearish_score": ns.bearish_score,
        "net": ns.net,
        "matched_bull": ns.matched_bull,
        "matched_bear": ns.matched_bear,
        "event_tags": ns.event_tags + macro_tags,
        "comovement_mode": handler.COMOVEMENT_MODE.value,
    }


def _macro_tags(headlines: list[str]) -> list[str]:
    text = " ".join(headlines)
    tags: list[str] = []
    if _FOOD_COMMODITY_RE.search(text):
        tags.append("macro:food_commodity")
    if _RATE_RE.search(text):
        tags.append("macro:rates")
    if _OIL_RE.search(text):
        tags.append("macro:energy")
    if _FDA_RE.search(text):
        tags.append("macro:healthcare_event")
    if _TECH_RE.search(text):
        tags.append("macro:tech_nasdaq")
    return tags


def batch_route(symbols: list[str], headlines_by_symbol: dict[str, list[str]]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for sym in symbols:
        out[sym.upper()] = route_headlines(sym, headlines_by_symbol.get(sym.upper(), []))
    return out


def industry_news_factor(symbol: str, headlines: list[str]) -> float:
    r = route_headlines(symbol, headlines)
    return float(r.get("net") or 0.0)
