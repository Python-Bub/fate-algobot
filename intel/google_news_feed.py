"""Google News RSS intel — quota-friendly headlines without NewsAPI 429s.

Uses the public Google News RSS endpoint (same path as Cramer fetchers).
This is NOT Google login scraping / SERP bypass — RSS is the allowed free feed.
Optional: set GOOGLE_CSE_ID + GOOGLE_API_KEY for Custom Search JSON API.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import requests

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "intel" / "google_news_cache.json"

_CACHE_MEM: dict[str, tuple[float, list[str]]] = {}


def _b(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in ("1", "true", "yes", "on")


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _company_hint(symbol: str) -> str:
    try:
        import yfinance as yf

        info = yf.Ticker(symbol).info or {}
        return str(info.get("shortName") or info.get("longName") or "")[:80]
    except Exception:
        return ""


def fetch_google_news_rss_headlines(query: str, *, when: str = "2d", limit: int = 12) -> list[str]:
    """Return plain headline strings from Google News RSS for a query."""
    if not _b("USE_GOOGLE_NEWS_RSS", True):
        return []
    try:
        from intel.cramer_email_fetcher import fetch_google_news_rss

        items = fetch_google_news_rss(query, when=when)
    except Exception:
        # Inline minimal fallback
        items = []
        try:
            url = (
                f"https://news.google.com/rss/search?q={quote_plus(query.strip())}+when:{when}"
                f"&hl=en-US&gl=US&ceid=US:en"
            )
            r = requests.get(url, timeout=12, headers={"User-Agent": "FATE-AlgoBot/1.0"})
            if r.status_code == 200:
                from intel.cramer_email_fetcher import _parse_rss

                items = _parse_rss(r.text)
        except Exception:
            return []
    out: list[str] = []
    for it in items[:limit]:
        title = str(it.get("title") or "").strip()
        desc = str(it.get("description") or "").strip()
        blob = f"{title} {desc}".strip()
        if blob:
            out.append(blob)
    return out


def fetch_google_cse_headlines(query: str, *, limit: int = 8) -> list[str]:
    """Optional Google Custom Search JSON API (needs GOOGLE_API_KEY + GOOGLE_CSE_ID)."""
    key = (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()
    cse = (os.getenv("GOOGLE_CSE_ID") or "").strip()
    if not key or not cse or not _b("USE_GOOGLE_CSE", True):
        return []
    try:
        r = requests.get(
            "https://www.googleapis.com/customsearch/v1",
            params={"key": key, "cx": cse, "q": query, "num": min(10, limit)},
            timeout=12,
        )
        if r.status_code == 429:
            try:
                from data_platform.source_rotator import note_limited

                note_limited("google_cse", seconds=_f("GOOGLE_CSE_COOLDOWN_SEC", 120))
            except Exception:
                pass
            return []
        if r.status_code != 200:
            return []
        items = r.json().get("items") or []
        return [
            f"{it.get('title') or ''} {it.get('snippet') or ''}".strip()
            for it in items
            if (it.get("title") or it.get("snippet"))
        ][:limit]
    except Exception:
        return []


def symbol_news_headlines(symbol: str, *, limit: int = 16) -> list[str]:
    """Quota-friendly headlines for a symbol via Google News RSS (+ optional CSE)."""
    if not _b("USE_GOOGLE_NEWS_INTEL", True):
        return []
    sym = symbol.strip().upper()
    ttl = _f("GOOGLE_NEWS_CACHE_TTL_SEC", 900)
    now = time.time()
    hit = _CACHE_MEM.get(sym)
    if hit and now - hit[0] < ttl:
        return list(hit[1])[:limit]

    try:
        from intel.english_lexicon import expand_news_query

        hint = _company_hint(sym) if _b("GOOGLE_NEWS_COMPANY_HINT", True) else ""
        queries = expand_news_query(sym, hint)
    except Exception:
        queries = [sym, f"{sym} stock"]

    when = os.getenv("GOOGLE_NEWS_WHEN", "2d")
    headlines: list[str] = []
    seen: set[str] = set()
    for q in queries[:3]:
        for h in fetch_google_news_rss_headlines(q, when=when, limit=8):
            k = h[:120].lower()
            if k in seen:
                continue
            seen.add(k)
            headlines.append(h)
            if len(headlines) >= limit:
                break
        if len(headlines) >= limit:
            break
        # Optional CSE if configured
        for h in fetch_google_cse_headlines(q, limit=4):
            k = h[:120].lower()
            if k in seen:
                continue
            seen.add(k)
            headlines.append(h)

    _CACHE_MEM[sym] = (now, headlines)
    return headlines[:limit]


def google_news_sentiment_boost(symbol: str) -> tuple[float, dict[str, Any]]:
    """Lexicon polarity over Google News headlines — additive intel, not sole sizer."""
    heads = symbol_news_headlines(symbol)
    if not heads:
        return 0.0, {"n": 0}
    try:
        from analytics.vector_math import polarity_mean

        avg = polarity_mean(heads)
    except Exception:
        try:
            from intel.english_lexicon import lexicon_polarity

            scores = [lexicon_polarity(h) for h in heads]
            avg = float(sum(scores) / max(len(scores), 1))
        except Exception:
            avg = 0.0
    return avg, {"n": len(heads), "sample": heads[:3], "score": avg}
