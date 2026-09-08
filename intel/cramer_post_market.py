"""Jim Cramer post-market / Mad Money / Homestretch intel.

CNBC Investing Club + Mad Money surface several after-hours products we can use:
  - Mad Money (6 PM ET): lightning rounds + episode stock calls
  - Homestretch: club midday→close audio/notes
  - "From the Desk of Jim Cramer" + post-market wraps

This module scrapes public CNBC Mad Money headlines, extracts buy/sell tilt,
appends to `CRAMER.jsonl`, and writes `data/intel/cramer_post_market_latest.json`
so rank/fortress can boost the same day into the close and overnight.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import requests

from utils import log

ROOT = Path(__file__).resolve().parents[1]
LATEST_PATH = ROOT / "data" / "intel" / "cramer_post_market_latest.json"
SYNC_PATH = ROOT / "data" / "intel" / "cramer_post_market_sync.json"
MAD_MONEY_URL = os.getenv("CRAMER_MAD_MONEY_URL", "https://www.cnbc.com/mad-money/")
# Extra allowlisted afternoon / episode surfaces (public HTTPS pages + RSS only).
MAD_MONEY_EXTRA_URLS = [
    u.strip()
    for u in os.getenv(
        "CRAMER_MAD_MONEY_EXTRA_URLS",
        "https://www.cnbc.com/mad-money/,"
        "https://www.cnbc.com/jim-cramer/,"
        "https://www.cnbc.com/investingclub/",
    ).split(",")
    if u.strip().startswith("https://")
]
# Public podcast / show RSS mirrors (allowlisted hosts only — titles, never media binaries).
MAD_MONEY_RSS_URLS = [
    u.strip()
    for u in os.getenv(
        "CRAMER_MAD_MONEY_RSS_URLS",
        "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    ).split(",")
    if u.strip().startswith("https://")
]

# Prose company names → tickers (lightning round titles rarely use $cashtags).
NAME_TO_TICKER = {
    "NLIGHT": "LASR",
    "N LIGHT": "LASR",
    "DUOLINGO": "DUOL",
    "CARPENTER TECHNOLOGY": "CRS",
    "CARPENTER": "CRS",
    "AMPRIUS": "AMPX",
    "AMPRIUS TECHNOLOGIES": "AMPX",
    "CASEY'S": "CASY",
    "CASEYS": "CASY",
    "CASEY'S GENERAL STORES": "CASY",
    "CHEWY": "CHWY",
    "WENDY'S": "WEN",
    "WENDYS": "WEN",
    "WALMART": "WMT",
    "TJX": "TJX",
    "APPLE": "AAPL",
    "OPENAI": "OPENAI",
    "PEPSI": "PEP",
    "PEPSICO": "PEP",
    "SK HYNIX": "000660.KS",
    "SALESFORCE": "CRM",
    "SERVICENOW": "NOW",
    "SERVICE NOW": "NOW",
    "ARISTA": "ANET",
    "ARISTA NETWORKS": "ANET",
    "MICRON": "MU",
    "NVIDIA": "NVDA",
    "META": "META",
    "GOOGLE": "GOOGL",
    "ALPHABET": "GOOGL",
    "AMAZON": "AMZN",
    "MICROSOFT": "MSFT",
    "COSTCO": "COST",
    "JOHNSON & JOHNSON": "JNJ",
    "JOHNSON AND JOHNSON": "JNJ",
    "JPMORGAN": "JPM",
    "JP MORGAN": "JPM",
}

CASHTAG_RE = re.compile(r"\$([A-Z]{1,5})\b")
BULL_RE = re.compile(
    r"\b(buy|buying|bullish|own|long|speculative buy|terrific|winner|opportunity|dip)\b",
    re.I,
)
BEAR_RE = re.compile(
    r"\b(sell|selling|avoid|trim|bearish|too hard to own|stay away|no to owning|dump)\b",
    re.I,
)


def _enabled() -> bool:
    return os.getenv("USE_CRAMER_POST_MARKET", "true").lower() in ("1", "true", "yes")


def _strip_html(html: str) -> str:
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.I | re.S)
    t = re.sub(r"<[^>]+>", "\n", t)
    t = re.sub(r"&nbsp;", " ", t)
    t = re.sub(r"&amp;", "&", t)
    t = re.sub(r"\n+", "\n", t)
    return t


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


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


def fetch_mad_money_headlines(*, url: str | None = None) -> list[dict[str, str]]:
    """Pull public Mad Money page headlines (lightning round + recaps + RSS)."""
    urls = []
    if url:
        urls.append(url)
    else:
        urls.append(MAD_MONEY_URL)
        urls.extend(MAD_MONEY_EXTRA_URLS)
    # Dedupe preserve order
    seen_u: set[str] = set()
    uniq_urls: list[str] = []
    for u in urls:
        if u not in seen_u:
            seen_u.add(u)
            uniq_urls.append(u)

    hits: list[dict[str, str]] = []
    seen: set[str] = set()

    def _absorb_lines(text: str, source: str) -> None:
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        for i, ln in enumerate(lines):
            low = ln.lower()
            if not any(
                k in low
                for k in (
                    "lightning round",
                    "cramer",
                    "jim cramer",
                    "mad money",
                    "buy the dip",
                    "stocks to buy",
                    "homestretch",
                    "from the desk",
                )
            ):
                continue
            if len(ln) < 24 or len(ln) > 220:
                continue
            key = _hash(ln.lower())
            if key in seen:
                continue
            seen.add(key)
            date_hint = ""
            if i + 1 < len(lines) and re.search(r"20\d{2}", lines[i + 1]):
                date_hint = lines[i + 1][:40]
            hits.append({"title": ln, "date_hint": date_hint, "source": source})
            if len(hits) >= int(os.getenv("CRAMER_PM_MAX_HEADLINES", "40")):
                return

    for target in uniq_urls:
        try:
            r = requests.get(
                target,
                timeout=float(os.getenv("CRAMER_FETCH_TIMEOUT_SEC", "15")),
                headers={"User-Agent": "FATE-AlgoBot/1.0 (intel; Mad Money post-market)"},
            )
            if r.status_code != 200:
                log.warning("[CRAMER_PM] %s HTTP %s", target[:60], r.status_code)
                continue
            _absorb_lines(_strip_html(r.text), "cnbc_mad_money")
        except Exception as e:
            log.warning("[CRAMER_PM] fetch failed %s: %s", target[:40], e)

    # Podcast / CNBC RSS (titles only — never download media binaries)
    for rss_url in MAD_MONEY_RSS_URLS:
        try:
            r = requests.get(
                rss_url,
                timeout=12,
                headers={"User-Agent": "FATE-AlgoBot/1.0 (intel; Mad Money RSS)"},
            )
            if r.status_code != 200:
                continue
            import xml.etree.ElementTree as ET

            root = ET.fromstring(r.text)
            for item in root.iter("item"):
                title = (item.findtext("title") or "").strip()
                if not title:
                    continue
                low = title.lower()
                if not any(k in low for k in ("cramer", "mad money", "lightning", "stock")):
                    # Still keep if cashtag present
                    if "$" not in title:
                        continue
                key = _hash(title.lower())
                if key in seen:
                    continue
                seen.add(key)
                hits.append(
                    {
                        "title": title[:220],
                        "date_hint": (item.findtext("pubDate") or "")[:40],
                        "source": "mad_money_rss",
                    }
                )
                if len(hits) >= int(os.getenv("CRAMER_PM_MAX_HEADLINES", "40")):
                    break
        except Exception as e:
            log.debug("[CRAMER_PM] rss %s: %s", rss_url[:40], e)

    return hits[: int(os.getenv("CRAMER_PM_MAX_HEADLINES", "40"))]


def _resolve_tickers(title: str) -> list[str]:
    found: list[str] = []
    for m in CASHTAG_RE.findall(title.upper()):
        if m not in found:
            found.append(m)
    up = title.upper()
    # Longest name match first
    for name in sorted(NAME_TO_TICKER.keys(), key=len, reverse=True):
        if name in up:
            t = NAME_TO_TICKER[name]
            if t not in found and not t.endswith(".KS") and t.isalpha() and 1 < len(t) <= 5:
                found.append(t)
            # break after first solid company name to avoid noise
            if found:
                break
    return found[:4]


def _tilt_for_title(title: str) -> float:
    # Prefer bear when both fire — "own" in BULL_RE also hits "too hard to own"
    if BEAR_RE.search(title):
        return -0.85
    if BULL_RE.search(title):
        if re.search(r"speculative buy|screaming|terrific|home run", title, re.I):
            return 0.95
        return 0.75
    if "lightning round" in title.lower():
        return 0.35  # segment mention without clear verb — mild interest
    return 0.15


def headlines_to_picks(headlines: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    picks: dict[str, dict[str, Any]] = {}
    for h in headlines:
        title = h.get("title") or ""
        tilt = _tilt_for_title(title)
        for sym in _resolve_tickers(title):
            prev = picks.get(sym)
            if prev is None or abs(tilt) >= abs(float(prev.get("tilt", 0))):
                picks[sym] = {
                    "tilt": tilt,
                    "title": title[:180],
                    "date_hint": h.get("date_hint", ""),
                    "source": h.get("source", "cnbc_mad_money"),
                }
    return picks


def _append_cramer_jsonl(picks: dict[str, dict[str, Any]], *, day: str) -> int:
    path = Path(os.getenv("CRAMER_TRANSCRIPT_FILE", "data/replay/transcripts/CRAMER.jsonl"))
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("a", encoding="utf-8") as fh:
        for sym, meta in picks.items():
            tilt = float(meta.get("tilt") or 0)
            verb = "buy buy buy" if tilt > 0 else "sell sell sell"
            text = f"{verb} ${sym}. Cramer post-market / Mad Money: {meta.get('title')}"
            fh.write(
                json.dumps(
                    {
                        "text": text,
                        "ts": day,
                        "source": "cramer_post_market",
                        "symbol": sym,
                        "tilt": tilt,
                    }
                )
                + "\n"
            )
            n += 1
    return n


def sync_post_market_cramer(*, force: bool = False) -> dict[str, Any]:
    """Fetch Mad Money public page → transcript boosts + latest intel file."""
    report: dict[str, Any] = {"ok": False, "ingested": False, "skipped": False, "picks": 0}
    if not _enabled():
        report["reason"] = "USE_CRAMER_POST_MARKET=false"
        return report

    headlines = fetch_mad_money_headlines()
    # Supplement with google RSS for Homestretch / post-market letter language
    try:
        from intel.cramer_email_fetcher import fetch_google_news_rss

        for q in (
            'Jim Cramer Homestretch Investing Club',
            'Jim Cramer "lightning round" Mad Money',
            'Jim Cramer "post market" OR "after the close" Investing Club',
            'Jim Cramer "from the desk"',
        ):
            for it in fetch_google_news_rss(q, when=os.getenv("CRAMER_GOOGLE_WHEN", "2d"))[:6]:
                headlines.append(
                    {
                        "title": str(it.get("title") or ""),
                        "date_hint": str(it.get("published") or "")[:40],
                        "source": "google_rss_pm",
                    }
                )
    except Exception as e:
        log.debug("[CRAMER_PM] rss: %s", e)

    # Dedupe titles
    dedup: list[dict[str, str]] = []
    seen: set[str] = set()
    for h in headlines:
        t = (h.get("title") or "").strip()
        if len(t) < 20:
            continue
        k = _hash(t.lower())
        if k in seen:
            continue
        seen.add(k)
        dedup.append(h)

    picks = headlines_to_picks(dedup)
    day = date.today().isoformat()
    blob = json.dumps({"day": day, "titles": [h.get("title") for h in dedup[:12]], "picks": picks}, sort_keys=True)
    content_hash = _hash(blob)
    prev = _load_sync()
    if not force and prev.get("date") == day and prev.get("content_hash") == content_hash:
        report["ok"] = True
        report["skipped"] = True
        report["reason"] = "already_synced_today"
        report["picks"] = len(picks)
        return report

    n = _append_cramer_jsonl(picks, day=day) if picks else 0
    doc = {
        "date": day,
        "synced_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "cramer_post_market",
        "headlines": [h.get("title") for h in dedup[:16]],
        "tickers": {s: meta for s, meta in picks.items()},
        "n_picks": len(picks),
        "content_hash": content_hash,
    }
    LATEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    LATEST_PATH.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    _save_sync({"date": day, "content_hash": content_hash, "picks": len(picks), "jsonl_lines": n})

    # Soft-ingest digest so morning_club boost path also sees evening names
    if picks and os.getenv("CRAMER_PM_INGEST_CLUB", "true").lower() in ("1", "true", "yes"):
        try:
            from intel.morning_club_intel import ingest_morning_email

            lines = [
                f"Jim Cramer Mad Money / Homestretch post-market digest {day}.",
                "Lightning round and episode calls:",
            ]
            for s, meta in picks.items():
                verb = "BUY" if float(meta["tilt"]) > 0 else "SELL"
                lines.append(f"{verb} ${s} — {meta.get('title')}")
            ingest_morning_email("\n".join(lines), source="cramer_post_market")
        except Exception as e:
            log.debug("[CRAMER_PM] club ingest: %s", e)

    report.update({"ok": True, "ingested": True, "picks": len(picks), "jsonl_lines": n, "headlines": len(dedup)})
    log.info("[CRAMER_PM] synced picks=%d headlines=%d → %s", len(picks), len(dedup), LATEST_PATH.name)
    return report


def post_market_boost_for(symbol: str) -> float:
    """Extra tilt from latest post-market file (decays same day → overnight)."""
    if not _enabled() or not LATEST_PATH.is_file():
        return 0.0
    try:
        doc = json.loads(LATEST_PATH.read_text(encoding="utf-8"))
        if doc.get("date") != date.today().isoformat() and os.getenv(
            "CRAMER_PM_ALLOW_YESTERDAY", "true"
        ).lower() not in ("1", "true", "yes"):
            return 0.0
        # Allow yesterday overnight into today's open
        age_ok = doc.get("date") in {
            date.today().isoformat(),
            # yesterday string via datetime
        }
        from datetime import timedelta

        yday = (date.today() - timedelta(days=1)).isoformat()
        if doc.get("date") not in (date.today().isoformat(), yday):
            return 0.0
        meta = (doc.get("tickers") or {}).get(symbol.strip().upper())
        if not meta:
            return 0.0
        w = float(os.getenv("CRAMER_PM_BOOST_GAIN", "0.55"))
        return max(-1.0, min(1.0, float(meta.get("tilt") or 0.0) * w))
    except Exception:
        return 0.0
