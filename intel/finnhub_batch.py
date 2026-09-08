"""Finnhub batch intel — general news + sentiment cache (fewer API calls)."""

from __future__ import annotations

import os
from datetime import date, timedelta

import requests

from utils import log

_FINNHUB = "https://finnhub.io/api/v1"


def _key() -> str:
    return (os.getenv("FINNHUB_API_KEY") or "").strip()


def fetch_general_news(*, category: str = "general") -> list[dict]:
    key = _key()
    if not key:
        return []
    from intel.api_coverage import allow_provider

    ok, reason = allow_provider("finnhub", context="general_news")
    if not ok:
        log.debug("[FINNHUB-BATCH] general news skipped: %s", reason)
        return []
    try:
        r = requests.get(
            f"{_FINNHUB}/news",
            params={"category": category, "token": key},
            timeout=float(os.getenv("SENT_HTTP_TIMEOUT", "8")),
        )
        if r.status_code != 200:
            return []
        from intel.api_budget import record

        record("finnhub")
        body = r.json()
        return list(body) if isinstance(body, list) else []
    except Exception as e:
        log.debug("[FINNHUB-BATCH] general news failed: %s", e)
        return []


def fetch_sentiment(symbol: str, *, use_cache: bool = True) -> dict:
    sym = symbol.strip().upper()
    cache_key = f"finnhub_sentiment:{sym}"
    if use_cache:
        from intel.api_budget import cache_get, cache_set

        cached = cache_get("finnhub_sentiment", sym)
        if isinstance(cached, dict) and cached:
            return cached
    key = _key()
    if not key:
        return {}
    from intel.api_coverage import allow_provider

    ok, reason = allow_provider("finnhub")
    if not ok:
        return {}
    try:
        r = requests.get(
            f"{_FINNHUB}/news-sentiment",
            params={"symbol": sym, "token": key},
            timeout=float(os.getenv("SENT_HTTP_TIMEOUT", "8")),
        )
        if r.status_code != 200:
            return {}
        from intel.api_budget import record

        record("finnhub")
        data = r.json() or {}
        if use_cache and data:
            ttl = float(os.getenv("INTEL_CACHE_FINNHUB_SENTIMENT_TTL_SEC", "7200"))
            from intel.api_budget import cache_set

            cache_set("finnhub_sentiment", sym, data, ttl_sec=ttl)
        return data
    except Exception as e:
        log.debug("[FINNHUB-BATCH] sentiment %s: %s", sym, e)
        return {}


def sentiment_headline_skip(symbol: str) -> bool:
    """Skip company-news fetch when cached Finnhub sentiment is fresh enough."""
    if os.getenv("FINNHUB_SENTIMENT_FIRST", "true").lower() not in ("1", "true", "yes"):
        return False
    data = fetch_sentiment(symbol)
    if not data:
        return False
    buzz = data.get("companyNewsScore")
    sent = data.get("sentiment") or {}
    return buzz is not None or bool(sent.get("bullishPercent"))


def fetch_company_news_lite(symbol: str, *, limit: int = 20) -> list[str]:
    """Company news only when sentiment cache miss — still one call."""
    sym = symbol.strip().upper()
    if sentiment_headline_skip(sym):
        return []
    key = _key()
    if not key:
        return []
    from intel.api_coverage import allow_provider

    ok, reason = allow_provider("finnhub")
    if not ok:
        return []
    try:
        end = date.today()
        start = end - timedelta(days=7)
        r = requests.get(
            f"{_FINNHUB}/company-news",
            params={"symbol": sym, "from": start.isoformat(), "to": end.isoformat(), "token": key},
            timeout=float(os.getenv("SENT_HTTP_TIMEOUT", "8")),
        )
        if r.status_code != 200:
            return []
        from intel.api_budget import record

        record("finnhub")
        body = r.json()
        items = body[:limit] if isinstance(body, list) else []
        return [(it.get("headline") or "") + " " + (it.get("summary") or "") for it in items]
    except Exception as e:
        log.debug("[FINNHUB-BATCH] company-news %s: %s", sym, e)
        return []
