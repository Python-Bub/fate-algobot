"""AI analysis of Jim Cramer CNBC Top 10 — structured intel for trading calculations."""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from typing import Any

from utils import log

SKIP_SYMS = frozenset({"SPACE", "OPENAI", "ANTH", "GPT", "IPO"})


def _enabled() -> bool:
    return os.getenv("USE_CRAMER_AI_ANALYSIS", "true").lower() in ("1", "true", "yes")


def _clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _extract_json(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("{") and text.endswith("}"):
        return json.loads(text)
    i, j = text.find("{"), text.rfind("}")
    if i >= 0 and j > i:
        return json.loads(text[i : j + 1])
    return {}


def _cache_key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def _cramer_models() -> list[str]:
    primary = (os.getenv("CRAMER_AI_MODEL") or os.getenv("LLM_MODEL") or "gpt-4o-mini").strip()
    fallbacks = [
        m.strip()
        for m in (os.getenv("CRAMER_AI_MODEL_FALLBACKS") or "gpt-4o-mini,gpt-3.5-turbo").split(",")
        if m.strip()
    ]
    out: list[str] = []
    for m in [primary, *fallbacks]:
        if m and m not in out:
            out.append(m)
    return out


def _post_chat_with_retry(messages: list[dict], *, retries: int | None = None) -> str:
    import requests

    base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    key = (os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("LLM_API_KEY (or OPENAI_API_KEY) missing")
    timeout = float(os.getenv("CRAMER_AI_TIMEOUT_SEC", os.getenv("LLM_TIMEOUT_SEC", "45")))
    delay = float(os.getenv("CRAMER_AI_RETRY_DELAY_SEC", "6"))
    max_wait = float(os.getenv("CRAMER_AI_MAX_RETRY_WAIT_SEC", "45"))
    if retries is None:
        retries = int(os.getenv("CRAMER_AI_RETRIES", "3"))
    models = _cramer_models()
    last_err: Exception | None = None
    for model in models:
        for attempt in range(retries):
            try:
                r = requests.post(
                    f"{base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={
                        "model": model,
                        "messages": messages,
                        "temperature": 0.0,
                        "response_format": {"type": "json_object"},
                    },
                    timeout=timeout,
                )
                r.raise_for_status()
                js = r.json()
                log.info("[CRAMER_AI] model=%s ok", model)
                return str(js["choices"][0]["message"]["content"])
            except Exception as e:
                last_err = e
                err = str(e).lower()
                if "429" in err or "rate" in err or "too many" in err:
                    wait = delay * (2**attempt)
                    log.info(
                        "[CRAMER_AI] rate limited model=%s — retry %d in %.0fs",
                        model,
                        attempt + 1,
                        wait,
                    )
                    time.sleep(min(wait, max_wait))
                    continue
                if "404" in err or "model" in err:
                    log.info("[CRAMER_AI] model=%s unavailable — trying fallback", model)
                    break
                raise
    if last_err:
        raise last_err
    raise RuntimeError("LLM call failed")


def _normalize_ticker_row(sym: str, row: dict) -> dict:
    conv = str(row.get("conviction") or "medium").lower()
    if conv not in ("low", "medium", "high"):
        conv = "medium"
    catalyst = str(row.get("catalyst") or "").lower()[:32]
    return {
        "sentiment": _clip(float(row.get("sentiment", 0.0)), -1, 1),
        "action_bias": _clip(float(row.get("action_bias", row.get("sentiment", 0.0))), -1, 1),
        "ai_confidence": _clip(float(row.get("confidence", row.get("ai_confidence", 0.0))), 0, 1),
        "conviction": conv,
        "club_held": bool(row.get("club_held", False)),
        "block_long": bool(row.get("block_long", False)),
        "thesis": str(row.get("thesis", ""))[:240],
        "catalyst": catalyst,
        "good_news_score": _clip(float(row.get("good_news_score", 0.0)), 0, 1),
        "bad_news_score": _clip(float(row.get("bad_news_score", 0.0)), 0, 1),
        "horizon": str(row.get("horizon") or "intraday")[:24],
        "item_number": int(row.get("item_number") or 0),
    }


def analyze_cramer_top10(text: str, *, force_refresh: bool = False) -> dict | None:
    """
    One batched LLM call for the full Top 10 article.
    Cached 24h by content hash. Returns structured dict for morning_club_intel merge.
    """
    if not _enabled() or not (text or "").strip():
        return None
    if os.getenv("USE_LLM_SIGNAL", "false").lower() not in ("1", "true", "yes"):
        return None
    key = (os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        return None

    ck = _cache_key(text)
    try:
        from intel.api_budget import cache_get, cache_set

        if not force_refresh:
            cached = cache_get("cramer_ai", ck)
            if isinstance(cached, dict) and cached.get("tickers"):
                cached["from_cache"] = True
                return cached
    except Exception:
        pass

    try:
        from intel.api_budget import allow, llm_allowed, record

        if not llm_allowed(force=True) and not allow("llm") and not allow("cramer_llm"):
            log.debug("[CRAMER_AI] LLM budget/window blocked")
            return None
    except Exception:
        pass

    system = (
        "You are a senior equity analyst parsing Jim Cramer's CNBC Investing Club "
        "'Top 10 things to watch' for an automated US stock trading system.\n"
        "Read all 10 numbered items. Map company names to US tickers (Broadcom->AVGO, "
        "CrowdStrike->CRWD, Alphabet->GOOGL, Nvidia->NVDA, Wells Fargo->WFC, "
        "Goldman Sachs->GS, Honeywell->HON, Capital One->COF, Home Depot->HD, "
        "Five Below->FIVE, Dollar Tree->DLTR, Dollar General->DG, Ollie's->OLLI, "
        "Quantinuum is not listed — note Honeywell HON sympathy only).\n"
        "Club 'owns' = Cramer says the Charitable Trust holds the name.\n"
        "Separate: bullish catalyst vs dilution/IPO supply/macro headwind.\n"
        "Return strict JSON:\n"
        "{\n"
        '  "market_tone": "risk_on|risk_off|mixed",\n'
        '  "market_sentiment": -1..1,\n'
        '  "ai_confidence": 0..1,\n'
        '  "day_trade_bias": -1..1,\n'
        '  "ai_thesis": "one sentence overall",\n'
        '  "macro_themes": ["..."],\n'
        '  "macro_risks": ["..."],\n'
        '  "club_owns": ["TICKER",...],\n'
        '  "top_buys": ["TICKER",...],\n'
        '  "top_avoids": ["TICKER",...],\n'
        '  "items": [{"n":1,"headline":"...","tickers":["..."],"bias":-1..1}],\n'
        '  "tickers": {\n'
        '    "TICKER": {\n'
        '      "sentiment": -1..1, "action_bias": -1..1, "confidence": 0..1,\n'
        '      "conviction": "low|medium|high", "club_held": bool, "block_long": bool,\n'
        '      "good_news_score": 0..1, "bad_news_score": 0..1,\n'
        '      "catalyst": "earnings|ipo_supply|upgrade|guidance|macro|none",\n'
        '      "horizon": "intraday|swing|avoid", "item_number": 1-10,\n'
        '      "thesis": "one line"\n'
        "    }\n"
        "  }\n"
        "}\n"
        "Include EVERY tradeable US ticker mentioned across all 10 items."
    )
    user = f"Cramer Top 10 article:\n\n{text[:14000]}"

    try:
        raw = _post_chat_with_retry(
            [{"role": "system", "content": system}, {"role": "user", "content": user}]
        )
        obj = _extract_json(raw)
        if not obj:
            return None

        tickers_in = obj.get("tickers") or {}
        tickers: dict[str, dict] = {}
        if isinstance(tickers_in, dict):
            for k, v in tickers_in.items():
                sym = str(k).strip().upper()
                if not sym or sym in SKIP_SYMS or len(sym) > 5 or not isinstance(v, dict):
                    continue
                tickers[sym] = _normalize_ticker_row(sym, v)

        owns = [str(x).strip().upper() for x in (obj.get("club_owns") or []) if str(x).strip()]
        for sym in owns:
            if sym in tickers:
                tickers[sym]["club_held"] = True

        tone = str(obj.get("market_tone") or "mixed").lower()
        if tone not in ("risk_on", "risk_off", "mixed"):
            tone = "mixed"

        out: dict[str, Any] = {
            "market_tone": tone,
            "market_sentiment": _clip(float(obj.get("market_sentiment", 0.0)), -1, 1),
            "ai_confidence": _clip(float(obj.get("ai_confidence", 0.0)), 0, 1),
            "day_trade_bias": _clip(float(obj.get("day_trade_bias", 0.0)), -1, 1),
            "ai_thesis": str(obj.get("ai_thesis", ""))[:400],
            "macro_themes": [str(x)[:120] for x in (obj.get("macro_themes") or [])[:8]],
            "macro_risks": [str(x)[:120] for x in (obj.get("macro_risks") or [])[:8]],
            "club_owns": owns,
            "top_buys": [str(x).upper() for x in (obj.get("top_buys") or [])[:12]],
            "top_avoids": [str(x).upper() for x in (obj.get("top_avoids") or [])[:12]],
            "items": (obj.get("items") or [])[:10],
            "tickers": tickers,
            "parser": "ai",
            "analyzed_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        try:
            from intel.api_budget import cache_set, record

            cache_set("cramer_ai", ck, out, ttl_sec=float(os.getenv("CRAMER_AI_CACHE_TTL_SEC", "86400")))
            record("cramer_llm")
            record("llm")
        except Exception:
            pass
        log.info(
            "[CRAMER_AI] analyzed Top 10 — %d tickers, tone=%s conf=%.2f buys=%s",
            len(tickers),
            tone,
            out["ai_confidence"],
            out["top_buys"][:4],
        )
        return out
    except Exception as e:
        log.warning("[CRAMER_AI] analysis failed: %s", e)
        return None


def merge_ai_and_heuristic(ai: dict | None, heuristic: dict) -> dict:
    """Blend AI + rules; AI dominates when confidence is high."""
    if not ai or not ai.get("tickers"):
        heuristic["parser"] = heuristic.get("parser", "heuristic")
        return heuristic

    w = float(os.getenv("CRAMER_AI_BLEND", "0.72"))
    ai_conf = float(ai.get("ai_confidence", 0.0))
    if ai_conf >= float(os.getenv("CRAMER_AI_HIGH_CONF", "0.65")):
        w = max(w, float(os.getenv("CRAMER_AI_HIGH_BLEND", "0.85")))

    tickers: dict[str, dict] = {}
    all_syms = set(heuristic.get("tickers") or {}) | set(ai.get("tickers") or {})
    for sym in all_syms:
        h = (heuristic.get("tickers") or {}).get(sym) or {}
        a = (ai.get("tickers") or {}).get(sym) or {}
        if not a and h:
            tickers[sym] = dict(h)
            continue
        if a and not h:
            tickers[sym] = dict(a)
            tickers[sym]["ai_action_bias"] = a.get("action_bias", 0)
            continue
        sent = (1 - w) * float(h.get("sentiment", 0)) + w * float(a.get("sentiment", 0))
        abias = (1 - w) * float(h.get("action_bias", 0)) + w * float(a.get("action_bias", 0))
        row = {
            "sentiment": _clip(sent, -1, 1),
            "action_bias": _clip(abias, -1, 1),
            "ai_action_bias": float(a.get("action_bias", 0)),
            "ai_confidence": float(a.get("ai_confidence", ai_conf)),
            "conviction": a.get("conviction") or h.get("conviction", "medium"),
            "club_held": bool(a.get("club_held") or h.get("club_held")),
            "block_long": bool(a.get("block_long") or h.get("block_long")),
            "thesis": str(a.get("thesis") or h.get("thesis", ""))[:240],
            "catalyst": a.get("catalyst") or h.get("catalyst", ""),
            "good_news_score": float(a.get("good_news_score", 0)),
            "bad_news_score": float(a.get("bad_news_score", 0)),
            "horizon": a.get("horizon", "intraday"),
        }
        if sym in (ai.get("top_buys") or []):
            row["action_bias"] = max(float(row["action_bias"]), 0.45)
            row["conviction"] = "high"
        if sym in (ai.get("top_avoids") or []):
            row["block_long"] = True
            row["action_bias"] = min(float(row["action_bias"]), -0.25)
        tickers[sym] = row

    tone = ai.get("market_tone") or heuristic.get("market_tone", "mixed")
    msent = (1 - w) * float(heuristic.get("market_sentiment", 0)) + w * float(
        ai.get("market_sentiment", 0)
    )
    return {
        "market_tone": tone,
        "market_sentiment": _clip(msent, -1, 1),
        "macro_themes": list(dict.fromkeys((ai.get("macro_themes") or []) + (heuristic.get("macro_themes") or [])))[:8],
        "macro_risks": list(dict.fromkeys((ai.get("macro_risks") or []) + (heuristic.get("macro_risks") or [])))[:8],
        "club_owns": list(dict.fromkeys((ai.get("club_owns") or []) + (heuristic.get("club_owns") or []))),
        "tickers": tickers,
        "parser": "ai+heuristic",
        "ai_confidence": ai_conf,
        "day_trade_bias": float(ai.get("day_trade_bias", 0)),
        "ai_thesis": ai.get("ai_thesis", ""),
        "top_buys": ai.get("top_buys") or [],
        "top_avoids": ai.get("top_avoids") or [],
        "ai_items": ai.get("items") or [],
    }
