"""LLM signal extraction agent (OpenAI-compatible API).

Purpose:
- Turn noisy unstructured text into deterministic numeric factors.
- Enforce strict JSON schema output.
- Fail closed (returns neutral factors) if model/API is unavailable.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

import requests

from utils import log


@dataclass
class LLMSignal:
    sentiment: float
    confidence: float
    action_bias: float
    horizon_days: float
    novelty: float
    key_thesis: str
    good_news_score: float
    bad_news_score: float
    narrative_polarity: str
    block_long: bool
    key_good_drivers: list[str]
    key_bad_risks: list[str]
    generated_at_utc: str


def _neutral() -> LLMSignal:
    return LLMSignal(
        sentiment=0.0,
        confidence=0.0,
        action_bias=0.0,
        horizon_days=0.0,
        novelty=0.0,
        key_thesis="",
        good_news_score=0.0,
        bad_news_score=0.0,
        narrative_polarity="neutral",
        block_long=False,
        key_good_drivers=[],
        key_bad_risks=[],
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
    )


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return json.loads(text)
    i = text.find("{")
    j = text.rfind("}")
    if i >= 0 and j > i:
        return json.loads(text[i : j + 1])
    return {}


def _post_chat(messages: list[dict]) -> str:
    from intel.llm_cooldown import active, remaining, retry_after_seconds, trip

    if active():
        raise RuntimeError(f"llm_cooldown {remaining():.0f}s")
    base = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    # Accept either LLM_API_KEY (project-specific) or OPENAI_API_KEY (standard) so the AI
    # grader doesn't silently return zeros just because the wrong env var name was used.
    key = (os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    if not key:
        raise RuntimeError("LLM_API_KEY (or OPENAI_API_KEY) missing")
    timeout = float(os.getenv("LLM_TIMEOUT_SEC", "12"))
    url = f"{base}/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.0,
        "response_format": {"type": "json_object"},
    }
    r = requests.post(
        url,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=payload,
        timeout=timeout,
    )
    if r.status_code == 429:
        wait = retry_after_seconds(r.headers, default=float(os.getenv("LLM_429_COOLDOWN_SEC", "180")))
        trip(wait, reason="openai_429")
        raise RuntimeError(f"429 cooldown {wait:.0f}s")
    r.raise_for_status()
    js = r.json()
    return str(js["choices"][0]["message"]["content"])


def _clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def score_text_with_llm(text: str, symbol: str = "") -> dict:
    if os.getenv("USE_LLM_SIGNAL", "false").lower() not in ("1", "true", "yes"):
        return asdict(_neutral())
    if not text.strip():
        return asdict(_neutral())
    try:
        from intel.api_budget import llm_allowed

        if not llm_allowed():
            return asdict(_neutral())
    except Exception:
        pass

    system = (
        "You are a financial news analyst for short-term equity trading (days to weeks). "
        "Your job is to SEPARATE clearly bullish catalysts from bearish risks — do not blur them into one number.\n"
        "BEARISH examples: earnings miss, guidance cut, downgrade, dilution, probe, layoffs, sympathy selloff, "
        "pre-earnings uncertainty with negative tone.\n"
        "BULLISH examples: beat/raise, upgrade, buyback, strong demand, constructive pre-earnings setup.\n"
        "Return strict JSON with keys:\n"
        "sentiment (-1..1 net), confidence (0..1), action_bias (-1..1), horizon_days (0..365), novelty (0..1),\n"
        "good_news_score (0..1 strength of bullish evidence),\n"
        "bad_news_score (0..1 strength of bearish evidence),\n"
        "narrative_polarity (good_news|bad_news|mixed|neutral),\n"
        "block_long (true if bearish evidence dominates near-term reward/risk),\n"
        "key_good_drivers (array of short strings),\n"
        "key_bad_risks (array of short strings),\n"
        "key_thesis (one sentence).\n"
        "If headlines conflict, use mixed with moderate scores on BOTH sides — not neutral zeros."
    )
    user = f"Symbol: {symbol}\nText:\n{text[:8000]}"
    try:
        raw = _post_chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}]
        )
        obj = _extract_json(raw)
        good = _clip(float(obj.get("good_news_score", 0.0)), 0.0, 1.0)
        bad = _clip(float(obj.get("bad_news_score", 0.0)), 0.0, 1.0)
        sent = _clip(float(obj.get("sentiment", good - bad)), -1.0, 1.0)
        narrative = str(obj.get("narrative_polarity") or obj.get("narrative") or "mixed").lower()
        if narrative not in ("good_news", "bad_news", "mixed", "neutral"):
            narrative = "mixed"
        kg = obj.get("key_good_drivers") or []
        kb = obj.get("key_bad_risks") or []
        if not isinstance(kg, list):
            kg = [str(kg)]
        if not isinstance(kb, list):
            kb = [str(kb)]
        out = LLMSignal(
            sentiment=sent,
            confidence=_clip(float(obj.get("confidence", 0.0)), 0.0, 1.0),
            action_bias=_clip(float(obj.get("action_bias", 0.0)), -1.0, 1.0),
            horizon_days=_clip(float(obj.get("horizon_days", 0.0)), 0.0, 365.0),
            novelty=_clip(float(obj.get("novelty", 0.0)), 0.0, 1.0),
            key_thesis=str(obj.get("key_thesis", ""))[:240],
            good_news_score=good,
            bad_news_score=bad,
            narrative_polarity=narrative,
            block_long=bool(obj.get("block_long", False)),
            key_good_drivers=[str(x)[:120] for x in kg[:6]],
            key_bad_risks=[str(x)[:120] for x in kb[:6]],
            generated_at_utc=datetime.now(timezone.utc).isoformat(),
        )
        result = asdict(out)
        try:
            from intel.api_budget import record

            record("llm")
        except Exception:
            pass
        return result
    except Exception as e:
        log.debug("[LLM] score_text fallback: %s", e)
        return asdict(_neutral())


def score_documents_with_llm(symbol: str, docs: list[str]) -> dict:
    if not docs:
        return asdict(_neutral())
    try:
        from intel.api_budget import cache_get, cache_set, llm_allowed, llm_cache_key, record

        key = llm_cache_key(symbol, docs)
        cached = cache_get("llm", key)
        if cached and isinstance(cached, dict):
            return cached
        if not llm_allowed():
            return asdict(_neutral())
    except Exception:
        key = ""
    joined = "\n\n---\n\n".join(docs[:40])
    out = score_text_with_llm(joined, symbol=symbol)
    try:
        from intel.api_budget import cache_set

        if key:
            cache_set("llm", key, out)
    except Exception:
        pass
    return out

