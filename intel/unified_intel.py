"""Unified intel hub — Cramer, news AI, insider flow, institutional flow in one score."""

from __future__ import annotations

import os
import re
import time
from typing import Any

_INSIDER_HEADLINE_RE = re.compile(
    r"\b("
    r"insiders?\s+sold|insider\s+sale|insider\s+sell|"
    r"(?:ceo|cfo|coo|cto|chief|president|chairman|director|officer|executive|hr).{0,50}sell|"
    r"sold\s+\$[\d.,]+\s*(?:m|million|b|billion)\s*(?:of\s+)?(?:stock|shares)?|"
    r"sells?\s+\$[\d.,]+\s*(?:m|million|b|billion)|"
    r"sells?\s+[\d,]+\s+shares|"
    r"10b5-?1|form\s+4|"
    r"officer\s+sold|executive\s+sold|"
    r"chief\s+\w+\s+officer\s+.{0,40}sell"
    r")\b",
    re.I,
)

_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def _enabled() -> bool:
    return os.getenv("UNIFIED_INTEL_ENABLED", "true").lower() in ("1", "true", "yes")


def _cache_ttl() -> float:
    return float(os.getenv("UNIFIED_INTEL_CACHE_SEC", "600"))


def _clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def unified_intel_for(symbol: str, *, force_refresh: bool = False) -> dict[str, Any]:
    """
    Composite intel for a symbol — used by family forecast, day-trade rank, fusion.
    Insider selling (e.g. EQIX C-suite sale) raises bad_news_score and can block longs.
    """
    sym = symbol.strip().upper()
    empty: dict[str, Any] = {
        "symbol": sym,
        "block_long": False,
        "block_reasons": [],
        "boost": 0.0,
        "good_news_score": 0.0,
        "bad_news_score": 0.0,
        "cramer_boost": 0.0,
        "insider_factor": 0.0,
        "news_sentiment": 0.0,
        "institutional_factor": 0.0,
        "media_boost": 0.0,
        "media_sentiment": 0.0,
        "social_sentiment": 0.0,
        "open_web_boost": 0.0,
        "analyst_score": 0.0,
        "day_trade_bias": 0.0,
        "in_top_buys": False,
        "in_top_avoids": False,
        "sources": [],
    }
    if not sym or not _enabled():
        return empty

    now = time.time()
    if not force_refresh:
        hit = _CACHE.get(sym)
        if hit and now - hit[0] < _cache_ttl():
            return dict(hit[1])

    out = dict(empty)
    reasons: list[str] = []
    good = 0.0
    bad = 0.0
    boost = 0.0

    # --- Cramer / morning club ---
    try:
        from intel.morning_club_intel import (
            cramer_day_trade_bias,
            load_latest,
            morning_club_block_long,
            morning_club_boost_for,
        )

        doc = load_latest()
        club = (doc.get("tickers") or {}).get(sym) or {}
        cramer_b = float(morning_club_boost_for(sym))
        out["cramer_boost"] = cramer_b
        out["day_trade_bias"] = float(cramer_day_trade_bias())
        out["in_top_buys"] = sym in {str(x).upper() for x in (doc.get("top_buys") or [])}
        out["in_top_avoids"] = sym in {str(x).upper() for x in (doc.get("top_avoids") or [])}
        good = max(good, float(club.get("good_news_score") or 0.0))
        bad = max(bad, float(club.get("bad_news_score") or 0.0))
        boost += cramer_b * float(os.getenv("UNIFIED_CRAMER_BLEND", "0.55"))
        if out["in_top_buys"]:
            boost += float(os.getenv("UNIFIED_TOP_BUY_ADD", "0.12"))
        if morning_club_block_long(sym) or out["in_top_avoids"]:
            out["block_long"] = True
            reasons.append("cramer_block")
        if club:
            out["sources"].append("cramer")
    except Exception:
        pass

    # --- Live news AI (headlines + LLM good/bad) ---
    try:
        from sentiment_pipeline import get_symbol_news_intel

        news = get_symbol_news_intel(sym) or {}
        ng = float(news.get("good_news_score") or 0.0)
        nb = float(news.get("bad_news_score") or 0.0)
        good = max(good, ng)
        bad = max(bad, nb)
        out["news_sentiment"] = float(news.get("sentiment") or 0.0)
        w_news = float(os.getenv("UNIFIED_NEWS_BLEND", "0.45"))
        boost += w_news * out["news_sentiment"]
        if news.get("block_long") or news.get("narrative") == "bad_news":
            out["block_long"] = True
            reasons.append("news_ai_block")
        if ng >= 0.55:
            boost += float(os.getenv("UNIFIED_GOOD_NEWS_ADD", "0.06")) * ng
        if nb >= 0.52 and nb > good + 0.12:
            boost -= float(os.getenv("UNIFIED_BAD_NEWS_PENALTY", "0.14")) * nb
        if news:
            out["sources"].append("news_ai")
    except Exception:
        pass

    # --- Yahoo insider transactions (structured) ---
    try:
        from intel.insider_signals import assess_insider_flow

        insider = assess_insider_flow(sym)
        factor = float(insider.get("factor") or 0.0)
        out["insider_factor"] = factor
        w_ins = float(os.getenv("UNIFIED_INSIDER_BLEND", "0.50"))
        boost += w_ins * factor
        if insider.get("block_long"):
            out["block_long"] = True
            reasons.append(str(insider.get("block_reason") or "insider_c_suite_sell"))
            bad = max(bad, 0.72)
        elif factor < -0.15:
            bad = max(bad, min(1.0, 0.35 + abs(factor) * 0.55))
        if insider.get("events"):
            out["sources"].append("insider_yahoo")
    except Exception:
        pass

    # --- Institutional flow (13F stakes — not insider sells) ---
    try:
        from intel.institutional_flow_signals import institutional_flow_factor

        inst = float(institutional_flow_factor(sym))
        out["institutional_factor"] = inst
        boost += float(os.getenv("UNIFIED_INSTITUTIONAL_BLEND", "0.25")) * inst
        if inst < -0.2:
            bad = max(bad, min(1.0, abs(inst) * 0.4))
        if abs(inst) > 0.05:
            out["sources"].append("institutional")
    except Exception:
        pass

    # --- Media intel (articles / podcasts / video captions) ---
    try:
        from intel.media_intel import media_score_for_symbol

        media = media_score_for_symbol(sym)
        mboost = float(media.get("boost") or 0.0)
        out["media_boost"] = mboost
        out["media_sentiment"] = float(media.get("sentiment") or 0.0)
        boost += float(os.getenv("UNIFIED_MEDIA_BLEND", "0.40")) * mboost
        if mboost > 0.05:
            good = max(good, min(1.0, 0.35 + mboost))
        if mboost < -0.08:
            bad = max(bad, min(1.0, 0.35 + abs(mboost)))
        if media.get("sources"):
            out["sources"].append("media_intel")
            out["sources"].extend(list(media.get("sources") or [])[:4])
    except Exception:
        pass

    # --- Open web: Wikipedia, SEC EDGAR, Wall Street analyst consensus ---
    try:
        from intel.open_web_intel import open_web_intel_for

        web = open_web_intel_for(sym)
        wboost = float(web.get("boost") or 0.0)
        out["open_web_boost"] = wboost
        out["analyst_score"] = float((web.get("analysts") or {}).get("score") or 0.0)
        boost += float(os.getenv("UNIFIED_OPEN_WEB_BLEND", "0.40")) * wboost
        if web.get("block_long"):
            out["block_long"] = True
            reasons.append("open_web_analyst_dump")
        if web.get("sources"):
            out["sources"].append("open_web")
            out["sources"].extend(list(web.get("sources") or [])[:3])
        if wboost > 0.08:
            good = max(good, min(1.0, 0.30 + wboost))
        if wboost < -0.12:
            bad = max(bad, min(1.0, 0.30 + abs(wboost)))
    except Exception:
        pass

    # --- Social sentiment ---
    try:
        from intel.social_sentiment import social_sentiment_score

        soc = social_sentiment_score(sym)
        if isinstance(soc, dict):
            ss = float(soc.get("score") or soc.get("sentiment") or 0.0)
        else:
            ss = float(soc or 0.0)
        out["social_sentiment"] = ss
        boost += float(os.getenv("UNIFIED_SOCIAL_BLEND", "0.18")) * ss
        if abs(ss) >= 0.05:
            out["sources"].append("social")
    except Exception:
        pass

    # --- Cramer post-market show notes ---
    try:
        from intel.cramer_post_market import post_market_boost_for

        pb = float(post_market_boost_for(sym) or 0.0)
        if abs(pb) >= 0.01:
            boost += float(os.getenv("UNIFIED_CRAMER_POST_BLEND", "0.20")) * pb
            out["sources"].append("cramer_post")
    except Exception:
        pass

    # --- Headline insider-sell scan (catches EQIX-style articles before Yahoo updates) ---
    try:
        from intel.headline_fetch_parallel import fetch_headline_groups_parallel

        fh, na, cr = fetch_headline_groups_parallel(sym, finnhub_limit=12, news_limit=12, cramer_limit=4)
        insider_hits = [
            h for h in (fh + na + cr) if h and _INSIDER_HEADLINE_RE.search(str(h))
        ]
        if insider_hits:
            bad = max(bad, min(1.0, 0.48 + 0.08 * min(3, len(insider_hits))))
            boost -= float(os.getenv("UNIFIED_INSIDER_HEADLINE_PENALTY", "0.18"))
            if len(insider_hits) >= 2 or any(
                re.search(r"\$[\d.]+\s*m", str(h), re.I) for h in insider_hits
            ):
                out["block_long"] = True
                reasons.append("insider_headline_sell")
            out["sources"].append("insider_headlines")
    except Exception:
        pass

    out["good_news_score"] = round(good, 4)
    out["bad_news_score"] = round(bad, 4)
    out["boost"] = round(_clip(boost, -1.0, 1.0), 4)
    out["block_reasons"] = reasons
    _CACHE[sym] = (now, out)
    return out


def blocks_long(symbol: str) -> tuple[bool, list[str]]:
    u = unified_intel_for(symbol)
    return bool(u.get("block_long")), list(u.get("block_reasons") or [])


def family_intel_adjustment(symbol: str) -> float:
    """Score bump for family_forecast rank tuple (~[-0.35, +0.35])."""
    u = unified_intel_for(symbol)
    if u.get("block_long"):
        return -0.5
    adj = float(u.get("boost") or 0.0) * float(os.getenv("FAMILY_UNIFIED_INTEL_GAIN", "0.32"))
    if u.get("in_top_buys"):
        adj += float(os.getenv("FAMILY_CRAMER_TOP_BUY_ADD", "0.08"))
    bad = float(u.get("bad_news_score") or 0.0)
    good = float(u.get("good_news_score") or 0.0)
    if bad >= 0.52 and bad > good + 0.15:
        adj -= float(os.getenv("FAMILY_BAD_NEWS_PENALTY", "0.15")) * bad
    elif good >= 0.55:
        adj += float(os.getenv("FAMILY_GOOD_NEWS_ADD", "0.06")) * good
    return _clip(adj, -0.5, 0.5)


def day_trade_intel_adjustment(symbol: str) -> tuple[float, list[str]]:
    """Returns (score_multiplier_delta, reason_tags) for day_trade_rank."""
    u = unified_intel_for(symbol)
    reasons: list[str] = []
    mult = 0.0
    if u.get("block_long"):
        return -1.0, ["unified_block"] + list(u.get("block_reasons") or [])
    boost = float(u.get("boost") or 0.0)
    if abs(boost) >= 0.06:
        mult += boost * float(os.getenv("DAY_TRADE_UNIFIED_BLEND", "0.35"))
        reasons.append(f"unified={boost:+.2f}")
    good = float(u.get("good_news_score") or 0.0)
    bad = float(u.get("bad_news_score") or 0.0)
    if good >= 0.52:
        mult += float(os.getenv("CRAMER_AI_GOOD_NEWS_SCORE_BLEND", "0.07")) * good
        reasons.append(f"good={good:.2f}")
    if bad >= 0.52 and bad > good + 0.12:
        mult -= float(os.getenv("CRAMER_AI_BAD_NEWS_SCORE_BLEND", "0.12")) * bad
        reasons.append(f"bad={bad:.2f}")
    if u.get("in_top_buys"):
        mult += float(os.getenv("DAY_TRADE_TOP_BUY_ADD", "0.10"))
        reasons.append("top_buy")
    dt = float(u.get("day_trade_bias") or 0.0)
    if abs(dt) >= 0.12:
        mult += float(os.getenv("CRAMER_DAY_BIAS_BLEND", "0.08")) * dt
    return mult, reasons
