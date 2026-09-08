"""AI news agent — separates good vs bad narratives, blends earnings context into every score."""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any

from utils import log

_INTEL_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def _enabled() -> bool:
    return os.getenv("USE_NEWS_AI_AGENT", "true").lower() in ("1", "true", "yes")


def _cache_ttl() -> float:
    return float(os.getenv("NEWS_AI_CACHE_TTL_SEC", os.getenv("SENTIMENT_CACHE_TTL_SEC", "900")))


def _neutral(symbol: str) -> dict[str, Any]:
    return {
        "symbol": symbol.strip().upper(),
        "sentiment": 0.0,
        "good_news_score": 0.0,
        "bad_news_score": 0.0,
        "net_polarity": "neutral",
        "narrative": "neutral",
        "confidence": 0.0,
        "block_long": False,
        "boost_long": False,
        "verdict": "neutral",
        "key_good": [],
        "key_bad": [],
        "llm_thesis": "",
        "earnings_context": "",
        "days_to_earnings": None,
        "source": "neutral",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def _blend_sentiment(
    lex_score: float,
    good: float,
    bad: float,
    llm_sent: float,
    *,
    verdict: str,
) -> float:
    """Higher weight on explicit good/bad separation vs single scalar."""
    polarity = float(good) - float(bad)
    base = 0.35 * float(lex_score) + 0.40 * polarity + 0.25 * float(llm_sent)
    if verdict == "bullish" and good >= 0.55:
        base = max(base, 0.20 + 0.55 * good)
    elif verdict == "bearish" and bad >= 0.55:
        base = min(base, -0.20 - 0.55 * bad)
    return max(-1.0, min(1.0, base))


def _llm_analyze(
    symbol: str,
    headlines: list[str],
    earnings_text: str,
    *,
    top_bullish: list[str] | None = None,
    top_bearish: list[str] | None = None,
) -> dict[str, Any]:
    from intel.llm_signal_agent import score_text_with_llm

    bull = list(top_bullish or [])[:8]
    bear = list(top_bearish or [])[:8]
    joined = "\n".join(
        [
            earnings_text,
            "",
            "TOP BULLISH HEADLINES:",
            *([f"- {h}" for h in bull[:6]] or ["- (none flagged bullish by lexicon)"]),
            "",
            "TOP BEARISH HEADLINES:",
            *([f"- {h}" for h in bear[:6]] or ["- (none flagged bearish by lexicon)"]),
            "",
            "ALL HEADLINES:",
            "\n".join(f"- {h[:240]}" for h in headlines[:20]),
        ]
    )
    raw = score_text_with_llm(joined, symbol=symbol)
    good = max(0.0, min(1.0, float(raw.get("good_news_score", max(0.0, raw.get("sentiment", 0.0))))))
    bad = max(0.0, min(1.0, float(raw.get("bad_news_score", max(0.0, -float(raw.get("sentiment", 0.0)))))))
    if good == 0.0 and bad == 0.0:
        sent = float(raw.get("sentiment", 0.0))
        if sent > 0.15:
            good = min(1.0, sent)
        elif sent < -0.15:
            bad = min(1.0, -sent)
    narrative = str(raw.get("narrative_polarity") or raw.get("narrative") or "mixed").lower()
    if narrative not in ("good_news", "bad_news", "mixed", "neutral"):
        if good > bad + 0.20:
            narrative = "good_news"
        elif bad > good + 0.20:
            narrative = "bad_news"
        elif good > 0.35 and bad > 0.35:
            narrative = "mixed"
        else:
            narrative = "neutral"
    conf = float(raw.get("confidence", 0.0))
    block = bool(raw.get("block_long", False))
    if not block and narrative == "bad_news" and bad >= float(os.getenv("NEWS_AI_BLOCK_BAD_SCORE", "0.62")):
        block = conf >= float(os.getenv("NEWS_AI_BLOCK_MIN_CONF", "0.45"))
    boost = narrative == "good_news" and good >= float(os.getenv("NEWS_AI_BOOST_GOOD_SCORE", "0.58"))
    return {
        "good_news_score": good,
        "bad_news_score": bad,
        "sentiment": float(raw.get("sentiment", good - bad)),
        "confidence": conf,
        "narrative": narrative,
        "block_long": block,
        "boost_long": boost,
        "llm_thesis": str(raw.get("key_thesis", ""))[:300],
        "key_good": list(raw.get("key_good_drivers") or [])[:4],
        "key_bad": list(raw.get("key_bad_risks") or [])[:4],
    }


def analyze_symbol_news(symbol: str, *, force_refresh: bool = False) -> dict[str, Any]:
    """Run lexicon digest + optional LLM good/bad split + earnings context."""
    sym = symbol.strip().upper()
    if not sym:
        return _neutral(sym)

    now = time.time()
    hit = _INTEL_CACHE.get(sym)
    if not force_refresh and hit and (now - hit[0]) < _cache_ttl():
        return dict(hit[1])

    try:
        from intel.earnings_calendar import earnings_context_text, earnings_snapshot

        earn_snap = earnings_snapshot(sym)
        earn_text = earnings_context_text(sym)
    except Exception:
        earn_snap = {}
        earn_text = ""

    try:
        from intel.news_digest import build_news_digest

        digest = build_news_digest(sym, use_llm=False)
    except Exception as e:
        log.debug("[NEWS_AI] digest failed %s: %s", sym, e)
        out = _neutral(sym)
        out["earnings_context"] = earn_text
        out["days_to_earnings"] = earn_snap.get("days_to_earnings")
        _INTEL_CACHE[sym] = (now, out)
        return out

    lex_score = float(digest.composite_score)
    good_lex = len(digest.top_bullish)
    bad_lex = len(digest.top_bearish)
    good_score = min(1.0, 0.25 * good_lex + max(0.0, lex_score))
    bad_score = min(1.0, 0.25 * bad_lex + max(0.0, -lex_score))

    institutional_meta: dict[str, Any] = {}
    try:
        from intel.institutional_flow_signals import assess_institutional_flow

        inst_docs = list(dict.fromkeys((digest.top_bullish or []) + (digest.top_bearish or [])))
        institutional_meta = assess_institutional_flow(sym, documents=inst_docs or None)
        if institutional_meta.get("factor"):
            inst_factor = float(institutional_meta.get("factor") or 0.0)
            if inst_factor > 0:
                good_score = min(1.0, good_score + 0.35 * inst_factor)
            elif inst_factor < 0:
                bad_score = min(1.0, bad_score + 0.35 * abs(inst_factor))
    except Exception as e:
        log.debug("[NEWS_AI] institutional flow skipped %s: %s", sym, e)

    insider_meta: dict[str, Any] = {}
    try:
        from intel.insider_signals import assess_insider_flow

        insider_meta = assess_insider_flow(sym)
        ins_factor = float(insider_meta.get("factor") or 0.0)
        if insider_meta.get("block_long"):
            bad_score = max(bad_score, float(os.getenv("NEWS_AI_INSIDER_BLOCK_BAD", "0.68")))
        elif ins_factor < -0.12:
            bad_score = min(1.0, bad_score + 0.40 * abs(ins_factor))
        elif ins_factor > 0.12:
            good_score = min(1.0, good_score + 0.25 * ins_factor)
    except Exception as e:
        log.debug("[NEWS_AI] insider flow skipped %s: %s", sym, e)

    llm_meta: dict[str, Any] = {}
    use_llm = _enabled() and os.getenv("USE_LLM_SIGNAL", "true").lower() in ("1", "true", "yes")
    headlines = list(dict.fromkeys((digest.top_bullish or []) + (digest.top_bearish or [])))
    if use_llm:
        try:
            from intel.headline_fetch_parallel import fetch_headline_groups_parallel

            fh, na, cr = fetch_headline_groups_parallel(sym, finnhub_limit=20, news_limit=20, cramer_limit=6)
            for grp in (fh, na, cr):
                headlines.extend(h[:220] for h in grp if h)
            headlines = list(dict.fromkeys(headlines))[:30]
            llm_meta = _llm_analyze(
                sym,
                headlines,
                earn_text,
                top_bullish=digest.top_bullish,
                top_bearish=digest.top_bearish,
            )
            good_score = max(good_score, float(llm_meta.get("good_news_score", 0.0)))
            bad_score = max(bad_score, float(llm_meta.get("bad_news_score", 0.0)))
        except Exception as e:
            log.debug("[NEWS_AI] llm analyze skipped %s: %s", sym, e)

    verdict = str(digest.verdict)
    if llm_meta.get("narrative") == "good_news":
        verdict = "bullish"
    elif llm_meta.get("narrative") == "bad_news":
        verdict = "bearish"
    elif llm_meta.get("narrative") == "mixed":
        verdict = "mixed"

    sentiment = _blend_sentiment(
        lex_score,
        good_score,
        bad_score,
        float(llm_meta.get("sentiment", lex_score)),
        verdict=verdict,
    )
    block_thr = float(os.getenv("SENTIMENT_BLOCK_THRESHOLD", "-0.35"))
    block_long = bool(
        llm_meta.get("block_long")
        or insider_meta.get("block_long")
        or digest.block_long
        or (sentiment < block_thr and verdict in ("bearish", "mixed"))
        or (bad_score >= float(os.getenv("NEWS_AI_BLOCK_BAD_SCORE", "0.62")) and good_score < 0.35)
    )
    boost_long = bool(
        llm_meta.get("boost_long")
        or institutional_meta.get("boost_long")
        or (verdict == "bullish" and good_score >= float(os.getenv("NEWS_AI_BOOST_GOOD_SCORE", "0.58")))
    )
    if institutional_meta.get("boost_long") and verdict != "bearish":
        verdict = "bullish"

    net = "neutral"
    if good_score > bad_score + 0.18:
        net = "good_news"
    elif bad_score > good_score + 0.18:
        net = "bad_news"
    elif good_score > 0.35 and bad_score > 0.35:
        net = "mixed"

    out: dict[str, Any] = {
        "symbol": sym,
        "sentiment": sentiment,
        "good_news_score": round(good_score, 4),
        "bad_news_score": round(bad_score, 4),
        "net_polarity": net,
        "narrative": str(llm_meta.get("narrative") or net),
        "confidence": float(llm_meta.get("confidence", 0.0)),
        "block_long": block_long,
        "boost_long": boost_long,
        "verdict": verdict,
        "bullish_headlines": digest.bullish_count,
        "bearish_headlines": digest.bearish_count,
        "top_bullish": digest.top_bullish[:3],
        "top_bearish": digest.top_bearish[:3],
        "key_good": llm_meta.get("key_good") or digest.top_bullish[:2],
        "key_bad": llm_meta.get("key_bad") or digest.top_bearish[:2],
        "llm_thesis": str(llm_meta.get("llm_thesis") or digest.llm_thesis or "")[:300],
        "earnings_context": earn_text,
        "days_to_earnings": earn_snap.get("days_to_earnings"),
        "next_earnings_date": earn_snap.get("next_earnings_date"),
        "in_earnings_window": bool(earn_snap.get("in_earnings_window")),
        "institutional_flow": institutional_meta if institutional_meta else None,
        "source": "llm+lexicon" if llm_meta else "lexicon",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    _INTEL_CACHE[sym] = (now, out)
    log.info(
        "[NEWS_AI] %s narrative=%s good=%.2f bad=%.2f sent=%.3f block=%s dte=%s",
        sym,
        out["narrative"],
        good_score,
        bad_score,
        sentiment,
        block_long,
        out.get("days_to_earnings"),
    )
    return out


def score_adjustments(intel: dict[str, Any]) -> tuple[float, float]:
    """Return (p_up_delta, score_delta) from AI news intel."""
    if not intel or not _enabled():
        return 0.0, 0.0
    p_delta = 0.0
    s_delta = 0.0
    good = float(intel.get("good_news_score", 0.0))
    bad = float(intel.get("bad_news_score", 0.0))
    if intel.get("boost_long"):
        p_delta += float(os.getenv("NEWS_AI_GOOD_P_UP_BOOST", "0.04"))
        s_delta += float(os.getenv("NEWS_AI_GOOD_SCORE_BOOST", "0.18"))
    if intel.get("block_long") or intel.get("narrative") == "bad_news":
        p_delta -= float(os.getenv("NEWS_AI_BAD_P_UP_PENALTY", "0.06"))
        s_delta -= float(os.getenv("NEWS_AI_BAD_SCORE_PENALTY", "0.28"))
    elif bad > good + 0.15:
        s_delta -= float(os.getenv("NEWS_AI_BAD_SCORE_PENALTY", "0.28")) * min(1.0, bad)
    elif good > bad + 0.15:
        s_delta += float(os.getenv("NEWS_AI_GOOD_SCORE_BOOST", "0.18")) * min(1.0, good)
    inst = intel.get("institutional_flow") if isinstance(intel.get("institutional_flow"), dict) else {}
    if inst.get("boost_long"):
        p_delta += float(inst.get("p_up_delta") or os.getenv("INSTITUTIONAL_P_UP_DELTA_SCALE", "0.05"))
        s_delta += float(inst.get("score_delta") or os.getenv("RANK_W_INSTITUTIONAL", "0.20"))
    return p_delta, s_delta


def clear_news_ai_cache(symbol: str | None = None) -> None:
    if symbol:
        _INTEL_CACHE.pop(symbol.strip().upper(), None)
    else:
        _INTEL_CACHE.clear()
