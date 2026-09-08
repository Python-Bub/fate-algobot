"""Yahoo Finance headlines + lexicon sentiment. No paid news quota."""

from __future__ import annotations

import yfinance as yf

from intel.news_sentiment_lexicon import classify_headline


def _item_text(item: object) -> tuple[str, str]:
    """Normalize yfinance news dicts (legacy title + nested content.title)."""
    if not isinstance(item, dict):
        t = str(item or "").strip()
        return t, ""
    c = item.get("content") if isinstance(item.get("content"), dict) else item
    title = str(
        c.get("title")
        or c.get("headline")
        or item.get("title")
        or item.get("headline")
        or ""
    ).strip()
    summary = str(
        c.get("summary")
        or c.get("description")
        or item.get("summary")
        or item.get("publisher")
        or ""
    ).strip()
    return title, summary


def fetch_news(ticker: str, limit: int = 15) -> list[dict]:
    """Yahoo headlines for the live ticker plus former names / spinoff relatives."""
    tickers = [ticker.strip().upper()]
    try:
        from universe_lifecycle.corporate_actions import related_symbols

        for s in related_symbols(ticker)[:4]:
            if s and s not in tickers:
                tickers.append(s)
    except Exception:
        pass
    out: list[dict] = []
    seen: set[str] = set()
    per = max(3, int(limit) // max(1, len(tickers)))
    for sym in tickers:
        try:
            raw = yf.Ticker(sym).news or []
        except Exception:
            raw = []
        for item in raw[:per]:
            title, summary = _item_text(item)
            if not title:
                continue
            key = title.casefold()
            if key in seen:
                continue
            seen.add(key)
            out.append({"headline": title, "title": title, "summary": summary, "source_symbol": sym})
            if len(out) >= max(1, int(limit)):
                return out
    return out


def analyze_sentiment(text: str) -> float:
    """Scalar sentiment in [-1, 1] from financial headline lexicon."""
    return classify_headline(text).score
