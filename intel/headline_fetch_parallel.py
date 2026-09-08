"""Parallel headline fetch (Phase 1 async I/O without adding aiohttp dependency).

Uses ThreadPoolExecutor to overlap Finnhub + NewsAPI + Cramer requests per symbol.
Enable with USE_PARALLEL_NEWS_FETCH=true (default true).
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

from sentiment_pipeline import fetch_cramer_mentions, fetch_finnhub_headlines, fetch_newsapi_headlines


def fetch_headline_groups_parallel(
    symbol: str,
    finnhub_limit: int = 30,
    news_limit: int = 30,
    cramer_limit: int = 12,
    *,
    as_of: str | None = None,
) -> tuple[list[str], list[str], list[str]]:
    """Return (finnhub, newsapi, cramer) headline texts with parallel HTTP where enabled.

    Hist ``as_of`` uses dated Finnhub only — NewsAPI/Cramer strings have no
    reliable timestamps, so they are omitted to fail closed vs look-ahead.
    """
    from intel.point_in_time import parse_as_of

    sym = symbol.strip().upper()
    hist = parse_as_of(as_of) is not None
    cache_key = f"{sym}:{finnhub_limit}:{news_limit}:{cramer_limit}:{as_of or 'live'}"
    try:
        from intel.api_budget import cache_get, cache_set

        cached = cache_get("headlines", cache_key)
        if cached and isinstance(cached, list) and len(cached) == 3:
            a, b, c = list(cached[0]), list(cached[1]), list(cached[2])
            if a or b or c:
                if not hist and not b:
                    fill = _free_headline_fill(sym, max(news_limit, 12))
                    if fill:
                        b = list(dict.fromkeys(list(b) + fill))
                return a, b, c
    except Exception:
        pass

    if hist:
        a = fetch_finnhub_headlines(sym, limit=finnhub_limit, as_of=as_of)
        b, c = [], []
    elif os.getenv("USE_PARALLEL_NEWS_FETCH", "true").lower() not in ("1", "true", "yes"):
        a, b, c = _fetch_groups_sequential(sym, finnhub_limit, news_limit, cramer_limit)
    else:
        a, b, c = _fetch_groups_parallel(sym, finnhub_limit, news_limit, cramer_limit)

    if not hist and not a and not b:
        fill = _free_headline_fill(sym, max(news_limit, 12))
        if fill:
            b = list(dict.fromkeys(list(b) + fill))

    try:
        from intel.api_budget import cache_set

        cache_set("headlines", cache_key, [a, b, c])
    except Exception:
        pass
    return a, b, c


def _fetch_groups_sequential(
    sym: str, finnhub_limit: int, news_limit: int, cramer_limit: int
) -> tuple[list[str], list[str], list[str]]:
    from intel.api_budget import allow, record, should_skip_cramer_newsapi, should_skip_newsapi

    a = fetch_finnhub_headlines(sym, limit=finnhub_limit)
    if a and allow("finnhub"):
        record("finnhub")
    b: list[str] = []
    if not should_skip_newsapi(len(a)):
        b = fetch_newsapi_headlines(sym, limit=news_limit)
        if b and allow("newsapi"):
            record("newsapi")
    c: list[str] = []
    if not should_skip_cramer_newsapi():
        c = fetch_cramer_mentions(sym, limit=cramer_limit)
        if c and allow("cramer_newsapi"):
            record("cramer_newsapi")
    else:
        try:
            from intel.api_coverage import cramer_headlines_from_replay

            c = cramer_headlines_from_replay(sym, limit=cramer_limit)
        except Exception:
            c = []
    return list(a), list(b), list(c)


def _fetch_groups_parallel(
    sym: str, finnhub_limit: int, news_limit: int, cramer_limit: int
) -> tuple[list[str], list[str], list[str]]:
    from intel.api_budget import allow, record, should_skip_cramer_newsapi, should_skip_newsapi

    workers = int(os.getenv("NEWS_FETCH_MAX_WORKERS", "3"))
    out: dict[str, list[str]] = {}

    def _run(name: str, fn) -> tuple[str, list[str]]:
        return name, list(fn() or [])

    a = fetch_finnhub_headlines(sym, limit=finnhub_limit)
    if a and allow("finnhub"):
        record("finnhub")
    out["finnhub"] = list(a)

    skip_news = should_skip_newsapi(len(a))
    skip_cramer = should_skip_cramer_newsapi()
    jobs: list[tuple[str, object]] = []
    if not skip_news:
        jobs.append(("newsapi", lambda: fetch_newsapi_headlines(sym, limit=news_limit)))
    if not skip_cramer:
        jobs.append(("cramer", lambda: fetch_cramer_mentions(sym, limit=cramer_limit)))
    else:
        try:
            from intel.api_coverage import cramer_headlines_from_replay

            out["cramer"] = cramer_headlines_from_replay(sym, limit=cramer_limit)
        except Exception:
            out["cramer"] = []

    if jobs:
        with ThreadPoolExecutor(max_workers=min(workers, len(jobs))) as ex:
            futs = [ex.submit(_run, name, fn) for name, fn in jobs]
            for fut in futs:
                try:
                    name, lst = fut.result()
                    out[name] = lst
                    if name == "newsapi" and lst and allow("newsapi"):
                        record("newsapi")
                    if name == "cramer" and lst and allow("cramer_newsapi"):
                        record("cramer_newsapi")
                except Exception:
                    pass

    return (
        out.get("finnhub", []),
        out.get("newsapi", []),
        out.get("cramer", []),
    )


def _free_headline_fill(sym: str, limit: int) -> list[str]:
    """Google RSS + Yahoo + Wikipedia/SEC when NewsAPI/Finnhub are empty or 429."""
    out: list[str] = []
    seen: set[str] = set()

    def _add(lines: list[str]) -> None:
        for h in lines:
            t = str(h or "").strip()
            if not t:
                continue
            k = t.lower()[:120]
            if k in seen:
                continue
            seen.add(k)
            out.append(t[:320])

    try:
        from intel.google_news_feed import symbol_news_headlines

        _add(symbol_news_headlines(sym, limit=limit))
    except Exception:
        pass
    try:
        from news_reader import fetch_news

        yh = fetch_news(sym, limit=min(12, limit))
        _add([str(x.get("headline") or x.get("title") or "") for x in yh])
    except Exception:
        pass
    try:
        from intel.open_web_intel import open_web_headlines

        _add(open_web_headlines(sym, limit=min(8, limit)))
    except Exception:
        pass
    return out[:limit]


def fetch_all_headline_texts(symbol: str, finnhub_limit: int = 30, news_limit: int = 30, cramer_limit: int = 12) -> list[str]:
    a, b, c = fetch_headline_groups_parallel(symbol, finnhub_limit, news_limit, cramer_limit)
    return list(a) + list(b) + list(c)
