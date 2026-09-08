"""Per-provider coverage rules — max intel from each API key without waste.

True API day starts 06:00 ET (pre-market intel). Orders still follow TRADE_START_ET / RTH.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, time
from typing import Any

from analytics.market_session import (
    _parse_et_time,
    intel_window_open,
    is_trading_day,
    now_et,
)

_TICKER_IN_TEXT = re.compile(r"\b[A-Z]{1,5}\b")


def _et_time(name: str, default: str) -> time:
    return _parse_et_time(os.getenv(name, default).strip()) or _parse_et_time(default) or time(6, 0)


def newsapi_window_open(dt: datetime | None = None) -> tuple[bool, str]:
    """NewsAPI only 06:00–10:00 ET — overnight headline burst, save daily quota."""
    dt = dt or now_et()
    if not is_trading_day(dt):
        return False, "weekend"
    start = _et_time("NEWSAPI_ACTIVE_START_ET", "06:00")
    end = _et_time("NEWSAPI_ACTIVE_END_ET", "10:00")
    t = dt.time()
    if t < start or t >= end:
        return False, f"outside {start.strftime('%H:%M')}-{end.strftime('%H:%M')} ET"
    return True, "newsapi_active"


def provider_strategy(provider: str) -> str:
    """Human-readable loophole / coverage note per provider."""
    notes = {
        "finnhub": (
            "1 call /news-sentiment per ticker (cached 2h); skip company-news if sentiment fresh; "
            "1 /news?category=general batch shared across watchlist at 6 AM"
        ),
        "newsapi": "Only 06:00–10:00 ET; skip if Finnhub ≥8 headlines; shared morning query cache",
        "cramer_newsapi": "Skip when CRAMER.jsonl replay has recent mentions (free local)",
        "llm": "Allowed 06:00–20:00 ET intel window; 1 batched morning call for playbook; per-ticker cache 1h",
        "polygon": "Batch snapshot up to 50 tickers per request; 5 min cache during prep",
        "alpaca_data": "Read-only quotes/bars free in intel window — warm prices before RTH",
        "tavily": "AI pick review only; capped daily; skip if Finnhub+LLM already strong",
        "fred": "Macro series cached 6h — no live pull during scans",
    }
    return notes.get(provider, "standard budget + cache")


def allow_provider(provider: str, *, context: str = "") -> tuple[bool, str]:
    """Gate a provider call using window + budget rules."""
    from intel.api_budget import allow

    p = provider.strip().lower()
    ctx = (context or "").strip().lower()

    if p == "newsapi" or p == "cramer_newsapi":
        ok, reason = newsapi_window_open()
        if not ok:
            return False, reason
    elif p == "llm":
        if os.getenv("LLM_INTEL_FROM_PREMARKET", "true").lower() in ("1", "true", "yes"):
            ok, reason = intel_window_open()
            if not ok:
                return False, reason
        else:
            try:
                from analytics.market_session import orders_allowed

                if not orders_allowed("any")[0]:
                    return False, "outside order session"
            except Exception:
                pass
    elif p in ("finnhub", "polygon", "alpaca_data"):
        ok, reason = intel_window_open()
        if not ok and p != "finnhub":
            return False, reason
        # Finnhub: allow off-window for earnings + cached sentiment reads
        if p == "finnhub" and not ok and ctx not in ("cache_hit", "earnings_calendar"):
            return False, reason
    elif p == "tavily":
        ok, reason = intel_window_open()
        if not ok:
            return False, reason
        if ctx not in ("ai_pick", "morning", ""):
            return False, "tavily ai_pick only"

    if not allow(p if p in ("newsapi", "finnhub", "llm", "cramer_newsapi", "polygon", "tavily", "alpaca_data") else p):
        return False, f"{p} daily cap reached"
    return True, "ok"


def should_skip_newsapi(finnhub_headline_count: int) -> bool:
    ok, _ = newsapi_window_open()
    if not ok:
        return True
    if os.getenv("USE_NEWSAPI", "true").lower() in ("0", "false", "no"):
        return True
    from intel.api_budget import allow

    if not allow("newsapi"):
        return True
    min_fh = int(os.getenv("NEWSAPI_SKIP_IF_FINNHUB_HEADLINES", "8"))
    return finnhub_headline_count >= min_fh


def should_skip_cramer_newsapi() -> bool:
    if os.getenv("CRAMER_REPLAY_BEFORE_NEWSAPI", "true").lower() in ("1", "true", "yes"):
        try:
            from intel.cramer_picks import _load_entries

            if _load_entries():
                return True
        except Exception:
            pass
    if os.getenv("USE_CRAMER_SIGNAL", "true").lower() not in ("1", "true", "yes"):
        return True
    from intel.api_budget import allow

    return not allow("cramer_newsapi")


def cramer_headlines_from_replay(symbol: str, *, limit: int = 8) -> list[str]:
    """Synthetic headline lines from local CRAMER.jsonl — zero NewsAPI cost."""
    try:
        from intel.cramer_picks import score_symbol_from_cramer

        row = score_symbol_from_cramer(symbol)
        if int(row.get("mentions") or 0) <= 0:
            return []
        sym = symbol.strip().upper()
        bias = "bullish" if float(row.get("final_factor") or 0) >= 0 else "bearish"
        lines = [
            f"Cramer replay {sym} {bias} mentions={row.get('mentions')} "
            f"strong_buy={row.get('strong_buy_mentions', 0)} last={row.get('last_date', '')}"
        ]
        if row.get("high_conviction_buy"):
            lines.append(f"Cramer high conviction buy {sym} table-pound signal")
        return lines[:limit]
    except Exception:
        return []


def match_symbols_in_texts(texts: list[str], symbols: set[str]) -> dict[str, list[str]]:
    """Map general-news headlines to tickers by symbol token match."""
    out: dict[str, list[str]] = {s: [] for s in symbols}
    for raw in texts:
        t = (raw or "").strip()
        if not t:
            continue
        found = {m.group(0) for m in _TICKER_IN_TEXT.finditer(t.upper())}
        for sym in found & symbols:
            if len(out[sym]) < 25:
                out[sym].append(t[:280])
    return out


def coverage_report() -> dict[str, Any]:
    intel_ok, intel_r = intel_window_open()
    news_ok, news_r = newsapi_window_open()
    from intel.api_budget import usage_summary

    return {
        "intel_window": {"open": intel_ok, "reason": intel_r},
        "newsapi_window": {"open": news_ok, "reason": news_r},
        "intel_start_et": os.getenv("INTEL_WINDOW_START_ET", "06:00"),
        "auto_unpause_et": os.getenv("AUTO_UNPAUSE_ET", "06:00"),
        "budget": usage_summary(),
        "strategies": {p: provider_strategy(p) for p in (
            "finnhub", "newsapi", "cramer_newsapi", "llm", "polygon", "alpaca_data", "tavily", "fred"
        )},
    }
