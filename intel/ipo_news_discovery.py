"""Discover IPO / new listing tickers from multiple feeds — NewsAPI optional.

Sources (merged; none remove another):
  1. NewsAPI everything queries (when NEWSAPI_KEY set and not disabled)
  2. Finnhub general news + /calendar/ipo (when FINNHUB_API_KEY / FINNHUB_KEY set)
  3. Nasdaq public IPO calendar HTTP (free)
  4. Yahoo screener short-history heuristic (free fallback)
  5. Alpaca /v2/assets tradable validation (when Alpaca keys set)
  6. Optional Tavily via bottom_fisher

When NEWSAPI_KEY is missing/disabled (or weekend quota window closed elsewhere),
Finnhub calendar + Nasdaq + Yahoo still populate tickers.
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from utils import log

ROOT = Path(__file__).resolve().parents[1]
_CACHE = ROOT / "data" / "ipo_news_discovery_cache.json"

_TICKER_DOLLAR = re.compile(r"\$([A-Z]{1,5})\b")
_TICKER_EXCHANGE = re.compile(
    r"\b(?:NASDAQ|NYSE|AMEX|NYSEARCA)\s*:\s*([A-Z]{1,5})\b", re.I
)
_TICKER_PAREN = re.compile(r"\(([A-Z]{2,5})\)")
_IPO_STRONG = re.compile(
    r"\b(IPO|initial public offering|goes public|going public|public debut|"
    r"direct listing|sets IPO|prices IPO|files? (?:for )?an? IPO|"
    r"SPAC (?:merger|deal)|de-SPAC|begins trading|starts trading on)\b",
    re.I,
)

# Words / private brands / regulators that are never equity tickers for training.
_DENY_TICKERS = frozenset(
    {
        "A",
        "AI",
        "ALL",
        "AM",
        "AN",
        "AND",
        "ANTH",
        "API",
        "ARE",
        "AS",
        "AT",
        "BE",
        "BIG",
        "CEO",
        "CFO",
        "CO",
        "DAY",
        "DO",
        "DRHP",
        "ETF",
        "EU",
        "EV",
        "FDA",
        "FOR",
        "GO",
        "GPT",
        "HAS",
        "HE",
        "HER",
        "HIS",
        "IF",
        "IFSCA",
        "IN",
        "IPO",
        "IQQ",
        "IS",
        "IT",
        "ITS",
        "LLC",
        "LTD",
        "NEW",
        "NO",
        "NOT",
        "NOW",
        "NYSE",
        "OF",
        "ON",
        "OPENAI",
        "OR",
        "OUR",
        "OUT",
        "PASTX",
        "PM",
        "PT",
        "RE",
        "S",
        "SEBI",
        "SEC",
        "SKHYV",
        "SO",
        "SPAC",
        "SPACE",
        "SPACEX",
        "THE",
        "THISX",
        "TO",
        "UDRHP",
        "UK",
        "UP",
        "US",
        "USA",
        "VS",
        "WE",
        "YOY",
        "OPENAI",
        "ANTHROPIC",
    }
)

def _default_queries() -> list[str]:
    raw = os.getenv("IPO_NEWSAPI_QUERIES", "").strip()
    if raw:
        return [q.strip() for q in raw.split("|") if q.strip()]
    return [
        "IPO debut stock ticker symbol",
        "files initial public offering",
        "direct listing begins trading",
        "SPAC merger closes begins trading",
        "company goes public NASDAQ",
        "prices IPO sets range",
        "oversized IPO subscription",
        "tech startup IPO 2025 2026",
    ]


def _newsapi_disabled() -> bool:
    if os.getenv("USE_NEWSAPI", "true").lower() in ("0", "false", "no"):
        return True
    if os.getenv("IPO_USE_NEWSAPI", "true").lower() in ("0", "false", "no"):
        return True
    return not (os.getenv("NEWSAPI_KEY", "") or "").strip()


def _finnhub_key() -> str:
    return (os.getenv("FINNHUB_API_KEY") or os.getenv("FINNHUB_KEY") or "").strip()


def _normalize_ticker(raw: str) -> str | None:
    t = str(raw or "").upper().strip()
    t = t.replace(".", "").replace("-", "")
    if not t or not t.isalpha():
        return None
    if not (2 <= len(t) <= 5):
        return None
    if t in _DENY_TICKERS:
        return None
    # Skip unit/warrant stubs unless explicitly allowed
    if len(t) >= 5 and t.endswith(("U", "W", "R")) and os.getenv(
        "IPO_ALLOW_UNITS", "false"
    ).lower() not in ("1", "true", "yes"):
        return None
    return t


def is_denied_ticker(symbol: str) -> bool:
    t = str(symbol or "").upper().strip()
    return (not t) or t in _DENY_TICKERS or not t.isalpha() or not (2 <= len(t) <= 5)


def _fetch_newsapi_query(query: str, *, page_size: int) -> list[str]:
    key = (os.getenv("NEWSAPI_KEY") or "").strip()
    if not key:
        return []
    try:
        import requests

        r = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": query,
                "language": "en",
                "pageSize": page_size,
                "sortBy": "publishedAt",
                "apiKey": key,
            },
            timeout=float(os.getenv("IPO_NEWS_HTTP_TIMEOUT", "18")),
        )
        if r.status_code == 429:
            log.warning("[IPO_NEWS] NewsAPI 429 — backing off this cycle")
            return []
        r.raise_for_status()
        texts: list[str] = []
        for a in r.json().get("articles") or []:
            if isinstance(a, dict):
                texts.append(
                    f"{a.get('title', '')} {a.get('description', '')} {a.get('content', '')}"
                )
        return texts
    except Exception as e:
        log.debug("[IPO_NEWS] NewsAPI %s: %s", query[:40], e)
        return []


def _fetch_finnhub_market_news(limit: int = 30) -> list[str]:
    key = _finnhub_key()
    if not key or os.getenv("IPO_USE_FINNHUB", "true").lower() in ("0", "false", "no"):
        return []
    try:
        import requests

        r = requests.get(
            "https://finnhub.io/api/v1/news",
            params={"category": "general", "token": key},
            timeout=12,
        )
        if r.status_code == 429:
            return []
        r.raise_for_status()
        out: list[str] = []
        for item in (r.json() or [])[:limit]:
            if isinstance(item, dict):
                out.append(f"{item.get('headline', '')} {item.get('summary', '')}")
        return out
    except Exception as e:
        log.debug("[IPO_NEWS] Finnhub market: %s", e)
        return []


def _fetch_finnhub_ipo_calendar(*, days_back: int = 45, days_fwd: int = 45) -> list[str]:
    """Finnhub /calendar/ipo — primary structured feed when key present."""
    key = _finnhub_key()
    if not key or os.getenv("IPO_USE_FINNHUB_CALENDAR", "true").lower() in (
        "0",
        "false",
        "no",
    ):
        return []
    try:
        import requests

        from_d = (date.today() - timedelta(days=max(7, days_back))).isoformat()
        to_d = (date.today() + timedelta(days=max(7, days_fwd))).isoformat()
        r = requests.get(
            "https://finnhub.io/api/v1/calendar/ipo",
            params={"from": from_d, "to": to_d, "token": key},
            timeout=20,
        )
        if r.status_code == 429:
            log.warning("[IPO_NEWS] Finnhub IPO calendar 429")
            return []
        r.raise_for_status()
        rows = (r.json() or {}).get("ipoCalendar") or []
        out: list[str] = []
        # Prefer priced / expected over filed-only; keep filed as secondary.
        prefer = {"priced", "expected", "withdrawn"}
        for row in rows:
            if not isinstance(row, dict):
                continue
            status = str(row.get("status") or "").lower()
            if status == "withdrawn":
                continue
            sym = _normalize_ticker(row.get("symbol") or "")
            if not sym:
                continue
            if status in prefer or status == "filed" or not status:
                out.append(sym)
        return list(dict.fromkeys(out))
    except Exception as e:
        log.debug("[IPO_NEWS] Finnhub IPO calendar: %s", e)
        return []


def _fetch_nasdaq_ipo_calendar() -> list[str]:
    """Public Nasdaq IPO calendar JSON (no key)."""
    if os.getenv("IPO_USE_NASDAQ", "true").lower() in ("0", "false", "no"):
        return []
    try:
        import requests

        ym = date.today().strftime("%Y-%m")
        urls = [
            f"https://api.nasdaq.com/api/ipo/calendar?date={ym}",
            "https://api.nasdaq.com/api/ipo/calendar",
        ]
        # Also pull prior month for late-priced deals
        prev = (date.today().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        urls.insert(0, f"https://api.nasdaq.com/api/ipo/calendar?date={prev}")
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; FATE_AlgoBot/1.0)",
            "Accept": "application/json",
        }
        out: list[str] = []
        seen_urls: set[str] = set()
        for url in urls:
            if url in seen_urls:
                continue
            seen_urls.add(url)
            try:
                r = requests.get(url, headers=headers, timeout=20)
                if r.status_code != 200:
                    continue
                data = (r.json() or {}).get("data") or {}
                for section in ("priced", "upcoming", "filed"):
                    block = data.get(section) or {}
                    rows = block.get("rows") if isinstance(block, dict) else None
                    if not rows:
                        continue
                    for row in rows:
                        if not isinstance(row, dict):
                            continue
                        sym = _normalize_ticker(row.get("proposedTickerSymbol") or "")
                        if sym:
                            out.append(sym)
            except Exception as e:
                log.debug("[IPO_NEWS] Nasdaq %s: %s", url[-24:], e)
        return list(dict.fromkeys(out))
    except Exception as e:
        log.debug("[IPO_NEWS] Nasdaq calendar: %s", e)
        return []


def _fetch_yahoo_newish_listings(limit: int = 40) -> list[str]:
    """Free Yahoo screener heuristic: short-history names from actives/gainers.

    Not a pure IPO calendar — used only as fallback signal when structured feeds
    are thin. Filters to equities with very short daily history.
    """
    if os.getenv("IPO_USE_YAHOO", "true").lower() in ("0", "false", "no"):
        return []
    max_bars = int(os.getenv("IPO_YAHOO_MAX_HISTORY_BARS", "15"))
    try:
        from yfinance import screen as yf_screen
    except Exception:
        return []

    screens = [
        s.strip()
        for s in os.getenv(
            "IPO_YAHOO_SCREENS", "day_gainers,small_cap_gainers,most_actives"
        ).split(",")
        if s.strip()
    ]
    candidates: list[str] = []
    for name in screens:
        try:
            res = yf_screen(name, count=25)
            quotes = (res or {}).get("quotes") or []
            for q in quotes:
                if not isinstance(q, dict):
                    continue
                if str(q.get("quoteType") or "").upper() not in ("", "EQUITY"):
                    continue
                sym = _normalize_ticker(q.get("symbol") or "")
                if sym:
                    candidates.append(sym)
        except Exception as e:
            log.debug("[IPO_NEWS] Yahoo screen %s: %s", name, e)

    candidates = list(dict.fromkeys(candidates))[: max(limit * 2, 40)]
    if not candidates:
        return []

    out: list[str] = []
    try:
        import yfinance as yf

        for sym in candidates:
            if len(out) >= limit:
                break
            try:
                hist = yf.Ticker(sym).history(period="3mo", auto_adjust=True)
                if hist is None or hist.empty:
                    continue
                if len(hist) <= max_bars:
                    out.append(sym)
            except Exception:
                continue
    except Exception as e:
        log.debug("[IPO_NEWS] Yahoo history filter: %s", e)
    return out


def _alpaca_tradable_set(symbols: list[str]) -> set[str] | None:
    """Return set of Alpaca-tradable symbols among candidates, or None if unavailable."""
    if os.getenv("IPO_USE_ALPACA", "true").lower() in ("0", "false", "no"):
        return None
    key = (os.getenv("ALPACA_API_KEY") or "").strip()
    secret = (os.getenv("ALPACA_SECRET_KEY") or "").strip()
    if not key or not secret:
        return None
    if not symbols:
        return set()
    try:
        import requests

        base = (os.getenv("ALPACA_BASE_URL") or "https://paper-api.alpaca.markets").rstrip(
            "/"
        )
        # Full asset dump once; filter locally (Alpaca has no IPO-date field).
        r = requests.get(
            f"{base}/v2/assets",
            headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret},
            params={"status": "active", "asset_class": "us_equity"},
            timeout=60,
        )
        if r.status_code != 200:
            log.debug("[IPO_NEWS] Alpaca assets HTTP %s", r.status_code)
            return None
        want = {s.upper() for s in symbols}
        tradable: set[str] = set()
        for a in r.json() or []:
            if not isinstance(a, dict):
                continue
            sym = str(a.get("symbol") or "").upper()
            if sym in want and a.get("tradable") and a.get("status") == "active":
                tradable.add(sym)
        return tradable
    except Exception as e:
        log.debug("[IPO_NEWS] Alpaca assets: %s", e)
        return None


def _extract_tickers(text: str, *, require_ipo_context: bool) -> set[str]:
    if require_ipo_context and not _IPO_STRONG.search(text):
        return set()
    found: set[str] = set()
    for pat in (_TICKER_DOLLAR, _TICKER_EXCHANGE, _TICKER_PAREN):
        for m in pat.findall(text):
            t = _normalize_ticker(m)
            if t:
                found.add(t)
    return found


def _extract_company_phrases(text: str) -> list[str]:
    """Heuristic company names near IPO language for yfinance resolve."""
    if not _IPO_STRONG.search(text):
        return []
    names: list[str] = []
    for m in re.finditer(
        r"([A-Z][A-Za-z0-9&\.\-]{2,40}(?:\s+[A-Z][A-Za-z0-9&\.\-]{1,30}){0,4})\s+"
        r"(?:files|prices|sets|plans|targets|announces|completes|prices)?\s*"
        r"(?:its |an |a )?(?:IPO|initial public offering|direct listing|SPAC)",
        text,
    ):
        name = m.group(1).strip()
        if len(name) >= 3 and name.upper() not in _DENY_TICKERS:
            # Skip private megabrands that are not listed tickers
            if name.upper() in ("OPENAI", "ANTHROPIC", "SPACEX"):
                continue
            names.append(name)
    return names


def _source_status() -> dict[str, Any]:
    """Document which keys / free fallbacks are available."""
    news_key = bool((os.getenv("NEWSAPI_KEY") or "").strip())
    fh_key = bool(_finnhub_key())
    alpaca = bool(
        (os.getenv("ALPACA_API_KEY") or "").strip()
        and (os.getenv("ALPACA_SECRET_KEY") or "").strip()
    )
    return {
        "newsapi_key": news_key,
        "newsapi_enabled": news_key and not _newsapi_disabled(),
        "finnhub_key": fh_key,
        "finnhub_calendar": fh_key
        and os.getenv("IPO_USE_FINNHUB_CALENDAR", "true").lower()
        in ("1", "true", "yes"),
        "nasdaq_public": os.getenv("IPO_USE_NASDAQ", "true").lower()
        in ("1", "true", "yes"),
        "yahoo_screener": os.getenv("IPO_USE_YAHOO", "true").lower()
        in ("1", "true", "yes"),
        "alpaca_assets": alpaca
        and os.getenv("IPO_USE_ALPACA", "true").lower() in ("1", "true", "yes"),
        "note": (
            "NEWSAPI_KEY / FINNHUB_KEY optional; Nasdaq + Yahoo are free fallbacks. "
            "NewsAPI is also time-windowed elsewhere in the stack (06:00–10:00 ET weekdays)."
        ),
    }


def discover_from_news(*, max_queries: int | None = None) -> dict:
    """
    Multi-source IPO / listing discovery; return tickers + names + per-source counts.
    Persists last run to data/ipo_news_discovery_cache.json.
    """
    max_q = max_queries or int(os.getenv("IPO_NEWSAPI_MAX_QUERIES", "6"))
    page_size = int(os.getenv("IPO_NEWSAPI_PAGE_SIZE", "15"))
    min_gap = float(os.getenv("IPO_NEWSAPI_QUERY_GAP_SEC", "1.2"))

    tickers: set[str] = set()
    names: list[str] = []
    texts: list[str] = []
    sources: dict[str, list[str]] = {
        "newsapi": [],
        "finnhub_news": [],
        "finnhub_ipo_calendar": [],
        "nasdaq_ipo_calendar": [],
        "yahoo_newish": [],
        "tavily": [],
    }
    status = _source_status()

    if not _newsapi_disabled():
        for q in _default_queries()[:max_q]:
            batch = _fetch_newsapi_query(q, page_size=page_size)
            texts.extend(batch)
            time.sleep(min_gap)
    else:
        log.info(
            "[IPO_NEWS] NewsAPI skipped (no NEWSAPI_KEY or USE_NEWSAPI/IPO_USE_NEWSAPI off) "
            "— using Finnhub/Nasdaq/Yahoo fallbacks"
        )

    fh_news = _fetch_finnhub_market_news()
    texts.extend(fh_news)

    for blob in texts:
        if not _IPO_STRONG.search(blob):
            continue
        found = _extract_tickers(blob, require_ipo_context=False)
        tickers |= found
        if found and blob in fh_news:
            sources["finnhub_news"].extend(sorted(found))
        elif found:
            sources["newsapi"].extend(sorted(found))
        names.extend(_extract_company_phrases(blob))

    fh_cal = _fetch_finnhub_ipo_calendar(
        days_back=int(os.getenv("IPO_FINNHUB_DAYS_BACK", "45")),
        days_fwd=int(os.getenv("IPO_FINNHUB_DAYS_FWD", "45")),
    )
    sources["finnhub_ipo_calendar"] = fh_cal
    tickers |= set(fh_cal)

    nd_cal = _fetch_nasdaq_ipo_calendar()
    sources["nasdaq_ipo_calendar"] = nd_cal
    tickers |= set(nd_cal)

    # Yahoo only if structured calendars are sparse
    if len(tickers) < int(os.getenv("IPO_YAHOO_IF_FEWER_THAN", "8")):
        y_new = _fetch_yahoo_newish_listings(
            limit=int(os.getenv("IPO_YAHOO_LIMIT", "20"))
        )
        sources["yahoo_newish"] = y_new
        tickers |= set(y_new)

    if os.getenv("IPO_USE_TAVILY", "true").lower() in ("1", "true", "yes"):
        try:
            from bottom_fisher.news_radar import discover_news_mentions

            for sym in discover_news_mentions():
                t = _normalize_ticker(sym)
                if t:
                    tickers.add(t)
                    sources["tavily"].append(t)
        except Exception:
            pass

    # Drop megacap AI proxies from discovery tickers (proxy path is separate)
    try:
        from tools.ai_ipo_autopilot import proxy_tickers

        proxies = set(proxy_tickers()) | {
            "MSFT",
            "NVDA",
            "GOOGL",
            "GOOG",
            "AMZN",
            "META",
            "AMD",
            "AVGO",
            "ORCL",
            "AAPL",
            "TSLA",
        }
        tickers -= proxies
    except Exception:
        pass

    # Optional Alpaca tradability filter (keeps non-Alpaca names if Alpaca unavailable).
    # Full /v2/assets dump is expensive — only when explicitly required.
    alpaca_ok = None
    alpaca_filtered = False
    require_alpaca = os.getenv("IPO_REQUIRE_ALPACA_TRADABLE", "false").lower() in (
        "1",
        "true",
        "yes",
    )
    annotate_alpaca = os.getenv("IPO_ALPACA_ANNOTATE", "false").lower() in (
        "1",
        "true",
        "yes",
    )
    if require_alpaca or annotate_alpaca:
        alpaca_ok = _alpaca_tradable_set(sorted(tickers))
    if alpaca_ok is not None and require_alpaca:
        tickers = {t for t in tickers if t in alpaca_ok}
        alpaca_filtered = True
    elif alpaca_ok is not None:
        status["alpaca_tradable_hits"] = sorted(t for t in tickers if t in alpaca_ok)[
            :80
        ]

    # De-dupe source lists
    for k, v in list(sources.items()):
        sources[k] = list(dict.fromkeys(v))

    payload = {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "n_articles": len(texts),
        "tickers": sorted(tickers),
        "company_names": list(dict.fromkeys(names))[:40],
        "queries_used": _default_queries()[:max_q],
        "sources": {k: v for k, v in sources.items() if v},
        "source_counts": {k: len(v) for k, v in sources.items()},
        "status": status,
        "alpaca_filtered": alpaca_filtered,
    }
    _CACHE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _CACHE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, _CACHE)
    log.info(
        "[IPO_NEWS] scan articles=%d tickers=%d names=%d sources=%s",
        len(texts),
        len(tickers),
        len(names),
        {k: len(v) for k, v in sources.items() if v},
    )
    return payload
