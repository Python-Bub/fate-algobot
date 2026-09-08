"""Open-web company intel from public, allowlisted APIs — no LinkedIn scraping.

Sources (cached + paced by intel.http_scheduler so we do not sit on 429s):
  - Wikipedia REST summary (company / metal / coin pages)
  - SEC EDGAR recent 8-K / 10-Q / Form 4 (what insiders and the company filed)
  - Yahoo Finance analyst recommendation trend (Wall Street consensus)
  - Google News RSS + Yahoo headlines (already in-repo)
  - DuckDuckGo instant answers (free)

LinkedIn, private social graphs, and paywalled SERP dumps are out of scope:
those violate ToS. Form 4 + 8-K + IR press RSS are the legal equivalent of
"what people at the company just announced."
"""

from __future__ import annotations

import os
import re
import time
from typing import Any
from urllib.parse import quote

from intel.http_scheduler import get_json
from intel.news_sentiment_lexicon import classify_headline
from utils import log

_TICKER_WIKI = {
    "AAPL": "Apple_Inc.",
    "MSFT": "Microsoft",
    "AMZN": "Amazon_(company)",
    "GOOG": "Alphabet_Inc.",
    "GOOGL": "Alphabet_Inc.",
    "META": "Meta_Platforms",
    "NVDA": "Nvidia",
    "TSLA": "Tesla,_Inc.",
    "NFLX": "Netflix",
    "JNJ": "Johnson_%26_Johnson",
    "WMT": "Walmart",
    "JPM": "JPMorgan_Chase",
    "XOM": "ExxonMobil",
    "CVX": "Chevron_Corporation",
    "SLV": "Silver",
    "GLD": "Gold",
    "USO": "West_Texas_Intermediate",
    "BTC-USD": "Bitcoin",
    "ETH-USD": "Ethereum",
    "SOL-USD": "Solana_(blockchain_platform)",
    "IBIT": "Bitcoin",
    "BITO": "Bitcoin",
}

_FORM4_RE = re.compile(r"\b(4|form\s*4|8-?k|10-?q|10-?k|s-3|424b)\b", re.I)
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def _enabled() -> bool:
    return os.getenv("OPEN_WEB_INTEL_ENABLED", "true").lower() in ("1", "true", "yes", "on")


def _ttl() -> float:
    return float(os.getenv("OPEN_WEB_INTEL_TTL_SEC", "1800"))


def _wiki_title(symbol: str) -> str:
    s = symbol.strip().upper()
    if s in _TICKER_WIKI:
        return _TICKER_WIKI[s]
    try:
        import yfinance as yf

        info = yf.Ticker(s.replace("/", "-")).info or {}
        name = str(info.get("shortName") or info.get("longName") or s).strip()
        return name.replace(" ", "_")
    except Exception:
        return s


def fetch_wikipedia(symbol: str) -> dict[str, Any]:
    title = _wiki_title(symbol)
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(title)}"
    js = get_json(url, ttl_sec=86400, timeout=10.0) or {}
    extract = str(js.get("extract") or "").strip()
    desc = str(js.get("description") or "").strip()
    page = str((js.get("content_urls") or {}).get("desktop", {}).get("page") or "")
    blob = f"{desc} {extract}".strip()
    sent = classify_headline(blob[:500]).score if blob else 0.0
    return {
        "title": str(js.get("title") or title),
        "extract": extract[:1200],
        "description": desc,
        "url": page,
        "sentiment": float(sent),
        "ok": bool(extract),
    }


def fetch_yahoo_analysts(symbol: str) -> dict[str, Any]:
    """Wall Street recommendation trend via Yahoo (no extra key)."""
    out = {"score": 0.0, "strong_buy": 0, "buy": 0, "hold": 0, "sell": 0, "strong_sell": 0, "ok": False}
    try:
        import yfinance as yf

        rec = yf.Ticker(symbol.replace("/", "-")).recommendations_summary
        if rec is None or getattr(rec, "empty", True):
            rec = yf.Ticker(symbol.replace("/", "-")).recommendations
        if rec is None or getattr(rec, "empty", True):
            return out
        row = rec.iloc[-1]
        def _i(name: str) -> int:
            for k in row.index:
                if str(k).lower().replace(" ", "") == name:
                    try:
                        return int(float(row[k]))
                    except (TypeError, ValueError):
                        return 0
            return 0

        sb = _i("strongbuy") or int(float(row.get("strongBuy", 0) or 0))
        b = _i("buy") or int(float(row.get("buy", 0) or 0))
        h = _i("hold") or int(float(row.get("hold", 0) or 0))
        s = _i("sell") or int(float(row.get("sell", 0) or 0))
        ss = _i("strongsell") or int(float(row.get("strongSell", 0) or 0))
        tot = sb + b + h + s + ss
        if tot <= 0:
            return out
        # Map to [-1, 1]: strong buy=1, buy=0.5, hold=0, sell=-0.5, strong sell=-1
        score = (1.0 * sb + 0.5 * b + 0.0 * h - 0.5 * s - 1.0 * ss) / tot
        out.update(
            score=float(max(-1.0, min(1.0, score))),
            strong_buy=sb,
            buy=b,
            hold=h,
            sell=s,
            strong_sell=ss,
            ok=True,
        )
        return out
    except Exception as e:
        log.debug("[OPEN_WEB] yahoo analysts %s: %s", symbol, e)
        return out


def fetch_sec_filings(symbol: str, *, limit: int = 8) -> dict[str, Any]:
    """Recent EDGAR filings via the public company_tickers + submissions JSON."""
    empty: dict[str, Any] = {"cik": "", "filings": [], "form4_count": 0, "eightk_count": 0, "ok": False}
    try:
        tickers = get_json(
            "https://www.sec.gov/files/company_tickers.json",
            ttl_sec=86400,
            timeout=15.0,
            headers={"User-Agent": os.getenv("SEC_USER_AGENT", "FATE-AlgoBot research bot contact@local")},
        )
        if not isinstance(tickers, dict):
            return empty
        want = symbol.strip().upper()
        cik = ""
        for _k, row in tickers.items():
            if not isinstance(row, dict):
                continue
            if str(row.get("ticker") or "").upper() == want:
                cik = str(int(row.get("cik_str") or row.get("cik") or 0)).zfill(10)
                break
        if not cik or cik == "0000000000":
            return empty
        sub = get_json(
            f"https://data.sec.gov/submissions/CIK{cik}.json",
            ttl_sec=3600,
            timeout=15.0,
            headers={"User-Agent": os.getenv("SEC_USER_AGENT", "FATE-AlgoBot research bot contact@local")},
        )
        if not isinstance(sub, dict):
            return empty
        recent = (sub.get("filings") or {}).get("recent") or {}
        forms = list(recent.get("form") or [])
        dates = list(recent.get("filingDate") or [])
        acc = list(recent.get("accessionNumber") or [])
        descs = list(recent.get("primaryDocDescription") or [])
        items: list[dict[str, str]] = []
        n4 = 0
        n8 = 0
        for i, form in enumerate(forms[: max(20, limit)]):
            f = str(form or "")
            if "4" == f.strip() or f.upper().startswith("4/"):
                n4 += 1
            if f.upper() in ("8-K", "8K"):
                n8 += 1
            if i < limit:
                items.append(
                    {
                        "form": f,
                        "date": str(dates[i] if i < len(dates) else ""),
                        "accession": str(acc[i] if i < len(acc) else ""),
                        "description": str(descs[i] if i < len(descs) else ""),
                    }
                )
        return {"cik": cik, "filings": items, "form4_count": n4, "eightk_count": n8, "ok": True}
    except Exception as e:
        log.debug("[OPEN_WEB] sec %s: %s", symbol, e)
        return empty


def fetch_ddg_company(symbol: str) -> str:
    try:
        from intel.free_news_investigator import fetch_ddg_snippets

        return fetch_ddg_snippets(f"{symbol} stock news analyst rating company")
    except Exception:
        return ""


def open_web_intel_for(symbol: str, *, force_refresh: bool = False) -> dict[str, Any]:
    """Composite public-web intel used by unified_intel / pre-trade / fortress."""
    sym = symbol.strip().upper()
    empty = {
        "symbol": sym,
        "boost": 0.0,
        "sentiment": 0.0,
        "headlines": [],
        "sources": [],
        "wiki": {},
        "analysts": {},
        "sec": {},
        "block_long": False,
    }
    if not sym or not _enabled():
        return empty
    now = time.time()
    if not force_refresh:
        hit = _CACHE.get(sym)
        if hit and now - hit[0] < _ttl():
            return dict(hit[1])

    wiki = fetch_wikipedia(sym)
    analysts = fetch_yahoo_analysts(sym)
    sec = fetch_sec_filings(sym)
    ddg = fetch_ddg_company(sym)

    headlines: list[str] = []
    try:
        from intel.google_news_feed import symbol_news_headlines

        headlines.extend(symbol_news_headlines(sym, limit=10))
    except Exception:
        pass
    try:
        from news_reader import fetch_news

        for a in fetch_news(sym, limit=8):
            t = str(a.get("headline") or a.get("title") or "").strip()
            if t:
                headlines.append(t)
    except Exception:
        pass
    if wiki.get("extract"):
        headlines.append(str(wiki.get("extract"))[:240])
    if ddg:
        headlines.append(ddg[:240])

    lex = [classify_headline(h).score for h in headlines if h]
    news_sent = float(sum(lex) / len(lex)) if lex else 0.0
    wiki_sent = float(wiki.get("sentiment") or 0.0)
    an_sent = float(analysts.get("score") or 0.0)

    boost = (
        0.45 * an_sent
        + 0.35 * news_sent
        + 0.20 * wiki_sent
    )
    # Cluster of Form 4s is a caution, not an automatic block (sales are often 10b5-1).
    form4 = int(sec.get("form4_count") or 0)
    if form4 >= int(os.getenv("OPEN_WEB_FORM4_CAUTION", "6")):
        boost -= 0.08

    block = False
    if an_sent <= -0.55 and news_sent < 0:
        block = True

    out = {
        "symbol": sym,
        "boost": float(max(-1.0, min(1.0, boost))),
        "sentiment": float(max(-1.0, min(1.0, 0.5 * news_sent + 0.3 * an_sent + 0.2 * wiki_sent))),
        "headlines": headlines[:16],
        "sources": [s for s, ok in (("wikipedia", wiki.get("ok")), ("yahoo_analysts", analysts.get("ok")), ("sec", sec.get("ok"))) if ok],
        "wiki": wiki,
        "analysts": analysts,
        "sec": sec,
        "block_long": block,
        "form4_count": form4,
    }
    _CACHE[sym] = (now, out)
    return dict(out)


def open_web_boost_for(symbol: str) -> float:
    gain = float(os.getenv("OPEN_WEB_BOOST_GAIN", "0.35"))
    return max(-1.0, min(1.0, float(open_web_intel_for(symbol).get("boost") or 0.0) * gain))


def open_web_headlines(symbol: str, *, limit: int = 12) -> list[str]:
    return list(open_web_intel_for(symbol).get("headlines") or [])[:limit]
