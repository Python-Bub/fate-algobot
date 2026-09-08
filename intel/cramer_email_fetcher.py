"""Fetch Jim Cramer / CNBC Investing Club daily emails & articles from the web — no manual paste."""

from __future__ import annotations

import hashlib
import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote_plus

import requests

from utils import log

ROOT = Path(__file__).resolve().parents[1]
SYNC_PATH = ROOT / "data" / "intel" / "cramer_email_sync.json"

# Articles matching any of these are treated as Cramer's daily/weekly Club intel.
CRAMER_INTEL_PATTERNS = re.compile(
    r"(investing club|morning thoughts|top\s*10|charitable trust|"
    r"club meeting|weekly rundown|game plan|mad money|lightning round|"
    r"homestretch|home stretch|post[- ]?market|after[- ]?(the[- ]?)?close|"
    r"from the desk|final hour|trade alert)",
    re.I,
)
CRAMER_AUTHOR_PATTERNS = re.compile(r"\b(jim cramer|cramer|jeff marks)\b", re.I)

DEFAULT_GOOGLE_QUERIES = [
    'Jim Cramer "Investing Club" "Morning Thoughts"',
    'Jim Cramer CNBC "Top 10" market',
    'CNBC Investing Club Cramer charitable trust',
    'Jim Cramer Homestretch OR "lightning round" Mad Money',
    'Jim Cramer "from the desk" OR "post market" Investing Club',
]


def _enabled() -> bool:
    return os.getenv("CRAMER_AUTO_FETCH_ONLINE", "true").lower() in ("1", "true", "yes")


def _load_sync() -> dict:
    if not SYNC_PATH.is_file():
        return {}
    try:
        return json.loads(SYNC_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_sync(data: dict) -> None:
    SYNC_PATH.parent.mkdir(parents=True, exist_ok=True)
    SYNC_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _strip_html(html: str) -> str:
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.I | re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def _fetch_url_text(url: str, *, max_chars: int = 12000) -> str:
    if not url or not url.startswith("http"):
        return ""
    try:
        r = requests.get(
            url,
            timeout=float(os.getenv("CRAMER_FETCH_TIMEOUT_SEC", "12")),
            headers={"User-Agent": "FATE-AlgoBot/1.0 (intel; +https://github.com)"},
        )
        if r.status_code != 200:
            return ""
        return _strip_html(r.text)[:max_chars]
    except Exception as e:
        log.debug("[CRAMER_FETCH] url %s: %s", url[:60], e)
        return ""


def _parse_rss(xml_text: str) -> list[dict]:
    items: list[dict] = []
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return items
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = (item.findtext("description") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        published = None
        if pub:
            try:
                published = parsedate_to_datetime(pub).astimezone(timezone.utc).isoformat()
            except Exception:
                published = pub
        if title or desc:
            items.append({"title": title, "link": link, "description": desc, "published": published})
    return items


def fetch_google_news_rss(query: str, *, when: str = "1d") -> list[dict]:
    q = quote_plus(query.strip())
    url = (
        f"https://news.google.com/rss/search?q={q}+when:{when}"
        f"&hl=en-US&gl=US&ceid=US:en"
    )
    try:
        r = requests.get(url, timeout=12, headers={"User-Agent": "FATE-AlgoBot/1.0"})
        if r.status_code != 200:
            return []
        return _parse_rss(r.text)
    except Exception as e:
        log.debug("[CRAMER_FETCH] google rss: %s", e)
        return []


def fetch_newsapi_digest() -> list[dict]:
    key = (os.getenv("NEWSAPI_KEY") or "").strip()
    if not key or os.getenv("USE_NEWSAPI", "true").lower() in ("0", "false", "no"):
        return []
    try:
        from intel.api_coverage import allow_provider

        ok, _ = allow_provider("newsapi", context="cramer")
        if not ok:
            return []
    except Exception:
        pass
    queries = [
        q.strip()
        for q in (os.getenv("CRAMER_NEWSAPI_QUERIES") or "").split("|")
        if q.strip()
    ] or [
        'Jim Cramer "Investing Club" morning',
        "Jim Cramer Top 10 Morning Thoughts",
        "Jim Cramer Mad Money lightning round",
        "Jim Cramer Homestretch Investing Club",
    ]
    out: list[dict] = []
    for query in queries[:4]:
        try:
            r = requests.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q": query,
                    "language": "en",
                    "pageSize": 8,
                    "sortBy": "publishedAt",
                    "apiKey": key,
                },
                timeout=12,
            )
            if r.status_code == 429:
                break
            if r.status_code != 200:
                continue
            for a in r.json().get("articles") or []:
                out.append(
                    {
                        "title": str(a.get("title") or ""),
                        "link": str(a.get("url") or ""),
                        "description": str(a.get("description") or ""),
                        "published": str(a.get("publishedAt") or ""),
                        "source": "newsapi",
                    }
                )
            try:
                from intel.api_budget import record

                record("newsapi")
            except Exception:
                pass
        except Exception as e:
            log.debug("[CRAMER_FETCH] newsapi %s: %s", query[:40], e)
    return out


def fetch_finnhub_cramer_snippets() -> list[dict]:
    try:
        from intel.finnhub_batch import fetch_general_news
    except Exception:
        return []
    general = fetch_general_news()
    out: list[dict] = []
    for g in general[:80]:
        if not isinstance(g, dict):
            continue
        headline = str(g.get("headline") or "")
        summary = str(g.get("summary") or "")
        blob = f"{headline} {summary}"
        if not (CRAMER_AUTHOR_PATTERNS.search(blob) and CRAMER_INTEL_PATTERNS.search(blob)):
            if not CRAMER_INTEL_PATTERNS.search(headline):
                continue
        out.append(
            {
                "title": headline,
                "link": str(g.get("url") or ""),
                "description": summary,
                "published": str(g.get("datetime") or ""),
                "source": "finnhub",
            }
        )
    return out


def _is_cramer_intel_item(item: dict) -> bool:
    blob = f"{item.get('title', '')} {item.get('description', '')}"
    if CRAMER_INTEL_PATTERNS.search(blob):
        return True
    if CRAMER_AUTHOR_PATTERNS.search(blob) and re.search(
        r"\b(stock|market|buy|sell|club|earnings|IPO)\b", blob, re.I
    ):
        return True
    return False


def _dedupe_items(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for it in items:
        key = _text_hash((it.get("title") or "")[:120])
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def collect_cramer_articles(*, max_items: int = 12) -> list[dict]:
    """Gather today's Cramer / Investing Club articles from free + API sources."""
    if not _enabled():
        return []
    pool: list[dict] = []
    when = os.getenv("CRAMER_GOOGLE_WHEN", "1d")
    queries = [
        q.strip()
        for q in (os.getenv("CRAMER_GOOGLE_QUERIES") or "").split("|")
        if q.strip()
    ] or DEFAULT_GOOGLE_QUERIES
    for q in queries[:5]:
        pool.extend(fetch_google_news_rss(q, when=when))
    pool.extend(fetch_newsapi_digest())
    pool.extend(fetch_finnhub_cramer_snippets())
    filtered = [it for it in pool if _is_cramer_intel_item(it)]
    return _dedupe_items(filtered)[:max_items]


def articles_to_digest_text(articles: list[dict], *, fetch_bodies: bool = True) -> str:
    """Merge articles into one numbered digest (parser-ready)."""
    if not articles:
        return ""
    parts: list[str] = []
    for i, art in enumerate(articles, start=1):
        title = (art.get("title") or "").strip()
        desc = _strip_html(art.get("description") or "")
        body = ""
        if fetch_bodies and art.get("link"):
            body = _fetch_url_text(str(art["link"]), max_chars=4000)
        chunk = f"{title}. {desc}"
        if body and len(body) > 80:
            chunk += f" {body[:3500]}"
        parts.append(f"{i}. {chunk.strip()}")
    return "\n\n".join(parts)


def sync_daily_cramer_intel(*, force: bool = False) -> dict:
    """
    Fetch online Cramer intel, ingest into morning_club_intel + CRAMER.jsonl.
    Returns status dict; skips if same content hash already ingested today.
    """
    report: dict = {
        "ok": False,
        "articles": 0,
        "ingested": False,
        "skipped": False,
        "reason": "",
    }
    if not _enabled():
        report["reason"] = "CRAMER_AUTO_FETCH_ONLINE=false"
        return report

    # Post-market / Mad Money / Homestretch public + RSS ingest (runs every sync).
    try:
        from intel.cramer_post_market import sync_post_market_cramer

        pm = sync_post_market_cramer(force=force)
        report["post_market"] = {
            "ok": pm.get("ok"),
            "ingested": pm.get("ingested"),
            "picks": pm.get("picks"),
            "skipped": pm.get("skipped"),
            "reason": pm.get("reason"),
        }
    except Exception as e:
        log.debug("[CRAMER_FETCH] post_market: %s", e)
        report["post_market"] = {"ok": False, "error": str(e)[:120]}

    # Priority: direct CNBC Top 10 URL for today (if already published)
    try:
        from intel.cramer_cnbc_top10 import poll_and_ingest_cnbc_top10

        cnbc = poll_and_ingest_cnbc_top10(force=force)
        if cnbc.get("ingested"):
            report["ok"] = True
            report["ingested"] = True
            report["articles"] = 1
            report["source"] = "cnbc_top10"
            report["url"] = cnbc.get("url")
            report["tickers"] = cnbc.get("tickers")
            report["market_tone"] = cnbc.get("market_tone")
            return report
        if cnbc.get("skipped") and cnbc.get("reason") == "already_ingested_today":
            report["ok"] = True
            report["skipped"] = True
            report["reason"] = "already_synced_today"
            return report
    except Exception as e:
        log.debug("[CRAMER_FETCH] cnbc top10: %s", e)

    articles = collect_cramer_articles()
    report["articles"] = len(articles)
    if not articles:
        report["reason"] = "no_articles_found"
        return report

    text = articles_to_digest_text(
        articles,
        fetch_bodies=os.getenv("CRAMER_FETCH_ARTICLE_BODIES", "true").lower()
        in ("1", "true", "yes"),
    )
    if len(text) < 200:
        report["reason"] = "digest_too_short"
        return report

    h = _text_hash(text)
    today = date.today().isoformat()
    prev = _load_sync()
    if not force and prev.get("date") == today and prev.get("content_hash") == h:
        report["ok"] = True
        report["skipped"] = True
        report["reason"] = "already_synced_today"
        return report

    from intel.morning_club_intel import ingest_morning_email

    doc = ingest_morning_email(text, source="online_cramer_digest")
    _save_sync(
        {
            "date": today,
            "content_hash": h,
            "synced_at_utc": datetime.now(timezone.utc).isoformat(),
            "articles": len(articles),
            "top_titles": [a.get("title", "")[:100] for a in articles[:5]],
            "tickers": len(doc.get("tickers") or {}),
            "market_tone": doc.get("market_tone"),
        }
    )
    report["ok"] = True
    report["ingested"] = True
    report["tickers"] = len(doc.get("tickers") or {})
    report["market_tone"] = doc.get("market_tone")
    log.info(
        "[CRAMER_FETCH] synced %d articles → %d tickers tone=%s",
        len(articles),
        report["tickers"],
        doc.get("market_tone"),
    )
    return report
