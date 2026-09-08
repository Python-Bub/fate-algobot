"""Free (no paid API) news + undervaluation investigation.

Sources (non-premium):
  - Google News RSS (public)
  - Yahoo Finance headlines (homemade news_reader)
  - DuckDuckGo Instant Answer JSON (no key)
  - Local value/DCF screen when a discount claim appears

Writes ``data/intel/valuation_alerts.json`` for fortress/HFT/bottom-fisher to boost.
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "intel" / "valuation_alerts.json"
WATCHLIST = ROOT / "data" / "intel" / "valuation_watchlist.json"

_VALUE_CLAIM = re.compile(
    r"("
    r"undervalued|under\s*valued|below\s+fair\s+value|"
    r"trading\s+(?:at\s+)?a\s+discount|margin\s+of\s+safety|"
    r"(\d{1,2})\s*%\s*(undervalued|upside|discount)|"
    r"price\s+target.{0,40}(upside|implies)|"
    r"intrinsic\s+value|bargain\s+(buy|valuation)|cheap\s+vs"
    r")",
    re.I,
)
_TICKER_RE = re.compile(r"\b([A-Z]{1,5})\b")
_PCT_RE = re.compile(r"(\d{1,2})\s*%\s*(undervalued|upside|discount)", re.I)

# Common name → ticker hints for headline parsing
_NAME_HINTS = {
    "GOOGLE": "GOOG",
    "ALPHABET": "GOOG",
    "GOOGL": "GOOGL",
    "GOOG": "GOOG",
    "APPLE": "AAPL",
    "MICROSOFT": "MSFT",
    "AMAZON": "AMZN",
    "NVIDIA": "NVDA",
    "META": "META",
    "TESLA": "TSLA",
    "NETFLIX": "NFLX",
}


def _b(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in ("1", "true", "yes", "on")


def fetch_ddg_snippets(query: str, *, max_chars: int = 1600) -> str:
    """DuckDuckGo Instant Answer — free, no API key."""
    try:
        q = quote_plus(query.strip()[:180])
        r = requests.get(
            f"https://api.duckduckgo.com/?q={q}&format=json&no_html=1&skip_disambig=1",
            timeout=10,
            headers={"User-Agent": "FATE-AlgoBot/1.0"},
        )
        if r.status_code != 200:
            return ""
        data = r.json() if r.text else {}
        parts: list[str] = []
        for key in ("AbstractText", "Answer", "Heading"):
            v = str(data.get(key) or "").strip()
            if v:
                parts.append(v)
        for topic in (data.get("RelatedTopics") or [])[:8]:
            if isinstance(topic, dict):
                t = str(topic.get("Text") or "").strip()
                if t:
                    parts.append(t)
            elif isinstance(topic, list):
                for sub in topic[:3]:
                    if isinstance(sub, dict):
                        t = str(sub.get("Text") or "").strip()
                        if t:
                            parts.append(t)
        blob = " | ".join(parts)
        return blob[:max_chars]
    except Exception:
        return ""


def fetch_free_headlines(symbol: str, *, limit: int = 16) -> list[str]:
    """Aggregate free headlines — Google RSS + Yahoo + DDG (no NewsAPI/Finnhub required)."""
    sym = symbol.strip().upper()
    aliases = [sym]
    if sym in ("GOOG", "GOOGL"):
        aliases = ["GOOG", "GOOGL", "Alphabet"]
    elif sym in _NAME_HINTS.values():
        # include company name for RSS recall
        for name, ticker in _NAME_HINTS.items():
            if ticker == sym and name not in aliases:
                aliases.append(name.title() if name not in ("GOOG", "GOOGL") else name)
    out: list[str] = []
    seen: set[str] = set()

    def _add(lines: list[str]) -> None:
        for h in lines:
            t = str(h or "").strip()
            if not t:
                continue
            key = t.lower()[:120]
            if key in seen:
                continue
            seen.add(key)
            out.append(t[:320])

    if _b("USE_GOOGLE_NEWS_RSS", True):
        try:
            from intel.google_news_feed import fetch_google_news_rss_headlines

            for qbase in aliases[:3]:
                _add(fetch_google_news_rss_headlines(f"{qbase} stock", when="2d", limit=limit))
                _add(
                    fetch_google_news_rss_headlines(
                        f'{qbase} undervalued OR "fair value" OR "20%" upside',
                        when="7d",
                        limit=max(6, limit // 2),
                    )
                )
        except Exception:
            pass

    try:
        from news_reader import fetch_news

        for s in {sym, "GOOGL" if sym == "GOOG" else "GOOG" if sym == "GOOGL" else sym}:
            yh = fetch_news(s, limit=12)
            if isinstance(yh, list):
                _add(
                    [
                        str(
                            (x.get("headline") or x.get("title") or "")
                            if isinstance(x, dict)
                            else x
                        )
                        for x in yh
                    ]
                )
    except Exception:
        pass

    ddg = fetch_ddg_snippets(f"{aliases[0]} stock undervalued fair value analysis")
    if ddg:
        _add([ddg])

    return out[: limit * 2]


def _extract_discount_pct(text: str) -> float | None:
    m = _PCT_RE.search(text or "")
    if not m:
        return None
    try:
        return float(m.group(1)) / 100.0
    except Exception:
        return None


def _guess_tickers(text: str) -> list[str]:
    up = (text or "").upper()
    found: list[str] = []
    for name, sym in _NAME_HINTS.items():
        if name in up and sym not in found:
            found.append(sym)
    # $TICKER form
    for m in re.finditer(r"\$([A-Z]{1,5})\b", up):
        sym = m.group(1)
        if sym not in found and sym not in {"CEO", "CFO", "USA", "IPO", "ETF", "GDP"}:
            found.append(sym)
    return found[:6]


def investigate_symbol(symbol: str) -> dict[str, Any]:
    """Investigate undervaluation claims for one symbol using free sources + local DCF."""
    sym = symbol.strip().upper()
    headlines = fetch_free_headlines(sym)
    claims = [h for h in headlines if _VALUE_CLAIM.search(h)]
    claim_pcts = [_extract_discount_pct(h) for h in claims]
    claim_pcts = [p for p in claim_pcts if p is not None]
    headline_discount = max(claim_pcts) if claim_pcts else None

    mos = None
    value_boost = 0.0
    value_rationale = ""
    try:
        from analytics.value_investing import analyze_value, value_investing_rank_boost

        av = analyze_value(sym)
        if isinstance(av, dict):
            mos = av.get("margin_of_safety")
            if mos is not None:
                try:
                    mos = float(mos)
                except Exception:
                    mos = None
            value_rationale = str(av.get("rationale") or av.get("summary") or "")[:240]
        value_boost = float(value_investing_rank_boost(sym) or 0.0)
    except Exception as e:
        value_rationale = f"value_screen_error:{e}"[:120]

    # Lexicon tilt on claims
    lex_score = 0.0
    try:
        from intel.news_sentiment_lexicon import classify_headline

        scores = [float(classify_headline(h).score) for h in claims[:8]]
        if scores:
            lex_score = sum(scores) / len(scores)
    except Exception:
        if claims:
            lex_score = 0.35

    # Action: buy-investigate when claim OR solid MOS
    mos_ok = mos is not None and mos >= float(os.getenv("VALUE_ALERT_MIN_MOS", "0.12"))
    claim_ok = bool(claims) and (
        headline_discount is None
        or headline_discount >= float(os.getenv("VALUE_ALERT_MIN_CLAIM_PCT", "0.10"))
    )
    investigate = claim_ok or mos_ok
    allow_long_boost = investigate and lex_score >= -0.15 and (mos is None or mos > -0.05)

    # Size tilt 0..0.25 from claim strength + MOS
    tilt = 0.0
    if allow_long_boost:
        tilt = 0.06
        if headline_discount:
            tilt += min(0.12, headline_discount * 0.5)
        if mos_ok and mos is not None:
            tilt += min(0.10, max(0.0, mos) * 0.4)
        tilt += max(0.0, min(0.05, value_boost))
        tilt = min(0.25, tilt)

    return {
        "symbol": sym,
        "investigate": investigate,
        "allow_long_boost": allow_long_boost,
        "tilt": round(tilt, 4),
        "headline_discount": headline_discount,
        "margin_of_safety": mos,
        "value_boost": round(value_boost, 4),
        "lex_score": round(lex_score, 4),
        "claim_count": len(claims),
        "headline_count": len(headlines),
        "top_claim": (claims[0][:240] if claims else ""),
        "top_headline": (headlines[0][:240] if headlines else ""),
        "value_rationale": value_rationale,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def scan_watchlist(symbols: list[str] | None = None) -> dict[str, Any]:
    if symbols is None:
        symbols = _default_watchlist()
    rows: dict[str, Any] = {}
    for i, sym in enumerate(symbols):
        if i:
            time.sleep(float(os.getenv("FREE_NEWS_PAUSE_SEC", "0.4")))
        rows[sym] = investigate_symbol(sym)
    # Also harvest open value claims from broad Google RSS (GOOG-style discovery)
    if _b("FREE_NEWS_BROAD_SCAN", True):
        try:
            from intel.google_news_feed import fetch_google_news_rss_headlines

            broad = fetch_google_news_rss_headlines(
                'stock undervalued OR "20% undervalued" OR "fair value" upside',
                when="2d",
                limit=20,
            )
            for h in broad:
                if not _VALUE_CLAIM.search(h):
                    continue
                for sym in _guess_tickers(h):
                    if sym in rows:
                        continue
                    row = investigate_symbol(sym)
                    if not row.get("top_claim"):
                        row["top_claim"] = h[:240]
                        row["claim_count"] = max(1, int(row.get("claim_count") or 0))
                        row["investigate"] = True
                    rows[sym] = row
        except Exception:
            pass

    payload = {
        "updated_ms": int(time.time() * 1000),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "free_news_investigator",
        "n": len(rows),
        "rows": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def _default_watchlist() -> list[str]:
    if WATCHLIST.is_file():
        try:
            doc = json.loads(WATCHLIST.read_text(encoding="utf-8"))
            syms = doc if isinstance(doc, list) else doc.get("symbols") or []
            return [str(s).upper() for s in syms if s][:40]
        except Exception:
            pass
    # Liquid majors + any FORCE stickies
    base = ["GOOG", "GOOGL", "AAPL", "MSFT", "AMZN", "META", "NVDA", "TSLA", "BRK.B", "JPM"]
    try:
        from tools.tradeable_universe import hft_trade_tickers

        for s in hft_trade_tickers()[:20]:
            if s not in base:
                base.append(s)
    except Exception:
        pass
    return base[:30]


def tilt_for(symbol: str) -> float:
    """Read last alert file tilt for a symbol (0 if missing)."""
    if not OUT.is_file():
        return 0.0
    try:
        doc = json.loads(OUT.read_text(encoding="utf-8"))
        row = (doc.get("rows") or {}).get(symbol.strip().upper()) or {}
        if row.get("allow_long_boost"):
            return float(row.get("tilt") or 0.0)
    except Exception:
        return 0.0
    return 0.0
