#!/usr/bin/env python3
"""Media intel — articles, podcasts, video captions → trading signal text.

Safe allowlisted fetches only (no arbitrary downloads / executables).
Feeds unified_intel + transcript store so the learning stack can improve
from the open web, not just price bars.
"""
from __future__ import annotations

import html
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TRANSCRIPT_DIR = ROOT / "data" / "replay" / "transcripts"
MEDIA_CACHE = ROOT / "data" / "media_intel"
USER_AGENT = "FATE-AlgoBot-MediaIntel/1.0 (+research; paper-trading)"

# Hosts we may fetch text/captions/RSS from (learning inputs only).
ALLOW_HOSTS = (
    "finance.yahoo.com",
    "yahoo.com",
    "seekingalpha.com",
    "cnbc.com",
    "reuters.com",
    "bloomberg.com",
    "wsj.com",
    "marketwatch.com",
    "investopedia.com",
    "sec.gov",
    "arxiv.org",
    "wikipedia.org",
    "news.google.com",
    "googleapis.com",
    "youtube.com",
    "youtu.be",
    "podcasts.apple.com",
    "feeds.megaphone.fm",
    "rss.cnn.com",
    "feeds.bbci.co.uk",
    "npr.org",
    "spotify.com",
    "anchor.fm",
    "simplecast.com",
    "buzzsprout.com",
    "libsyn.com",
    "transistor.fm",
    "pinecast.com",
    "fed.rss.npr.org",
)

# Default podcast / show RSS feeds (text titles+summaries — no audio binary hoard).
DEFAULT_PODCAST_FEEDS = (
    "https://feeds.megaphone.fm/GLT1412515089",  # Odd Lots (Bloomberg)
    "https://feeds.simplecast.com/54nAGcIl",  # The Journal (WSJ) — may 404; ignored
    "https://rss.cnn.com/rss/money_latest.rss",
    "https://feeds.bbci.co.uk/news/business/rss.xml",
    "https://www.npr.org/rss/rss.php?id=1006",  # Business
)

_TICKER_RE = re.compile(r"\b([A-Z]{1,5})\b")
_SENT_POS = re.compile(
    r"\b(surge|rally|beat|upgrade|record|growth|bullish|outperform|breakthrough|ai boom)\b",
    re.I,
)
_SENT_NEG = re.compile(
    r"\b(plunge|crash|miss|downgrade|lawsuit|fraud|bankrupt|bearish|layoff|probe|investigation)\b",
    re.I,
)


def _enabled() -> bool:
    return os.getenv("MEDIA_INTEL_ENABLED", "true").lower() in ("1", "true", "yes")


def _host_ok(url: str) -> bool:
    try:
        host = (urllib.parse.urlparse(url).hostname or "").lower()
    except Exception:
        return False
    if not host:
        return False
    return any(host == h or host.endswith("." + h) for h in ALLOW_HOSTS)


def _fetch(url: str, *, timeout: float = 12.0, max_bytes: int = 800_000) -> bytes | None:
    if not _host_ok(url):
        return None
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read(max_bytes + 1)
            if len(data) > max_bytes:
                data = data[:max_bytes]
            return data
    except Exception:
        return None


def _strip_html(raw: str) -> str:
    t = re.sub(r"(?is)<script.*?>.*?</script>", " ", raw)
    t = re.sub(r"(?is)<style.*?>.*?</style>", " ", t)
    t = re.sub(r"(?is)<[^>]+>", " ", t)
    t = html.unescape(t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _sentiment(text: str) -> float:
    if not text:
        return 0.0
    pos = len(_SENT_POS.findall(text))
    neg = len(_SENT_NEG.findall(text))
    if pos + neg == 0:
        return 0.0
    return max(-1.0, min(1.0, (pos - neg) / max(3.0, pos + neg)))


def fetch_article_text(url: str) -> dict[str, Any]:
    """Read an article page into plain text (allowlisted hosts only)."""
    out: dict[str, Any] = {"url": url, "ok": False, "text": "", "sentiment": 0.0}
    raw = _fetch(url)
    if not raw:
        return out
    try:
        text = _strip_html(raw.decode("utf-8", errors="ignore"))
    except Exception:
        return out
    out["ok"] = bool(text)
    out["text"] = text[:12000]
    out["sentiment"] = _sentiment(text)
    return out


def fetch_rss_items(feed_url: str, *, limit: int = 12) -> list[dict[str, Any]]:
    raw = _fetch(feed_url)
    if not raw:
        return []
    try:
        root = ET.fromstring(raw)
    except Exception:
        return []
    items: list[dict[str, Any]] = []
    # RSS 2.0 + Atom
    nodes = list(root.iter())
    for node in nodes:
        tag = node.tag.split("}")[-1].lower()
        if tag not in ("item", "entry"):
            continue
        title = ""
        link = ""
        summary = ""
        for child in list(node):
            ct = child.tag.split("}")[-1].lower()
            if ct == "title" and child.text:
                title = child.text.strip()
            elif ct in ("link",) and (child.text or child.get("href")):
                link = (child.text or child.get("href") or "").strip()
            elif ct in ("description", "summary", "content") and child.text:
                summary = _strip_html(child.text)[:1500]
        if title:
            blob = f"{title}. {summary}"
            items.append(
                {
                    "title": title,
                    "link": link,
                    "summary": summary,
                    "sentiment": _sentiment(blob),
                    "feed": feed_url,
                }
            )
        if len(items) >= limit:
            break
    return items


def podcast_digest(*, feeds: list[str] | None = None, limit_per: int = 8) -> dict[str, Any]:
    """Ingest podcast/show RSS titles+summaries (listen via text, no audio cache)."""
    feeds = feeds or [
        x.strip()
        for x in os.getenv("MEDIA_PODCAST_FEEDS", ",".join(DEFAULT_PODCAST_FEEDS)).split(",")
        if x.strip()
    ]
    all_items: list[dict[str, Any]] = []
    for f in feeds:
        all_items.extend(fetch_rss_items(f, limit=limit_per))
    # Score by absolute sentiment interest
    all_items.sort(key=lambda x: abs(float(x.get("sentiment") or 0)), reverse=True)
    MEDIA_CACHE.mkdir(parents=True, exist_ok=True)
    path = MEDIA_CACHE / "podcast_digest.json"
    doc = {"ts": time.time(), "n": len(all_items), "items": all_items[:80]}
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return doc


def youtube_caption_text(video_id: str) -> dict[str, Any]:
    """Best-effort YouTube timedtext captions (no binary download)."""
    out: dict[str, Any] = {"video_id": video_id, "ok": False, "text": "", "sentiment": 0.0}
    vid = video_id.strip()
    if "youtube.com" in vid or "youtu.be" in vid:
        q = urllib.parse.urlparse(vid)
        if "youtu.be" in (q.netloc or ""):
            vid = q.path.strip("/")
        else:
            vid = urllib.parse.parse_qs(q.query).get("v", [vid])[0]
    # Prefer English automatic / manual captions
    for lang in ("en", "en-US", "a.en"):
        url = f"https://www.youtube.com/api/timedtext?v={urllib.parse.quote(vid)}&lang={lang}"
        raw = _fetch(url, max_bytes=400_000)
        if not raw:
            continue
        try:
            xml = raw.decode("utf-8", errors="ignore")
            texts = re.findall(r"<text[^>]*>(.*?)</text>", xml, flags=re.I | re.S)
            joined = _strip_html(" ".join(html.unescape(t) for t in texts))
            if len(joined) < 40:
                continue
            out["ok"] = True
            out["text"] = joined[:20000]
            out["sentiment"] = _sentiment(joined)
            out["lang"] = lang
            return out
        except Exception:
            continue
    return out


def append_transcript(symbol: str, text: str, *, source: str) -> Path | None:
    if not text or len(text) < 40:
        return None
    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    path = TRANSCRIPT_DIR / f"{symbol.upper()}.jsonl"
    rec = {
        "ts": time.time(),
        "source": source,
        "text": text[:8000],
        "sentiment": _sentiment(text),
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    return path


def media_score_for_symbol(symbol: str, *, force: bool = False) -> dict[str, Any]:
    """Composite media score for one ticker from podcast digest + article search + transcripts."""
    sym = symbol.strip().upper()
    empty = {
        "symbol": sym,
        "boost": 0.0,
        "sentiment": 0.0,
        "n_hits": 0,
        "sources": [],
        "titles": [],
    }
    if not _enabled() or not sym:
        return empty

    hits: list[str] = []
    sents: list[float] = []
    sources: list[str] = []

    # Podcast / RSS digest
    digest_path = MEDIA_CACHE / "podcast_digest.json"
    if force or not digest_path.is_file() or time.time() - digest_path.stat().st_mtime > 3600:
        try:
            podcast_digest()
        except Exception:
            pass
    try:
        doc = json.loads(digest_path.read_text(encoding="utf-8")) if digest_path.is_file() else {}
        for it in doc.get("items") or []:
            blob = f"{it.get('title','')} {it.get('summary','')}"
            if re.search(rf"\b{re.escape(sym)}\b", blob):
                hits.append(str(it.get("title") or "")[:120])
                sents.append(float(it.get("sentiment") or 0.0))
                sources.append("podcast_rss")
    except Exception:
        pass

    # Yahoo Finance news headlines page (lightweight HTML scrape)
    try:
        url = f"https://finance.yahoo.com/quote/{urllib.parse.quote(sym)}/news/"
        art = fetch_article_text(url)
        if art.get("ok"):
            sents.append(float(art.get("sentiment") or 0.0))
            sources.append("yahoo_news_page")
            # Keep a short excerpt for learning
            append_transcript(sym, art["text"][:3000], source="yahoo_news_page")
    except Exception:
        pass

    # Existing transcript factors
    try:
        from intel.transcript_factor_engine import score_symbol_transcripts

        tr = score_symbol_transcripts(sym) or {}
        if tr:
            sents.append(float(tr.get("sentiment") or tr.get("score") or 0.0))
            sources.append("transcripts")
    except Exception:
        pass

    if not sents:
        return empty
    sent = sum(sents) / len(sents)
    boost = max(-0.35, min(0.35, sent * float(os.getenv("MEDIA_INTEL_GAIN", "0.22"))))
    return {
        "symbol": sym,
        "boost": round(boost, 4),
        "sentiment": round(sent, 4),
        "n_hits": len(hits) + len(sents),
        "sources": sorted(set(sources)),
        "titles": hits[:8],
    }


def refresh_media_intel(*, symbols: list[str] | None = None, youtube_ids: list[str] | None = None) -> dict[str, Any]:
    """Batch refresh podcast digest + optional YouTube captions into transcripts."""
    report: dict[str, Any] = {"podcast": {}, "youtube": [], "symbols": {}}
    report["podcast"] = podcast_digest()
    for vid in youtube_ids or [
        x.strip() for x in os.getenv("MEDIA_YOUTUBE_IDS", "").split(",") if x.strip()
    ]:
        cap = youtube_caption_text(vid)
        report["youtube"].append({"id": vid, "ok": cap.get("ok"), "sent": cap.get("sentiment")})
        if cap.get("ok"):
            # Tag as MARKET generic + extract tickers mentioned
            tickers = set(_TICKER_RE.findall(cap["text"][:5000])) & {
                s.upper() for s in (symbols or [])
            }
            if not tickers and symbols:
                tickers = {symbols[0].upper()}
            for t in list(tickers)[:12] or ["MARKET"]:
                append_transcript(t, cap["text"], source=f"youtube:{vid}")
    for sym in symbols or []:
        report["symbols"][sym.upper()] = media_score_for_symbol(sym, force=False)
    MEDIA_CACHE.mkdir(parents=True, exist_ok=True)
    (MEDIA_CACHE / "last_refresh.json").write_text(json.dumps(report, indent=2)[:200000] + "\n")
    return report


if __name__ == "__main__":
    import sys

    syms = [s.upper() for s in sys.argv[1:]] or ["AAPL", "NVDA", "MSFT", "SPCX"]
    print(json.dumps(refresh_media_intel(symbols=syms), indent=2)[:4000])
