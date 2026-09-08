"""Hook bottom-fisher into paper_sim / fortress scoring."""

from __future__ import annotations

import os

from bottom_fisher.config import bottom_fisher_enabled, bottom_fisher_paper_boost_enabled
from bottom_fisher.store import lookup_ticker
from utils import log


def bottom_fisher_score_boost(ticker: str) -> tuple[float, dict]:
    """Return (score_addition, metadata) for composite ranking."""
    if not bottom_fisher_enabled() or not bottom_fisher_paper_boost_enabled():
        return 0.0, {}
    row = lookup_ticker(ticker)
    if not row:
        return 0.0, {}
    if not row.get("trade_eligible", False):
        return 0.0, {"bottom_fisher": True, "trade_eligible": False}
    w = float(os.getenv("RANK_W_BOTTOM_FISHER", "0.34"))
    composite = float(row.get("composite_score", 0))
    boost = w * composite
    meta = {
        "bottom_fisher": True,
        "trade_eligible": True,
        "bottom_composite": composite,
        "recovery_score": row.get("recovery_score"),
        "catalyst_score": row.get("catalyst_score"),
        "ai_grade": row.get("ai_grade"),
        "ai_verdict": row.get("ai_verdict"),
        "recovery_thesis": row.get("recovery_thesis", ""),
    }
    return float(boost), meta


def enrich_row_with_bottom_fisher(row: dict) -> dict:
    """Mutate paper_sim row with bottom-fisher fields + score boost."""
    t = str(row.get("ticker", "")).upper()
    boost, meta = bottom_fisher_score_boost(t)
    if boost <= 0:
        return row
    row["score"] = float(row.get("score", 0)) + boost
    row["bottom_fisher_boost"] = boost
    for k, v in meta.items():
        row[k] = v
    if row.get("ai_verdict") == "buy" and float(row.get("ai_confidence", 0)) >= float(
        os.getenv("BOTTOM_FISHER_AI_BUY_CONF", "0.55")
    ):
        row["bottom_fisher_strong"] = True
    return row


def maybe_force_investigate(ticker: str) -> None:
    """On-demand news+AI check when symbol surfaces in live flow."""
    if not bottom_fisher_enabled():
        return
    if os.getenv("BOTTOM_FISHER_LIVE_INVESTIGATE", "true").lower() not in ("1", "true", "yes"):
        return
    try:
        from bottom_fisher.config import BottomFisherConfig
        from bottom_fisher.news_radar import scan_news_for_ticker
        from bottom_fisher.ai_agent import review_bottom_candidate

        news = scan_news_for_ticker(ticker)
        if not news.investigate:
            return
        review = review_bottom_candidate(
            {
                "ticker": ticker,
                "catalyst_score": news.catalyst_score,
                "top_headline": news.top_headline,
                "news_rationale": news.rationale,
            }
        )
        log.info(
            "[BOTTOM_FISHER] live investigate %s news=%.2f ai=%s conf=%.2f",
            ticker,
            news.catalyst_score,
            review.grade,
            review.confidence,
        )
    except Exception as e:
        log.debug("[BOTTOM_FISHER] investigate %s: %s", ticker, e)
