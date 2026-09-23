"""
Finnhub headlines + optional FinBERT (ProsusAI/finbert) scores.
Blocks aggressive longs when sentiment very negative if SENTIMENT_BLOCK_LONG=true
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import requests

from utils import log

FINNHUB = "https://finnhub.io/api/v1/company-news"

# Per-process caches + circuit breakers.
_SENT_CACHE: dict[str, float] = {}
_SENT_CACHE_TS: dict[str, float] = {}
_LAST_NEWS_INTEL: dict[str, dict] = {}
_NEWSAPI_DISABLED = False
_FINNHUB_DISABLED = False

_SENT_HTTP_TIMEOUT = float(os.getenv("SENT_HTTP_TIMEOUT", "6"))
_NEWSAPI_BREAKER = Path(os.getenv("FATE_ROOT", ".")) / "data" / "newsapi_circuit_open.json"
_NEWSAPI_COOLDOWN_SEC = float(os.getenv("NEWSAPI_COOLDOWN_SEC", str(6 * 3600)))


def _newsapi_circuit_open() -> bool:
    """Shared cross-process breaker so restarts don't re-hit NewsAPI after 429."""
    global _NEWSAPI_DISABLED
    if _NEWSAPI_DISABLED:
        return True
    try:
        if not _NEWSAPI_BREAKER.is_file():
            return False
        import json

        doc = json.loads(_NEWSAPI_BREAKER.read_text(encoding="utf-8"))
        until = float(doc.get("until_ts") or 0)
        if until > time.time():
            _NEWSAPI_DISABLED = True
            return True
        _NEWSAPI_BREAKER.unlink(missing_ok=True)
    except Exception:
        return False
    return False


def _disable_newsapi(reason: str) -> None:
    global _NEWSAPI_DISABLED
    already = _NEWSAPI_DISABLED or _newsapi_circuit_open()
    _NEWSAPI_DISABLED = True
    try:
        import json

        _NEWSAPI_BREAKER.parent.mkdir(parents=True, exist_ok=True)
        _NEWSAPI_BREAKER.write_text(
            json.dumps(
                {
                    "until_ts": time.time() + _NEWSAPI_COOLDOWN_SEC,
                    "reason": reason[:200],
                    "set_at": time.time(),
                }
            )
            + "\n",
            encoding="utf-8",
        )
    except Exception:
        pass
    if already:
        return
    log.warning(
        "[SENT] NewsAPI disabled for this process (%s). Set NEWSAPI_KEY or wait for quota reset.",
        reason[:140],
    )


def _disable_finnhub(reason: str) -> None:
    global _FINNHUB_DISABLED
    if _FINNHUB_DISABLED:
        return
    _FINNHUB_DISABLED = True
    log.warning("[SENT] Finnhub disabled for this process (%s).", reason[:140])


def fetch_newsapi_headlines(symbol: str, limit: int = 20) -> list[str]:
    if _newsapi_circuit_open():
        return []
    if os.getenv("USE_NEWSAPI", "true").lower() in ("0", "false", "no"):
        return []
    key = os.getenv("NEWSAPI_KEY", "").strip()
    if not key:
        return []
    try:
        from intel.symbol_news_context import newsapi_search_query

        q = newsapi_search_query(symbol)
        url = "https://newsapi.org/v2/everything"
        r = requests.get(
            url,
            params={"q": q, "language": "en", "pageSize": limit, "sortBy": "publishedAt", "apiKey": key},
            timeout=_SENT_HTTP_TIMEOUT,
        )
        if r.status_code == 429:
            _disable_newsapi(f"HTTP 429 on {symbol}")
            return []
        r.raise_for_status()
        arts = r.json().get("articles") or []
        return [(a.get("title") or "") + " " + (a.get("description") or "") for a in arts]
    except Exception as e:
        log.warning("[SENT] NewsAPI failed: %s", e)
        return []


def fetch_cramer_mentions(symbol: str, limit: int = 10) -> list[str]:
    try:
        from intel.api_coverage import cramer_headlines_from_replay, should_skip_cramer_newsapi

        replay = cramer_headlines_from_replay(symbol, limit=limit)
        if replay:
            return replay
        if should_skip_cramer_newsapi():
            return []
    except Exception:
        pass
    if _newsapi_circuit_open():
        return []
    if os.getenv("USE_NEWSAPI", "true").lower() in ("0", "false", "no"):
        return []
    key = os.getenv("NEWSAPI_KEY", "").strip()
    if not key:
        return []
    try:
        url = "https://newsapi.org/v2/everything"
        query = f"Jim Cramer {symbol}"
        r = requests.get(
            url,
            params={"q": query, "language": "en", "pageSize": limit, "sortBy": "publishedAt", "apiKey": key},
            timeout=_SENT_HTTP_TIMEOUT,
        )
        if r.status_code == 429:
            _disable_newsapi(f"HTTP 429 on Cramer({symbol})")
            return []
        r.raise_for_status()
        arts = r.json().get("articles") or []
        return [(a.get("title") or "") + " " + (a.get("description") or "") for a in arts]
    except Exception as e:
        log.warning("[SENT] Cramer mentions fetch failed: %s", e)
        return []


def fetch_finnhub_headlines(
    symbol: str, limit: int = 20, *, as_of: str | None = None
) -> list[str]:
    if _FINNHUB_DISABLED:
        return []
    from intel.point_in_time import filter_items_as_of, news_window

    start, end = news_window(as_of, lookback_days=7)
    sym = symbol.strip().upper()
    if os.getenv("FINNHUB_SENTIMENT_FIRST", "true").lower() in ("1", "true", "yes"):
        try:
            from intel.finnhub_batch import fetch_company_news_lite, fetch_sentiment

            fetch_sentiment(sym)
            lite = fetch_company_news_lite(sym, limit=limit, as_of=as_of)
            if lite:
                return lite
            if as_of is None and os.getenv(
                "FINNHUB_SKIP_COMPANY_NEWS_IF_SENTIMENT", "true"
            ).lower() in ("1", "true", "yes"):
                from intel.finnhub_batch import sentiment_headline_skip

                if sentiment_headline_skip(sym):
                    return []
        except Exception:
            pass
    key = os.getenv("FINNHUB_API_KEY", "").strip()
    if not key:
        return []
    try:
        r = requests.get(
            FINNHUB,
            params={
                "symbol": symbol,
                "from": start.isoformat(),
                "to": end.isoformat(),
                "token": key,
            },
            timeout=_SENT_HTTP_TIMEOUT,
        )
        if r.status_code in (401, 403, 429):
            _disable_finnhub(f"HTTP {r.status_code} on {symbol}")
            return []
        r.raise_for_status()
        body = r.json()
        items = body if isinstance(body, list) else []
        items = filter_items_as_of(items, as_of)[:limit]
        return [(it.get("headline") or "") + " " + (it.get("summary") or "") for it in items]
    except Exception as e:
        log.warning("[SENT] Finnhub failed: %s", e)
        return []


def finbert_score(texts: list[str]) -> float:
    if not texts:
        return 0.0
    if os.getenv("USE_FINBERT", "false").lower() not in ("1", "true", "yes"):
        from news_reader import analyze_sentiment

        return sum(analyze_sentiment(t) for t in texts) / len(texts)

    try:
        scores = [_finbert_model_score(os.getenv("FINBERT_MODEL", "ProsusAI/finbert"), texts)]
        tone = os.getenv("FINBERT_TONE_MODEL", "yiyanghkust/finbert-tone").strip()
        primary = os.getenv("FINBERT_MODEL", "ProsusAI/finbert").strip()
        if tone and tone != primary:
            try:
                scores.append(_finbert_model_score(tone, texts))
            except Exception as e:
                log.debug("[SENT] FinBERT-tone skip: %s", e)
        scores = [s for s in scores if s is not None]
        if not scores:
            raise RuntimeError("no finbert scores")
        return sum(scores) / len(scores)
    except Exception as e:
        log.warning("[SENT] FinBERT unavailable (%s) — keyword fallback", e)
        from news_reader import analyze_sentiment

        return sum(analyze_sentiment(t) for t in texts) / max(len(texts), 1)


_FINBERT_MODELS: dict[str, tuple] = {}


def _finbert_model_score(name: str, texts: list[str]) -> float:
    # Missing tokenizer files 404 in a long probe. Cap that so a scan is not stuck.
    os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "3")
    os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "8")
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    import torch

    bundle = _FINBERT_MODELS.get(name)
    if bundle is None:
        tok = AutoTokenizer.from_pretrained(name)
        mdl = AutoModelForSequenceClassification.from_pretrained(name)
        mdl.eval()
        _FINBERT_MODELS[name] = (tok, mdl)
    else:
        tok, mdl = bundle
    scores = []
    chunk = texts[:20]
    for t in chunk:
        if not t.strip():
            continue
        inp = tok(t[:512], return_tensors="pt", truncation=True, padding=True)
        with torch.no_grad():
            out = mdl(**inp).logits.softmax(-1)[0]
        p = out.tolist()
        # FinBERT-family: last=pos, first=neg when 3-way; 2-way uses pos-neg.
        if len(p) >= 3:
            s = p[2] - p[0]
        elif len(p) == 2:
            s = p[1] - p[0]
        else:
            s = p[0]
        scores.append(s)
    return sum(scores) / max(len(scores), 1)


def clear_sentiment_cache(symbol: str | None = None) -> None:
    """Drop cached sentiment so the next composite_sentiment() hits live APIs."""
    if symbol is None:
        _SENT_CACHE.clear()
        _SENT_CACHE_TS.clear()
        _LAST_NEWS_INTEL.clear()
        try:
            from intel.news_ai_agent import clear_news_ai_cache

            clear_news_ai_cache()
        except Exception:
            pass
        return
    sym = symbol.strip().upper()
    _SENT_CACHE.pop(sym, None)
    _SENT_CACHE_TS.pop(sym, None)
    _LAST_NEWS_INTEL.pop(sym, None)
    try:
        from intel.news_ai_agent import clear_news_ai_cache

        clear_news_ai_cache(sym)
    except Exception:
        pass


def get_symbol_news_intel(symbol: str) -> dict:
    """Latest AI news intel for symbol (populates via composite_sentiment if needed)."""
    sym = symbol.strip().upper()
    if sym in _LAST_NEWS_INTEL:
        return dict(_LAST_NEWS_INTEL[sym])
    composite_sentiment(sym)
    return dict(_LAST_NEWS_INTEL.get(sym, {}))


def composite_sentiment(symbol: str) -> float:
    if os.getenv("DISABLE_SENTIMENT", "false").lower() in ("1", "true", "yes"):
        return 0.0
    sym = symbol.strip().upper()
    ttl = float(os.getenv("SENTIMENT_CACHE_TTL_SEC", "900"))
    if sym in _SENT_CACHE:
        age = __import__("time").time() - float(_SENT_CACHE_TS.get(sym, 0))
        if age < ttl:
            return _SENT_CACHE[sym]

    if os.getenv("USE_NEWS_AI_AGENT", "true").lower() in ("1", "true", "yes"):
        try:
            from intel.news_ai_agent import analyze_symbol_news

            intel = analyze_symbol_news(sym)
            _LAST_NEWS_INTEL[sym] = intel
            score = float(intel.get("sentiment", 0.0))
            _SENT_CACHE[sym] = score
            _SENT_CACHE_TS[sym] = __import__("time").time()
            return score
        except Exception as e:
            log.debug("[SENT] news AI agent skipped %s: %s", sym, e)

    verbose = os.getenv("NEWS_SENTIMENT_VERBOSE", "false").lower() in ("1", "true", "yes")
    watch = {s.strip().upper() for s in (os.getenv("NEWS_SENTIMENT_WATCH", "") or "").split(",") if s.strip()}
    if verbose or sym in watch:
        try:
            from intel.news_digest import build_news_digest, log_news_digest

            digest = build_news_digest(sym)
            log_news_digest(sym, digest)
            _SENT_CACHE[sym] = float(digest.composite_score)
            return _SENT_CACHE[sym]
        except Exception as e:
            log.debug("[SENT] digest path skipped %s: %s", sym, e)

    headlines = fetch_finnhub_headlines(sym)
    if not headlines:
        headlines = fetch_newsapi_headlines(sym)
    # When NewsAPI is 429/circuit-open, Google News RSS fills the gap (no paid quota)
    if (not headlines) or _newsapi_circuit_open():
        try:
            from intel.google_news_feed import symbol_news_headlines

            g_heads = symbol_news_headlines(sym, limit=int(os.getenv("GOOGLE_NEWS_HEADLINE_LIMIT", "14")))
            if g_heads:
                # Prefer Google headlines when NewsAPI is down; else append for coverage
                headlines = g_heads if not headlines else (headlines + g_heads)
        except Exception as e:
            log.debug("[SENT] google news rss skipped %s: %s", sym, e)
    if os.getenv("USE_CRAMER_SIGNAL", "true").lower() in ("1", "true", "yes"):
        headlines = headlines + fetch_cramer_mentions(sym, limit=8)
    if not headlines:
        try:
            from news_reader import fetch_news
            alt = fetch_news(sym)
            headlines = [a["headline"] + " " + a.get("summary", "") for a in alt]
        except Exception:
            headlines = []
    score = finbert_score(headlines)
    try:
        from intel.english_lexicon import enrich_headline_score

        blob = " ".join(headlines[:12])
        score = enrich_headline_score(blob, score)
    except Exception:
        pass
    if os.getenv("USE_INTEL_FACTORS", "true").lower() in ("1", "true", "yes"):
        try:
            from intel.news_factor_engine import score_symbol_news_factors
            from intel.transcript_factor_engine import score_symbol_transcripts

            nf = score_symbol_news_factors(sym)
            tf = score_symbol_transcripts(sym)
            if os.getenv("HEAVY_NEWS_INTEL", "false").lower() in ("1", "true", "yes"):
                # Heavier weight on structured intel (news + transcripts) vs raw headline FinBERT.
                score = (
                    0.25 * float(score)
                    + 0.50 * float(nf.get("final_factor", 0.0))
                    + 0.25 * float(tf.get("final_factor", 0.0))
                )
            else:
                score = (
                    0.55 * float(score)
                    + 0.30 * float(nf.get("final_factor", 0.0))
                    + 0.15 * float(tf.get("final_factor", 0.0))
                )
        except Exception as e:
            log.debug("[SENT] intel factor blend skipped %s: %s", symbol, e)
    _SENT_CACHE[sym] = score
    _SENT_CACHE_TS[sym] = __import__("time").time()
    return score


def block_long_on_sentiment(score: float, *, symbol: str | None = None) -> bool:
    if os.getenv("SENTIMENT_BLOCK_LONG", "true").lower() not in ("1", "true", "yes"):
        return False
    if symbol:
        intel = get_symbol_news_intel(symbol)
        if intel.get("block_long"):
            return True
        if intel.get("narrative") == "bad_news" and float(intel.get("bad_news_score", 0.0)) >= float(
            os.getenv("NEWS_AI_BLOCK_BAD_SCORE", "0.62")
        ):
            return True
    thr = float(os.getenv("SENTIMENT_BLOCK_THRESHOLD", "-0.35"))
    return score < thr
