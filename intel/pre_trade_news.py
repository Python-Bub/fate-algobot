"""Fresh headline/intel pull immediately before a trade decision (not cached bulk training)."""

from __future__ import annotations

import os

from utils import log


def refresh_pre_trade_intel(symbol: str) -> dict:
    """
    Bypass process-level sentiment cache and re-fetch live headlines + intel factors.
    Call this right before placing/confirming a hold (especially multi-day / longterm).
    """
    sym = symbol.strip().upper()
    from sentiment_pipeline import clear_sentiment_cache, composite_sentiment, get_symbol_news_intel

    clear_sentiment_cache(sym)
    sent = float(composite_sentiment(sym))
    news_intel = get_symbol_news_intel(sym)

    news_factor = 0.0
    transcript_factor = 0.0
    if os.getenv("USE_INTEL_FACTORS", "true").lower() in ("1", "true", "yes"):
        try:
            from intel.news_factor_engine import score_symbol_news_factors
            from intel.transcript_factor_engine import score_symbol_transcripts

            nf = score_symbol_news_factors(sym)
            tf = score_symbol_transcripts(sym)
            news_factor = float(nf.get("final_factor", 0.0))
            transcript_factor = float(tf.get("final_factor", 0.0))
            if os.getenv("HEAVY_NEWS_INTEL", "false").lower() in ("1", "true", "yes"):
                sent = 0.45 * sent + 0.35 * news_factor + 0.20 * transcript_factor
            else:
                sent = 0.70 * sent + 0.20 * news_factor + 0.10 * transcript_factor
        except Exception as e:
            log.debug("[PRE_TRADE_NEWS] intel blend skipped %s: %s", sym, e)

    try:
        from intel.open_web_intel import open_web_intel_for

        web = open_web_intel_for(sym, force_refresh=True)
        if web.get("block_long"):
            news_intel["block_long"] = True
        sent = max(-1.0, min(1.0, 0.75 * sent + 0.25 * float(web.get("sentiment") or 0.0)))
        news_intel.setdefault("open_web", web)
    except Exception as e:
        log.debug("[PRE_TRADE_NEWS] open web skipped %s: %s", sym, e)

    digest_verdict = str(news_intel.get("verdict") or news_intel.get("narrative") or "")
    digest_bear = int(news_intel.get("bearish_headlines") or 0)
    digest_bull = int(news_intel.get("bullish_headlines") or 0)
    if news_intel:
        sent = max(-1.0, min(1.0, 0.60 * sent + 0.40 * float(news_intel.get("sentiment", sent))))

    log.info(
        "[PRE_TRADE_NEWS] %s fresh pull sent=%.3f news=%.3f narrative=%s good=%.2f bad=%.2f dte=%s",
        sym,
        sent,
        news_factor,
        digest_verdict or "n/a",
        float(news_intel.get("good_news_score", 0.0)),
        float(news_intel.get("bad_news_score", 0.0)),
        news_intel.get("days_to_earnings"),
    )
    return {
        "sentiment": sent,
        "news_factor": news_factor,
        "transcript_factor": transcript_factor,
        "verdict": digest_verdict,
        "bearish_headlines": digest_bear,
        "bullish_headlines": digest_bull,
        "news_ai": news_intel,
        "block_long": bool(news_intel.get("block_long")),
        "days_to_earnings": news_intel.get("days_to_earnings"),
        "next_earnings_date": news_intel.get("next_earnings_date"),
    }
