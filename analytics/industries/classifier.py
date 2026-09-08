"""Universal industry classifier — all symbols, lifecycle events, spinoffs, IPOs."""

from __future__ import annotations

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

from analytics.industries.base import ClassificationResult, IndustryContext
from analytics.industries.registry import all_handlers, get_handler, get_unclassified_handler
from utils import log

ROOT = Path(__file__).resolve().parents[2]
MAP_PATH = ROOT / "data" / "industry" / "industry_map.json"
OVERRIDES_PATH = ROOT / "data" / "industry" / "symbol_overrides.json"
TICKER_DB_PATH = ROOT / "data" / "industry" / "ticker_database.json"
CLASSIFY_CACHE_PATH = ROOT / "data" / "industry" / "classify_cache.json"

_MEM_MAP: dict[str, dict] | None = None
_MEM_OVERRIDES: dict[str, str] | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save_json(path: Path, doc: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=0), encoding="utf-8")
    os.replace(tmp, path)


def load_overrides() -> dict[str, str]:
    global _MEM_OVERRIDES
    if _MEM_OVERRIDES is not None:
        return _MEM_OVERRIDES
    doc = _load_json(OVERRIDES_PATH, {"symbols": {}})
    syms = doc.get("symbols") or doc
    _MEM_OVERRIDES = {str(k).upper(): str(v).lower() for k, v in syms.items()}
    try:
        from analytics.water_theme import industry_overrides

        _MEM_OVERRIDES.update({k.upper(): v.lower() for k, v in industry_overrides().items()})
    except Exception:
        pass
    return _MEM_OVERRIDES


def load_industry_map() -> dict[str, dict[str, Any]]:
    global _MEM_MAP
    if _MEM_MAP is not None:
        return _MEM_MAP
    doc = _load_json(MAP_PATH, {"symbols": {}})
    _MEM_MAP = {str(k).upper(): v for k, v in (doc.get("symbols") or {}).items() if isinstance(v, dict)}
    return _MEM_MAP


def save_industry_map(symbols: dict[str, dict[str, Any]], *, meta: dict | None = None) -> None:
    global _MEM_MAP
    doc = {
        "version": 2,
        "updated_at_utc": _now(),
        "symbol_count": len(symbols),
        "industry_counts": _count_industries(symbols),
        "symbols": symbols,
    }
    if meta:
        doc["meta"] = meta
    _save_json(MAP_PATH, doc)
    _MEM_MAP = symbols


def _count_industries(symbols: dict[str, dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in symbols.values():
        iid = str(row.get("industry_id") or "unclassified")
        counts[iid] = counts.get(iid, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: -x[1]))


def _canonical_symbol(symbol: str) -> str:
    sym = symbol.strip().upper()
    try:
        from universe_lifecycle.corporate_actions import canonical_symbol

        return canonical_symbol(sym)
    except Exception:
        return sym


def _yf_meta(symbol: str) -> dict[str, Any]:
    try:
        import yfinance as yf

        tk = yf.Ticker(symbol)
        info = tk.info or {}
        return {
            "sector": str(info.get("sector") or ""),
            "industry": str(info.get("industry") or ""),
            "market_cap": float(info.get("marketCap") or 0.0),
            "quote_type": str(info.get("quoteType") or ""),
            "short_name": str(info.get("shortName") or ""),
            "long_name": str(info.get("longName") or ""),
        }
    except Exception:
        return {}


def _load_ticker_database() -> dict[str, dict]:
    doc = _load_json(TICKER_DB_PATH, {"symbols": {}})
    out = {str(k).upper(): v for k, v in (doc.get("symbols") or {}).items()}
    try:
        from analytics.industries.peer_ticker_map import TICKER_INDUSTRY, TICKER_META

        for sym, iid in TICKER_INDUSTRY.items():
            if sym not in out:
                meta = TICKER_META.get(sym, {})
                out[sym] = {
                    "industry_id": iid,
                    "confidence": float(meta.get("confidence") or 0.85),
                    "source": "peer_ticker_map",
                }
    except Exception:
        pass
    return out


def _match_handlers(ctx: IndustryContext) -> ClassificationResult:
    try:
        from analytics.industries.name_lexicon import match_name_lexicon

        lex = match_name_lexicon(ctx.company_name, ctx.sector, ctx.yahoo_industry)
        if lex and lex.confidence >= 0.55:
            return lex
    except Exception:
        pass

    best: ClassificationResult | None = None
    for handler in all_handlers():
        hit = handler.classify(ctx)
        if hit is None:
            continue
        if best is None or hit.confidence > best.confidence:
            best = hit
    if best:
        return best
    try:
        from analytics.industries.sector_fallback import match_sector_fallback

        fb = match_sector_fallback(ctx.sector, ctx.yahoo_industry, ctx.company_name)
        if fb is not None:
            return fb
    except Exception:
        pass
    u = get_unclassified_handler()
    return ClassificationResult(
        industry_id=u.INDUSTRY_ID,
        industry_name=u.INDUSTRY_NAME,
        confidence=0.1,
        etf_proxy=u.ETF_PROXY,
        comovement_mode=u.COMOVEMENT_MODE.value,
        reasons=["no_match"],
    )


def _inherit_from_lifecycle(ctx: IndustryContext) -> str | None:
    """Spinoff / rename lineage — inherit parent industry when configured."""
    parent = ctx.parent_symbol.strip().upper()
    if not parent:
        return None
    parent_row = load_industry_map().get(parent) or {}
    pid = str(parent_row.get("industry_id") or load_overrides().get(parent) or "")
    if not pid:
        return None
    handler = get_handler(pid)
    if handler.inherit_from_parent(pid):
        return pid
    return None


def classify_ticker(
    symbol: str,
    *,
    use_cache: bool = True,
    use_yfinance: bool = True,
    news_headlines: list[str] | None = None,
    parent_symbol: str = "",
    is_spinoff: bool = False,
    is_ipo: bool = False,
) -> dict[str, Any]:
    """Classify one ticker into one of 50 industries with full metadata."""
    from analytics.industries.ai_registry import merge_ai_into_industry_row

    sym = _canonical_symbol(symbol)
    if not sym:
        return {"symbol": symbol, "industry_id": "unclassified", "confidence": 0.0}

    overrides = load_overrides()
    if sym in overrides:
        iid = overrides[sym]
        handler = get_handler(iid)
        row = _row_from_result(sym, ClassificationResult(
            industry_id=iid,
            industry_name=handler.INDUSTRY_NAME,
            confidence=0.98,
            etf_proxy=handler.ETF_PROXY,
            comovement_mode=handler.COMOVEMENT_MODE.value,
            reasons=["manual_override"],
        ), sector="", yahoo_industry="", market_cap=0.0)
        return merge_ai_into_industry_row(sym, row)

    cached = load_industry_map().get(sym)
    if use_cache and cached and cached.get("industry_id") and cached.get("industry_id") != "unclassified":
        if not is_ipo and not is_spinoff:
            return merge_ai_into_industry_row(sym, dict(cached))

    try:
        from analytics.industries.ai_registry import ai_primary_overrides

        ai_ov = ai_primary_overrides()
        if sym in ai_ov:
            iid = ai_ov[sym]
            handler = get_handler(iid)
            row = _row_from_result(
                sym,
                ClassificationResult(
                    industry_id=iid,
                    industry_name=handler.INDUSTRY_NAME,
                    confidence=0.9,
                    etf_proxy=handler.ETF_PROXY,
                    comovement_mode=handler.COMOVEMENT_MODE.value,
                    reasons=["ai_override_module"],
                ),
                sector="",
                yahoo_industry="",
                market_cap=0.0,
            )
            return merge_ai_into_industry_row(sym, row)
    except Exception:
        pass

    ticker_db = _load_ticker_database()
    if sym in ticker_db:
        iid = str(ticker_db[sym].get("industry_id") or "")
        if iid:
            handler = get_handler(iid)
            return merge_ai_into_industry_row(
                sym,
                _row_from_result(
                    sym,
                    ClassificationResult(
                        industry_id=iid,
                        industry_name=handler.INDUSTRY_NAME,
                        confidence=float(ticker_db[sym].get("confidence") or 0.9),
                        etf_proxy=handler.ETF_PROXY,
                        comovement_mode=handler.COMOVEMENT_MODE.value,
                        reasons=["ticker_database"],
                    ),
                    sector=str(ticker_db[sym].get("sector") or ""),
                    yahoo_industry=str(ticker_db[sym].get("yahoo_industry") or ""),
                    market_cap=float(ticker_db[sym].get("market_cap") or 0.0),
                ),
            )

    meta = _yf_meta(sym) if use_yfinance else {}
    if cached:
        for key, ck in (
            ("sector", "sector"),
            ("industry", "yahoo_industry"),
            ("short_name", "short_name"),
            ("long_name", "long_name"),
            ("market_cap", "market_cap"),
        ):
            if not meta.get(key) and cached.get(ck):
                meta[key] = cached.get(ck)
    if str(meta.get("quote_type") or "").upper() in ("ETF", "MUTUALFUND", "INDEX"):
        return {
            "symbol": sym,
            "industry_id": "unclassified",
            "industry_name": "Unclassified",
            "confidence": 0.05,
            "etf_proxy": "SPY",
            "instrument_type": meta.get("quote_type"),
            "tradable_equity": False,
            "classified_at_utc": _now(),
        }

    ctx = IndustryContext(
        symbol=sym,
        sector=str(meta.get("sector") or ""),
        yahoo_industry=str(meta.get("industry") or ""),
        market_cap=float(meta.get("market_cap") or 0.0),
        news_headlines=news_headlines or [],
        parent_symbol=parent_symbol,
        is_spinoff=is_spinoff,
        is_ipo=is_ipo,
        company_name=str(meta.get("long_name") or meta.get("short_name") or ""),
    )

    inherited = _inherit_from_lifecycle(ctx)
    if inherited:
        handler = get_handler(inherited)
        result = ClassificationResult(
            industry_id=inherited,
            industry_name=handler.INDUSTRY_NAME,
            confidence=0.88,
            etf_proxy=handler.ETF_PROXY,
            comovement_mode=handler.COMOVEMENT_MODE.value,
            reasons=["lifecycle_inherit", f"parent:{parent_symbol.upper()}"],
        )
    else:
        result = _match_handlers(ctx)

    return merge_ai_into_industry_row(
        sym,
        _row_from_result(
            sym,
            result,
            sector=ctx.sector,
            yahoo_industry=ctx.yahoo_industry,
            market_cap=ctx.market_cap,
            meta=meta,
        ),
    )


def _finalize_row(sym: str, row: dict[str, Any]) -> dict[str, Any]:
    try:
        from analytics.industries.ai_registry import merge_ai_into_industry_row

        return merge_ai_into_industry_row(sym, row)
    except Exception:
        return row


def _row_from_result(
    sym: str,
    result: ClassificationResult,
    *,
    sector: str = "",
    yahoo_industry: str = "",
    market_cap: float = 0.0,
    meta: dict | None = None,
) -> dict[str, Any]:
    handler = get_handler(result.industry_id)
    row = {
        "symbol": sym,
        "industry_id": result.industry_id,
        "industry_name": result.industry_name,
        "confidence": round(float(result.confidence), 4),
        "etf_proxy": result.etf_proxy,
        "comovement_mode": result.comovement_mode,
        "reasons": result.reasons,
        "sector": sector,
        "yahoo_industry": yahoo_industry,
        "market_cap": market_cap,
        "rate_sensitive": result.industry_id in _rate_set(),
        "nasdaq_heavy": handler.NASDAQ_BETA >= 1.1,
        "classified_at_utc": _now(),
    }
    if meta:
        row["short_name"] = meta.get("short_name", "")
    row.update(handler.to_meta_dict())
    return row


@lru_cache(maxsize=1)
def _rate_set() -> frozenset[str]:
    from analytics.industry_taxonomy import RATE_SENSITIVE

    return RATE_SENSITIVE


def classify_universe(
    symbols: list[str],
    *,
    workers: int | None = None,
    use_yfinance: bool = True,
    persist: bool = True,
    merge_existing: bool = True,
) -> dict[str, dict[str, Any]]:
    """Classify many symbols in parallel; persist to industry_map.json."""
    syms = sorted({_canonical_symbol(s) for s in symbols if s})
    w = workers if workers is not None else int(os.getenv("INDUSTRY_CLASSIFY_WORKERS", "8"))
    out: dict[str, dict] = dict(load_industry_map()) if merge_existing else {}

    def _one(s: str) -> tuple[str, dict]:
        return s, classify_ticker(s, use_cache=False, use_yfinance=use_yfinance)

    done = 0
    with ThreadPoolExecutor(max_workers=max(1, w)) as pool:
        futs = {pool.submit(_one, s): s for s in syms}
        for fut in as_completed(futs):
            sym, row = fut.result()
            out[sym] = row
            done += 1
            if done % 100 == 0:
                log.info("[INDUSTRY] classified %d/%d", done, len(syms))

    if persist:
        save_industry_map(out, meta={"source": "classify_universe", "batch_size": len(syms)})
    return out


def iter_universe_symbols(*, tier: str = "all") -> Iterator[str]:
    """Symbols by tier: all | top50 | top100 trainable pools."""
    tier = (tier or "all").strip().lower()
    seen: set[str] = set()

    def add(s: str) -> None:
        u = _canonical_symbol(s)
        try:
            from fortress_universe import is_tradeable_equity

            if u and is_tradeable_equity(u):
                seen.add(u)
        except Exception:
            if u and re.fullmatch(r"[A-Z0-9.-]{1,6}", u):
                seen.add(u)

    if tier in ("top50", "top50pct", "half"):
        try:
            from fortress_universe import load_top50pct_symbols

            for s in load_top50pct_symbols():
                add(s)
            yield from sorted(seen)
            return
        except Exception:
            pass

    if tier in ("top100", "mega"):
        try:
            from fortress_universe import load_top100_symbols

            for s in load_top100_symbols():
                add(s)
            yield from sorted(seen)
            return
        except Exception:
            pass

    model_dir = ROOT / "models"
    if model_dir.is_dir():
        for p in model_dir.glob("*_model.pkl"):
            add(p.name.replace("_model.pkl", ""))

    snap = ROOT / "data" / "universe" / "universe_snapshot.json"
    doc = _load_json(snap, {})
    for s in doc.get("symbols") or doc.get("tickers") or []:
        add(str(s))

    try:
        from fortress_universe import load_top100_symbols

        for s in load_top100_symbols():
            add(s)
    except Exception:
        pass

    reg = ROOT / "data" / "universe" / "symbol_registry.json"
    rdoc = _load_json(reg, {})
    for s in (rdoc.get("symbols") or rdoc.keys()):
        if isinstance(s, str):
            add(s)

    for s in load_overrides():
        add(s)

    yield from sorted(seen)


def handle_lifecycle_classification(event: dict[str, Any]) -> dict[str, Any] | None:
    """Classify new ticker after spinoff/rename/IPO corporate event."""
    kind = str(event.get("kind") or "")
    new_sym = str(event.get("new") or event.get("symbol") or "").upper()
    old_sym = str(event.get("old") or "").upper()
    if not new_sym:
        return None

    parent = old_sym if kind == "spinoff" else ""
    row = classify_ticker(
        new_sym,
        use_cache=False,
        use_yfinance=True,
        parent_symbol=parent,
        is_spinoff=kind == "spinoff",
        is_ipo=kind in ("ipo", "listing"),
    )
    row["lifecycle_event"] = kind
    row["predecessor"] = old_sym or None

    mp = load_industry_map()
    mp[new_sym] = row
    save_industry_map(mp, meta={"last_lifecycle": event})
    if old_sym and kind in ("rename", "merge"):
        mp.pop(old_sym, None)
        save_industry_map(mp)
    return row


def apply_corporate_events_to_industry_map() -> list[dict]:
    """After corporate_actions detect, classify new tickers."""
    results: list[dict] = []
    try:
        from universe_lifecycle.corporate_actions import load_registry

        reg = load_registry()
        for ev in reg.get("events") or []:
            kind = str(ev.get("kind") or "")
            if kind not in ("rename", "merge", "spinoff", "ipo", "listing"):
                continue
            row = handle_lifecycle_classification(ev)
            if row:
                results.append(row)
    except Exception as e:
        log.debug("[INDUSTRY] lifecycle classify failed: %s", e)
    return results
