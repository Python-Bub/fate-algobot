"""LLM + web-search industry classifier — multi-industry, weekly refresh."""

from __future__ import annotations

import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path
from typing import Any

from utils import log

ROOT = Path(__file__).resolve().parents[1]
LLM_CACHE_DIR = ROOT / "data" / "industry" / "llm_batch_cache"

INDUSTRY_CLASSIFIER_PROMPT = """You are an expert equity industry analyst for a quantitative trading system.
Classify US equities into one or more of exactly these industry buckets.
Return STRICT JSON only.

Rules:
- primary industry = largest revenue / market perception TODAY (not legacy branding)
- add secondary industries when the company genuinely spans buckets (Amazon, Tesla, Berkshire, JNJ, GE)
- industry weights MUST sum to 1.0 across all entries (primary gets largest share)
- use "unclassified" ONLY when truly impossible to determine after reading context
- consider business segments, recent M&A, spinoffs, and news — not ticker letters
- REITs: pick the specific REIT bucket (residential/office/retail/industrial/specialized)
- Banks: regional vs diversified vs consumer finance vs exchanges
- Tech: distinguish semiconductors vs semi equipment vs software vs hardware vs interactive media
- Energy: integrated vs E&P vs equipment vs utilities vs renewables
- be decisive — confidence >= 0.75 when sector/industry or search evidence is clear

Single symbol schema:
{
  "symbol": "TICKER",
  "company_name": "string",
  "industries": [
    {"industry_id": "semiconductors", "weight": 0.7, "role": "primary", "rationale": "..."},
    {"industry_id": "auto_manufacturers", "weight": 0.3, "role": "secondary", "rationale": "..."}
  ],
  "confidence": 0.0-1.0,
  "business_summary": "one sentence",
  "tags": ["ai", "cloud", "ev"],
  "review_in_days": 7
}

Batch schema (when classifying multiple tickers):
{
  "classifications": [ { ...single symbol objects... } ]
}
"""


@lru_cache(maxsize=1)
def _industry_catalog_blurb() -> str:
    """Compact handler catalog for LLM disambiguation."""
    try:
        from analytics.industries.handlers import ALL_HANDLERS

        lines: list[str] = []
        for iid, h in sorted(ALL_HANDLERS.items()):
            if iid == "unclassified":
                continue
            pats = ", ".join(list(h.YAHOO_PATTERNS)[:3]) if h.YAHOO_PATTERNS else ""
            lines.append(
                f"- {iid}: {h.INDUSTRY_NAME} | mode={h.COMOVEMENT_MODE.value} | etf={h.ETF_PROXY}"
                + (f" | patterns={pats}" if pats else "")
            )
        return "\n".join(lines[:55])
    except Exception:
        from analytics.industry_taxonomy import all_industry_ids

        return ", ".join(all_industry_ids())


def _neural_first() -> bool:
    return os.getenv("USE_INDUSTRY_NEURAL_FIRST", "true").lower() in ("1", "true", "yes")


def _llm_cache_get(key: str) -> dict | None:
    if os.getenv("INDUSTRY_AI_LLM_CACHE", "true").lower() not in ("1", "true", "yes"):
        return None
    p = LLM_CACHE_DIR / f"{key}.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _llm_cache_put(key: str, batch: dict[str, dict]) -> None:
    if os.getenv("INDUSTRY_AI_LLM_CACHE", "true").lower() not in ("1", "true", "yes"):
        return
    LLM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    p = LLM_CACHE_DIR / f"{key}.json"
    p.write_text(json.dumps(batch, default=str), encoding="utf-8")


def _batch_cache_key(symbols: list[str], user_blob: str) -> str:
    raw = "|".join(sorted(symbols)) + "|" + user_blob[:8000]
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _classify_neural_fallback(symbol: str, *, persist: bool = True) -> dict[str, Any]:
    from analytics.industries.neural_classifier import classify_symbol_neural

    return classify_symbol_neural(symbol, persist=persist)


def _industry_id_list() -> list[str]:
    from analytics.industry_taxonomy import all_industry_ids

    return all_industry_ids()


def _llm_enabled() -> bool:
    if os.getenv("USE_INDUSTRY_AI", "true").lower() not in ("1", "true", "yes"):
        return False
    key = (os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
    return bool(key)


def _industry_llm_allowed(*, n: int = 1) -> bool:
    """Industry training uses separate quota — does not require USE_LLM_SIGNAL."""
    if not _llm_enabled():
        return False
    if os.getenv("INDUSTRY_AI_IGNORE_BUDGET", "false").lower() in ("1", "true", "yes"):
        return True
    try:
        from intel.api_budget import allow

        if allow("industry_llm", n=n):
            return True
        return allow("llm", n=n)
    except Exception:
        return True


def _record_industry_llm(*, n: int = 1) -> None:
    try:
        from intel.api_budget import allow, record

        if allow("industry_llm", n=n):
            record("industry_llm", n=n)
        else:
            record("llm", n=n)
    except Exception:
        pass


def _search_enabled() -> bool:
    if os.getenv("INDUSTRY_AI_USE_SEARCH", "true").lower() not in ("1", "true", "yes"):
        return False
    return bool(os.getenv("TAVILY_API_KEY", "").strip())


def fetch_company_context(symbol: str, *, company_name: str = "") -> dict[str, Any]:
    """Gather yfinance meta + optional Tavily web snippets for classification."""
    sym = symbol.strip().upper()
    ctx: dict[str, Any] = {"symbol": sym, "snippets": [], "sources": []}

    try:
        import yfinance as yf

        info = yf.Ticker(sym).info or {}
        ctx.update(
            {
                "sector": str(info.get("sector") or ""),
                "industry": str(info.get("industry") or ""),
                "short_name": str(info.get("shortName") or company_name or ""),
                "long_name": str(info.get("longName") or ""),
                "summary": str(info.get("longBusinessSummary") or "")[:1200],
                "market_cap": info.get("marketCap"),
                "website": str(info.get("website") or ""),
            }
        )
    except Exception as e:
        log.debug("[INDUSTRY_AI] yfinance ctx skipped %s: %s", sym, e)

    if _search_enabled():
        try:
            from intel.ai_final_pick_review import fetch_tavily_snippet

            name = ctx.get("short_name") or ctx.get("long_name") or sym
            queries = (
                f"{name} {sym} company business segments revenue mix 2025 2026",
                f"{sym} stock industry sector GICS business description",
                f"{sym} {name} what does the company do products services",
                f"{sym} investor relations business overview segments",
            )
            char_lim = int(os.getenv("INDUSTRY_AI_TAVILY_CHARS", "1600"))
            for q in queries[: int(os.getenv("INDUSTRY_AI_SEARCH_QUERIES", "4"))]:
                snip = fetch_tavily_snippet(q, max_chars=char_lim)
                if snip and snip not in ctx["snippets"]:
                    ctx["snippets"].append(snip[:char_lim])
                    ctx["sources"].append("tavily")
        except Exception as e:
            log.debug("[INDUSTRY_AI] tavily skipped %s: %s", sym, e)

    try:
        if os.getenv("INDUSTRY_AI_USE_NEWS_INTEL", "false").lower() in ("1", "true", "yes"):
            from sentiment_pipeline import get_symbol_news_intel

            intel = get_symbol_news_intel(sym)
            headlines: list[str] = []
            for key in ("top_bullish", "top_bearish", "key_good", "key_bad"):
                headlines.extend(intel.get(key) or [])
            if headlines:
                ctx["news_headlines"] = list(dict.fromkeys(str(h) for h in headlines if h))[:12]
                ctx["sources"].append("news_intel")
    except Exception:
        pass

    return ctx


def _extract_json(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("{") and text.endswith("}"):
        return json.loads(text)
    i = text.find("{")
    j = text.rfind("}")
    if i >= 0 and j > i:
        return json.loads(text[i : j + 1])
    return {}


def _post_chat(messages: list[dict]) -> str:
    from intel.llm_signal_agent import _post_chat as _pc

    retries = int(os.getenv("INDUSTRY_AI_LLM_RETRIES", "4"))
    for attempt in range(retries):
        try:
            return _pc(messages)
        except Exception as e:
            err = str(e)
            if attempt < retries - 1 and ("429" in err or "timeout" in err.lower()):
                wait = float(os.getenv("INDUSTRY_AI_RETRY_WAIT", "8")) * (attempt + 1)
                log.warning("[INDUSTRY_AI] LLM retry %d/%d in %.0fs: %s", attempt + 1, retries, wait, err[:80])
                time.sleep(wait)
                continue
            raise


def _system_prompt() -> str:
    catalog = _industry_catalog_blurb()
    ids = _industry_id_list()
    return (
        INDUSTRY_CLASSIFIER_PROMPT
        + "\n\nIndustry catalog:\n"
        + catalog
        + "\n\nAllowed industry_id values:\n"
        + ", ".join(ids)
    )


def _parse_batch_response(raw: str, symbols: list[str]) -> dict[str, dict[str, Any]]:
    parsed = _extract_json(raw)
    out: dict[str, dict] = {}
    rows = parsed.get("classifications") or parsed.get("results") or []
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict) and row.get("symbol"):
                out[str(row["symbol"]).upper()] = row
    if not out and parsed.get("symbol"):
        out[str(parsed["symbol"]).upper()] = parsed
    # Ensure every requested symbol has an entry
    for s in symbols:
        su = s.upper()
        if su not in out:
            out[su] = {"symbol": su, "error": "missing_from_batch"}
    return out


def classify_symbols_batch_llm(
    symbols: list[str],
    contexts: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Classify up to N symbols in one LLM call (cached; neural fallback on 429)."""
    syms = [s.strip().upper() for s in symbols if s]
    if not syms:
        return {}

    if _neural_first() or not _llm_enabled():
        return {s: _classify_neural_fallback(s, persist=False) for s in syms}

    if not _industry_llm_allowed():
        return {s: _classify_neural_fallback(s, persist=False) for s in syms}

    ctx_map = contexts or {}
    payload_rows = []
    for s in syms:
        ctx = ctx_map.get(s) or fetch_company_context(s)
        payload_rows.append({"symbol": s, "context": ctx})

    user_blob = json.dumps({"tickers": payload_rows}, default=str)
    cache_key = _batch_cache_key(syms, user_blob)
    model = os.getenv("INDUSTRY_AI_MODEL", os.getenv("LLM_MODEL", "gpt-4o-mini"))
    elapsed_ms = 0

    cached = _llm_cache_get(cache_key)
    if cached:
        batch = dict(cached)
    else:
        messages = [
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": user_blob},
        ]
        t0 = time.perf_counter()
        try:
            raw = _post_chat(messages)
            batch = _parse_batch_response(raw, syms)
            _record_industry_llm(n=1)
            _llm_cache_put(cache_key, batch)
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
        except Exception as e:
            log.warning("[INDUSTRY_AI] batch LLM failed (%d syms): %s — neural fallback", len(syms), e)
            batch = {s: _classify_neural_fallback(s, persist=False) for s in syms}
            if not any(b.get("industries") for b in batch.values()):
                return {s: {"symbol": s, "error": str(e)} for s in syms}

    for s in syms:
        hit = batch.get(s, {"symbol": s, "error": "missing"})
        hit["symbol"] = s
        hit["model"] = hit.get("model") or model
        hit["elapsed_ms"] = hit.get("elapsed_ms") or elapsed_ms
        ctx = ctx_map.get(s) or {}
        hit["search_used"] = bool(ctx.get("snippets")) or hit.get("search_used")
        hit["search_evidence"] = hit.get("search_evidence") or ctx.get("snippets") or []
        batch[s] = hit
    return batch


def _fetch_contexts_parallel(symbols: list[str], workers: int | None = None) -> dict[str, dict]:
    w = workers if workers is not None else int(os.getenv("INDUSTRY_AI_CONTEXT_WORKERS", "6"))
    out: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=max(1, w)) as pool:
        futs = {pool.submit(fetch_company_context, s): s for s in symbols}
        for fut in as_completed(futs):
            sym = futs[fut]
            try:
                out[sym.upper()] = fut.result()
            except Exception as e:
                out[sym.upper()] = {"symbol": sym.upper(), "error": str(e)}
    return out


def classify_symbol_with_ai(
    symbol: str,
    *,
    company_name: str = "",
    extra_context: str = "",
    force_search: bool = False,
) -> dict[str, Any]:
    """Classify one ticker via LLM; returns parsed dict or empty on failure."""
    sym = symbol.strip().upper()
    if not _llm_enabled():
        return {"symbol": sym, "skipped": True, "reason": "llm_disabled"}

    try:
        from intel.api_budget import llm_allowed

        if not _industry_llm_allowed():
            return {"symbol": sym, "skipped": True, "reason": "llm_budget"}
    except Exception:
        if not _industry_llm_allowed():
            return {"symbol": sym, "skipped": True, "reason": "llm_budget"}

    ctx = fetch_company_context(sym, company_name=company_name)
    if force_search and not ctx.get("snippets") and _search_enabled():
        ctx = fetch_company_context(sym, company_name=company_name)

    ids = _industry_id_list()
    user_blob = json.dumps(
        {
            "symbol": sym,
            "context": ctx,
            "allowed_industry_ids": ids,
            "extra": extra_context[:800],
        },
        default=str,
    )

    messages = [
        {"role": "system", "content": _system_prompt()},
        {"role": "user", "content": user_blob},
    ]

    model = os.getenv("INDUSTRY_AI_MODEL", os.getenv("LLM_MODEL", "gpt-4o-mini"))
    t0 = time.perf_counter()
    try:
        raw = _post_chat(messages)
        parsed = _extract_json(raw)
        _record_industry_llm()
    except Exception as e:
        log.warning("[INDUSTRY_AI] LLM failed %s: %s", sym, e)
        return {"symbol": sym, "error": str(e)}

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    if not parsed.get("industries"):
        return {"symbol": sym, "error": "empty_industries", "raw": raw[:400]}

    parsed["symbol"] = sym
    parsed["model"] = model
    parsed["elapsed_ms"] = elapsed_ms
    parsed["search_used"] = bool(ctx.get("snippets"))
    parsed["search_evidence"] = ctx.get("snippets") or []
    return parsed


def classify_batch_with_ai(
    symbols: list[str],
    *,
    persist: bool = True,
    sleep_sec: float | None = None,
    use_mega_batch: bool | None = None,
) -> list[dict[str, Any]]:
    """Classify many symbols; persists into ai_registry when persist=True."""
    from analytics.industries.ai_registry import upsert_ai_classification

    pause = sleep_sec if sleep_sec is not None else float(os.getenv("INDUSTRY_AI_SLEEP_SEC", "0.25"))
    mega = use_mega_batch
    if mega is None:
        mega = int(os.getenv("INDUSTRY_AI_MEGA_BATCH", "24")) > 1
    batch_size = int(os.getenv("INDUSTRY_AI_MEGA_BATCH", "24"))
    verify_thr = float(os.getenv("INDUSTRY_AI_VERIFY_BELOW", "0.72"))
    results: list[dict[str, Any]] = []

    syms = [s.strip().upper() for s in symbols if s]
    if not syms:
        return results

    def _persist_hit(s: str, hit: dict[str, Any]) -> dict[str, Any]:
        if hit.get("skipped") or hit.get("error") or not hit.get("industries"):
            return hit
        row = upsert_ai_classification(
            s,
            industries=hit.get("industries") or [],
            source=str(hit.get("model") or "ai_llm_search" if hit.get("search_used") else "ai_llm"),
            confidence=float(hit.get("confidence") or 0.75),
            search_evidence=hit.get("search_evidence"),
            model=str(hit.get("model") or ""),
            persist=persist,
        )
        hit["registry_row"] = row
        log.info(
            "[INDUSTRY_AI] %s primary=%s conf=%.2f inds=%d search=%s",
            s,
            row.get("primary_industry_id"),
            float(row.get("confidence") or 0),
            len(row.get("industries") or []),
            hit.get("search_used"),
        )
        return hit

    if mega and batch_size > 1:
        for i in range(0, len(syms), batch_size):
            chunk = syms[i : i + batch_size]
            ctx_map = _fetch_contexts_parallel(chunk)
            batch_hits = classify_symbols_batch_llm(chunk, ctx_map)
            retry: list[str] = []
            for s in chunk:
                hit = batch_hits.get(s, {"symbol": s, "error": "missing"})
                conf = float(hit.get("confidence") or 0.0)
                if hit.get("error") or not hit.get("industries"):
                    retry.append(s)
                    results.append(hit)
                    continue
                if conf < verify_thr:
                    retry.append(s)
                hit = _persist_hit(s, hit)
                results.append(hit)
            # Failures / low confidence → neural (no extra OpenAI calls)
            for s in retry:
                neural = _classify_neural_fallback(s, persist=persist)
                if neural.get("industries"):
                    neural = _persist_hit(s, neural)
                else:
                    neural = classify_symbol_with_ai(s, force_search=True)
                    if neural.get("industries"):
                        neural = _persist_hit(s, neural)
                results.append(neural)
                time.sleep(pause * 0.25)
            time.sleep(pause)
        return results

    for sym in syms:
        hit = classify_symbol_with_ai(sym)
        if hit.get("skipped") or hit.get("error"):
            results.append(hit)
            time.sleep(pause)
            continue
        conf = float(hit.get("confidence") or 0.0)
        if conf < verify_thr:
            hit = classify_symbol_with_ai(sym, force_search=True)
        hit = _persist_hit(sym, hit)
        results.append(hit)
        time.sleep(pause)

    return results


def apply_ai_to_industry_map(symbols: list[str] | None = None) -> int:
    """Merge AI registry into industry_map.json for given symbols (or all AI entries)."""
    from analytics.industries.ai_registry import load_ai_registry, merge_ai_into_industry_row
    from analytics.industries.classifier import load_industry_map, save_industry_map

    reg = load_ai_registry()
    syms = [s.strip().upper() for s in (symbols or list(reg.keys())) if s]
    mp = load_industry_map()
    updated = 0
    for sym in syms:
        if sym not in reg:
            continue
        base = mp.get(sym) or {"symbol": sym, "industry_id": "unclassified", "confidence": 0.1}
        merged = merge_ai_into_industry_row(sym, base)
        if merged != base:
            mp[sym] = merged
            updated += 1
    if updated:
        save_industry_map(mp, meta={"source": "ai_merge", "updated": updated})
    return updated
