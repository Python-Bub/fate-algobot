"""News radar: detect catalysts on bottom names + investigate fresh headlines."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

from bottom_fisher.config import BottomFisherConfig
from utils import log

_CATALYST_POS = re.compile(
    r"\b(upgrade|turnaround|restructur|buyback|insider\s+buy|beat\s+estimates|"
    r"guidance\s+raise|short\s+squeeze|oversold|recovery|rebound|acquisition|"
    r"merger|partnership|fda\s+approv|contract\s+win|debt\s+refinanc|"
    r"undervalued|under\s*valued|below\s+fair\s+value|margin\s+of\s+safety|"
    r"\d{1,2}\s*%\s*(undervalued|upside|discount)|trading\s+at\s+a\s+discount|"
    r"bargain|cheap\s+vs|intrinsic\s+value)\b",
    re.I,
)
_CATALYST_NEG = re.compile(
    r"\b(bankruptcy|chapter\s+11|fraud|sec\s+investigation|delist|offering|"
    r"dilution|going\s+concern|class\s+action|downgrade|misses\s+estimates|"
    r"guidance\s+cut|layoff|recall)\b",
    re.I,
)
_TICKER_IN_HEADLINE = re.compile(r"\$([A-Z]{1,5})\b")


@dataclass
class NewsCatalyst:
    ticker: str
    catalyst_score: float
    headline_count: int
    positive_hits: int
    negative_hits: int
    novelty: float
    top_headline: str
    news_trigger: bool
    investigate: bool
    rationale: str

    def to_dict(self) -> dict:
        return asdict(self)


def scan_news_for_ticker(ticker: str, cfg: BottomFisherConfig | None = None) -> NewsCatalyst:
    cfg = cfg or BottomFisherConfig.from_env()
    sym = ticker.strip().upper()
    headlines: list[str] = []
    try:
        from intel.headline_fetch_parallel import fetch_all_headline_texts

        headlines = fetch_all_headline_texts(
            sym,
            finnhub_limit=int(os.getenv("BOTTOM_FISHER_FINNHUB_LIMIT", "20")),
            news_limit=int(os.getenv("BOTTOM_FISHER_NEWSAPI_LIMIT", "12")),
            cramer_limit=int(os.getenv("BOTTOM_FISHER_CRAMER_LIMIT", "8")),
        )
    except Exception as e:
        log.debug("[BOTTOM_FISHER] headlines %s: %s", sym, e)

    pos = neg = 0
    best_line = ""
    for h in headlines[:40]:
        if not h:
            continue
        if _CATALYST_POS.search(h):
            pos += 1
            if not best_line:
                best_line = h[:240]
        if _CATALYST_NEG.search(h):
            neg += 1
            if not best_line:
                best_line = h[:240]

    n = len(headlines)
    novelty = min(1.0, n / 8.0)
    pos_s = min(1.0, pos / 3.0)
    neg_pen = min(0.7, neg * 0.25)
    score = max(0.0, min(1.0, 0.35 * novelty + 0.55 * pos_s - neg_pen))
    trigger = n >= int(os.getenv("BOTTOM_FISHER_NEWS_TRIGGER_COUNT", "3")) or pos >= 1
    investigate = trigger and (pos > 0 or score >= cfg.min_news_catalyst)

    rationale = "quiet"
    if neg > pos and neg >= 2:
        rationale = "negative_cluster"
    elif pos >= 2:
        rationale = "positive_catalyst"
    elif trigger:
        rationale = "headline_spike"

    return NewsCatalyst(
        ticker=sym,
        catalyst_score=float(score),
        headline_count=n,
        positive_hits=pos,
        negative_hits=neg,
        novelty=float(novelty),
        top_headline=best_line,
        news_trigger=bool(trigger),
        investigate=bool(investigate),
        rationale=rationale,
    )


def discover_news_mentions(extra_queries: list[str] | None = None) -> list[str]:
    """Optional: pull tickers mentioned in market-wide news (Tavily)."""
    q = os.getenv(
        "BOTTOM_FISHER_NEWS_DISCOVERY_QUERY",
        "oversold stocks turnaround upgrade rebound today",
    )
    if extra_queries:
        q = extra_queries[0]
    key = (os.getenv("TAVILY_API_KEY") or "").strip()
    if not key:
        return []
    try:
        import requests

        r = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": key,
                "query": q,
                "search_depth": "basic",
                "max_results": 12,
                "include_answer": True,
            },
            timeout=18,
        )
        r.raise_for_status()
        js = r.json()
        text = str(js.get("answer", ""))
        for it in js.get("results") or []:
            if isinstance(it, dict):
                text += " " + str(it.get("title", "")) + " " + str(it.get("content", ""))
        found = sorted({m.upper() for m in _TICKER_IN_HEADLINE.findall(text)})
        return found[: int(os.getenv("BOTTOM_FISHER_DISCOVERY_CAP", "15"))]
    except Exception as e:
        log.debug("[BOTTOM_FISHER] news discovery: %s", e)
        return []
