"""Symbol-agnostic news search + headline relevance (no per-ticker favor lists in code)."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_AMBIG_PATH = ROOT / "data" / "ambiguous_equity_tickers.txt"
_COMPANY_CACHE = ROOT / "data" / "symbol_company_cache.json"

# English words / short tokens — never treat bare substring as relevance for these.
_AMBIGUOUS_EXTRA = frozenset(
    {
        "A",
        "I",
        "IT",
        "ON",
        "OR",
        "AT",
        "BE",
        "DO",
        "GO",
        "SO",
        "AN",
        "AS",
        "IF",
        "IN",
        "IS",
        "ME",
        "MY",
        "NO",
        "OF",
        "TO",
        "UP",
        "US",
        "WE",
    }
)


def _load_ambiguous_set() -> frozenset[str]:
    out: set[str] = set(_AMBIGUOUS_EXTRA)
    if _AMBIG_PATH.is_file():
        for ln in _AMBIG_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
            ln = ln.split("#", 1)[0].strip().upper()
            if ln and ln.isascii() and ln.replace("-", "").isalnum():
                out.add(ln)
    extra = os.getenv("AMBIGUOUS_TICKERS", "").strip()
    if extra:
        out.update(s.strip().upper() for s in extra.split(",") if s.strip())
    return frozenset(out)


@lru_cache(maxsize=1)
def ambiguous_ticker_set() -> frozenset[str]:
    return _load_ambiguous_set()


def is_ambiguous_ticker(symbol: str) -> bool:
    sym = symbol.strip().upper()
    if len(sym) <= 2:
        return True
    if len(sym) <= 4 and sym in ambiguous_ticker_set():
        return True
    return sym in ambiguous_ticker_set()


def _read_company_cache() -> dict:
    if not _COMPANY_CACHE.is_file():
        return {}
    try:
        return json.loads(_COMPANY_CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_company_cache(doc: dict) -> None:
    _COMPANY_CACHE.parent.mkdir(parents=True, exist_ok=True)
    _COMPANY_CACHE.write_text(json.dumps(doc, indent=0), encoding="utf-8")


def company_name_tokens(symbol: str, *, max_age_hours: float = 168.0) -> list[str]:
    """Company name tokens from yfinance (cached on disk). Same rules for every symbol."""
    sym = symbol.strip().upper()
    cache = _read_company_cache()
    row = cache.get(sym) or {}
    try:
        ts = datetime.fromisoformat(str(row.get("fetched_at", "")).replace("Z", "+00:00"))
        age_h = (datetime.now(timezone.utc) - ts).total_seconds() / 3600.0
        if row.get("tokens") and age_h < max_age_hours:
            return list(row["tokens"])
    except Exception:
        pass

    tokens: list[str] = []
    try:
        import yfinance as yf

        info = yf.Ticker(sym).info or {}
        for key in ("longName", "shortName"):
            name = str(info.get(key) or "").strip()
            if not name:
                continue
            parts = re.findall(r"[A-Za-z][A-Za-z0-9&.-]{2,}", name)
            for p in parts:
                up = p.upper()
                if up == sym or up in ambiguous_ticker_set():
                    continue
                if up not in tokens:
                    tokens.append(up)
    except Exception:
        pass

    cache[sym] = {
        "tokens": tokens[:6],
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_company_cache(cache)
    return tokens


def newsapi_search_query(symbol: str) -> str:
    """Build a NewsAPI query from symbol + company name — no hardcoded per-stock strings."""
    sym = symbol.strip().upper()
    trade_ctx = '(stock OR shares OR earnings OR revenue OR "price target" OR NYSE OR NASDAQ)'

    if is_ambiguous_ticker(sym):
        names = company_name_tokens(sym)
        name_q = " OR ".join(f'"{n}"' for n in names[:3])
        sym_q = f'"${sym}" OR NASDAQ:{sym}'
        core = f"({sym_q}" + (f' OR {name_q}' if name_q else "") + ")"
        return f"{core} AND {trade_ctx}"

    if len(sym) <= 5:
        return f'"{sym}" AND {trade_ctx}'
    return f'"{sym}" AND {trade_ctx}'


def headline_relevant(symbol: str, text: str) -> bool:
    """True when the headline likely refers to this equity (not generic 'meta' noise)."""
    sym = symbol.strip().upper()
    t = text or ""
    if not t.strip():
        return False

    if re.search(rf"\${re.escape(sym)}\b", t, re.I):
        return True
    if re.search(rf"\bNASDAQ:\s*{re.escape(sym)}\b", t, re.I):
        return True
    if re.search(rf"\bNYSE:\s*{re.escape(sym)}\b", t, re.I):
        return True
    if re.search(rf"\({re.escape(sym)}\)", t, re.I):
        return True

    for tok in company_name_tokens(sym):
        if len(tok) >= 4 and re.search(rf"\b{re.escape(tok)}\b", t, re.I):
            return True

    if is_ambiguous_ticker(sym):
        return False

    # Longer / unique tickers: require whole-word ticker mention.
    return bool(re.search(rf"\b{re.escape(sym)}\b", t, re.I))
