"""Shared API quotas + disk cache so news/LLM keys are not burned on repeats or off-hours."""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BUDGET_PATH = ROOT / "data" / "api_budget.json"
CACHE_DIR = ROOT / "data" / "intel_cache"

_DEFAULT_LIMITS = {
    "newsapi": 80,
    "finnhub": 2000,
    "finnhub_earnings": 2500,
    "llm": 400,
    "cramer_llm": 12,
    "industry_llm": 2500,
    "cramer_newsapi": 40,
    "polygon": 120,
    "tavily": 30,
    "alpaca_data": 5000,
}


def _enabled() -> bool:
    return os.getenv("API_BUDGET_ENABLED", "true").lower() in ("1", "true", "yes")


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _load_budget() -> dict:
    if not BUDGET_PATH.is_file():
        return {"date": _today(), "counts": {}}
    try:
        doc = json.loads(BUDGET_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"date": _today(), "counts": {}}
    if doc.get("date") != _today():
        return {"date": _today(), "counts": {}}
    doc.setdefault("counts", {})
    return doc


def _save_budget(doc: dict) -> None:
    BUDGET_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = BUDGET_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=0), encoding="utf-8")
    os.replace(tmp, BUDGET_PATH)


def _limit(provider: str) -> int:
    key = f"API_{provider.upper()}_MAX_PER_DAY"
    env_key = provider.upper() + "_MAX_PER_DAY"
    for k in (key, env_key):
        raw = os.getenv(k, "").strip()
        if raw.isdigit():
            return int(raw)
    return int(_DEFAULT_LIMITS.get(provider, 9999))


def allow(provider: str, *, n: int = 1) -> bool:
    if not _enabled():
        return True
    doc = _load_budget()
    used = int(doc["counts"].get(provider, 0))
    return used + n <= _limit(provider)


def record(provider: str, *, n: int = 1) -> None:
    if not _enabled():
        return
    doc = _load_budget()
    doc["counts"][provider] = int(doc["counts"].get(provider, 0)) + n
    _save_budget(doc)


def usage_summary() -> dict:
    doc = _load_budget()
    out = {"date": doc.get("date"), "providers": {}}
    for p, lim in _DEFAULT_LIMITS.items():
        used = int(doc.get("counts", {}).get(p, 0))
        out["providers"][p] = {"used": used, "limit": _limit(p)}
    return out


def _cache_path(category: str, key: str) -> Path:
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
    return CACHE_DIR / category / f"{h}.json"


def cache_get(category: str, key: str) -> Any | None:
    if os.getenv("INTEL_CACHE_ENABLED", "true").lower() not in ("1", "true", "yes"):
        return None
    p = _cache_path(category, key)
    if not p.is_file():
        return None
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    ttl = float(doc.get("ttl_sec", 3600))
    if time.time() - float(doc.get("ts", 0)) > ttl:
        return None
    return doc.get("payload")


def cache_set(category: str, key: str, payload: Any, *, ttl_sec: float | None = None) -> None:
    if os.getenv("INTEL_CACHE_ENABLED", "true").lower() not in ("1", "true", "yes"):
        return
    if ttl_sec is None:
        ttl_sec = float(os.getenv(f"INTEL_CACHE_{category.upper()}_TTL_SEC", "3600"))
    p = _cache_path(category, key)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(
        json.dumps({"ts": time.time(), "ttl_sec": ttl_sec, "payload": payload}, indent=0),
        encoding="utf-8",
    )
    os.replace(tmp, p)


def should_skip_newsapi(finnhub_headline_count: int) -> bool:
    try:
        from intel.api_coverage import should_skip_newsapi as _cov

        return _cov(finnhub_headline_count)
    except Exception:
        if os.getenv("USE_NEWSAPI", "true").lower() in ("0", "false", "no"):
            return True
        if not allow("newsapi"):
            return True
        min_fh = int(os.getenv("NEWSAPI_SKIP_IF_FINNHUB_HEADLINES", "8"))
        return finnhub_headline_count >= min_fh


def should_skip_cramer_newsapi() -> bool:
    try:
        from intel.api_coverage import should_skip_cramer_newsapi as _cov

        return _cov()
    except Exception:
        if os.getenv("USE_CRAMER_SIGNAL", "true").lower() not in ("1", "true", "yes"):
            return True
        return not allow("cramer_newsapi")


def llm_allowed(*, force: bool = False) -> bool:
    if os.getenv("USE_LLM_SIGNAL", "false").lower() not in ("1", "true", "yes"):
        return False
    if force:
        return allow("llm")
    try:
        from intel.api_coverage import allow_provider

        ok, _ = allow_provider("llm")
        return ok and allow("llm")
    except Exception:
        pass
    if os.getenv("LLM_ONLY_DURING_SESSION", "true").lower() in ("1", "true", "yes"):
        try:
            from analytics.market_session import orders_allowed

            if not orders_allowed("any")[0]:
                return False
        except Exception:
            pass
    return allow("llm")


def llm_cache_key(symbol: str, docs: list[str]) -> str:
    sym = symbol.strip().upper()
    sample = "|".join((d or "")[:120] for d in docs[:5])
    return f"{sym}:{hashlib.sha256(sample.encode()).hexdigest()[:16]}"
