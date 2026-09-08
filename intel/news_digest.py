"""Aggregate Finnhub + NewsAPI headlines into a readable good/bad/neutral digest."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from intel.headline_fetch_parallel import fetch_headline_groups_parallel
from intel.news_sentiment_lexicon import classify_headline
from intel.symbol_news_context import headline_relevant
from intel.symbol_news_context import newsapi_search_query as build_newsapi_query
from utils import log


def newsapi_search_query(symbol: str) -> str:
    """Re-export for sentiment_pipeline (symbol-agnostic implementation)."""
    return build_newsapi_query(symbol)


@dataclass
class NewsDigest:
    symbol: str
    composite_score: float
    verdict: str  # bullish | bearish | mixed | neutral | no_data
    bullish_count: int
    bearish_count: int
    neutral_count: int
    finnhub_count: int
    newsapi_count: int
    cramer_count: int
    finnhub_buzz_score: float | None
    finnhub_bull_pct: float | None
    finnhub_bear_pct: float | None
    top_bullish: list[str]
    top_bearish: list[str]
    llm_thesis: str
    block_long: bool
    generated_at_utc: str

    def to_dict(self) -> dict:
        return asdict(self)


def _fetch_finnhub_sentiment(symbol: str) -> dict:
    try:
        from intel.finnhub_batch import fetch_sentiment

        return fetch_sentiment(symbol)
    except Exception:
        return {}


def build_news_digest(symbol: str, *, use_llm: bool | None = None) -> NewsDigest:
    sym = symbol.strip().upper()
    fh, na, cr = fetch_headline_groups_parallel(sym, finnhub_limit=25, news_limit=25, cramer_limit=10)

    labeled: list[tuple[str, str, str, float]] = []
    for src, texts in (("finnhub", fh), ("newsapi", na), ("cramer", cr)):
        for txt in texts:
            if not (txt or "").strip():
                continue
            if not headline_relevant(sym, txt):
                continue
            c = classify_headline(txt)
            labeled.append((src, c.label, txt.strip()[:280], c.score))

    bull = [t for _, lab, t, _ in labeled if lab == "bullish"]
    bear = [t for _, lab, t, _ in labeled if lab == "bearish"]
    neu = [t for _, lab, t, _ in labeled if lab == "neutral"]

    scores = [s for *_, s in labeled]
    mean_lex = sum(scores) / len(scores) if scores else 0.0

    fh_sent = _fetch_finnhub_sentiment(sym)
    sent_block = fh_sent.get("sentiment") or {}
    buzz = fh_sent.get("companyNewsScore")
    bull_pct = sent_block.get("bullishPercent")
    bear_pct = sent_block.get("bearishPercent")
    bullish_score = float(sent_block.get("bullishScore") or 0.0)
    bearish_score = float(sent_block.get("bearishScore") or 0.0)
    fh_score = bullish_score - bearish_score if sent_block else None

    composite = 0.55 * mean_lex
    if fh_score is not None:
        composite = 0.40 * mean_lex + 0.60 * max(-1.0, min(1.0, fh_score))

    llm_thesis = ""
    llm_only_verdict: str | None = None
    if use_llm is None:
        use_llm = os.getenv("USE_LLM_SIGNAL", "false").lower() in ("1", "true", "yes")
    if use_llm and labeled:
        try:
            from intel.llm_signal_agent import score_documents_with_llm

            docs = [t for _, _, t, _ in labeled[:35]]
            llm = score_documents_with_llm(sym, docs)
            llm_sent = float(llm.get("sentiment", 0.0))
            composite = 0.50 * composite + 0.50 * llm_sent
            llm_thesis = str(llm.get("key_thesis", ""))[:300]
        except Exception as e:
            log.debug("[NEWS_DIGEST] llm skipped %s: %s", sym, e)
    elif use_llm and not labeled and os.getenv("NEWS_LLM_NO_HEADLINE_FALLBACK", "true").lower() in (
        "1",
        "true",
        "yes",
    ):
        try:
            from intel.llm_signal_agent import score_text_with_llm

            llm = score_text_with_llm(
                f"Current US equity outlook for {sym} over the next 5 trading days. "
                "Consider sector trends, recent price action, and macro headwinds.",
                symbol=sym,
            )
            llm_sent = float(llm.get("sentiment", 0.0))
            composite = float(llm_sent)
            llm_thesis = str(llm.get("key_thesis", ""))[:300]
            if llm_sent >= 0.15:
                llm_only_verdict = "bullish"
            elif llm_sent <= -0.15:
                llm_only_verdict = "bearish"
            else:
                llm_only_verdict = "neutral"
            log.info(
                "[NEWS_DIGEST] %s llm-only fallback verdict=%s sent=%.3f",
                sym,
                llm_only_verdict,
                llm_sent,
            )
        except Exception as e:
            log.debug("[NEWS_DIGEST] llm-only fallback skipped %s: %s", sym, e)

    bear_scores = [s for _, lab, _, s in labeled if lab == "bearish"]
    strong_bear = any(s <= -0.45 for s in bear_scores)

    n = len(labeled)
    if llm_only_verdict:
        verdict = llm_only_verdict
    elif n == 0:
        verdict = "no_data"
    elif strong_bear or (len(bear) >= 2 and len(bear) > len(bull)):
        verdict = "bearish"
    elif len(bull) >= 2 and len(bull) > len(bear) * 1.5 and not strong_bear:
        verdict = "bullish"
    elif len(bear) > 0 and len(bull) > 0:
        verdict = "mixed"
    elif composite <= -0.20:
        verdict = "bearish"
    elif composite >= 0.25:
        verdict = "bullish"
    else:
        verdict = "neutral"

    thr = float(os.getenv("SENTIMENT_BLOCK_THRESHOLD", "-0.35"))
    block = composite < thr and verdict in ("bearish", "mixed")

    return NewsDigest(
        symbol=sym,
        composite_score=float(composite),
        verdict=verdict,
        bullish_count=len(bull),
        bearish_count=len(bear),
        neutral_count=len(neu),
        finnhub_count=len(fh),
        newsapi_count=len(na),
        cramer_count=len(cr),
        finnhub_buzz_score=float(buzz) if buzz is not None else None,
        finnhub_bull_pct=float(bull_pct) if bull_pct is not None else None,
        finnhub_bear_pct=float(bear_pct) if bear_pct is not None else None,
        top_bullish=bull[:4],
        top_bearish=bear[:4],
        llm_thesis=llm_thesis,
        block_long=block,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
    )


def log_news_digest(symbol: str, digest: NewsDigest | None = None) -> NewsDigest:
    d = digest or build_news_digest(symbol)
    log.info(
        "[NEWS_DIGEST] %s verdict=%s score=%.3f bull=%d bear=%d neu=%d "
        "sources fh=%d na=%d cr=%d fh_bull%%=%s fh_bear%%=%s block_long=%s",
        d.symbol,
        d.verdict,
        d.composite_score,
        d.bullish_count,
        d.bearish_count,
        d.neutral_count,
        d.finnhub_count,
        d.newsapi_count,
        d.cramer_count,
        f"{d.finnhub_bull_pct:.0%}" if d.finnhub_bull_pct is not None else "n/a",
        f"{d.finnhub_bear_pct:.0%}" if d.finnhub_bear_pct is not None else "n/a",
        d.block_long,
    )
    for h in d.top_bearish[:2]:
        log.info("[NEWS_DIGEST] %s BEAR: %s", d.symbol, h[:220])
    for h in d.top_bullish[:2]:
        log.info("[NEWS_DIGEST] %s BULL: %s", d.symbol, h[:220])
    if d.llm_thesis:
        log.info("[NEWS_DIGEST] %s thesis: %s", d.symbol, d.llm_thesis[:240])
    return d
