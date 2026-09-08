"""Eternal investor succession — failover when primary Cramer feeds go dark.

Primary: Cramer / Mad Money / Investing Club public feeds.
Alternates: allowlisted reputable public investor signal sources (RSS / APIs only).
When primary is stale, alternate weights rise so the stack keeps live signal coverage
as long as markets + public feeds exist. Never downloads binaries or shady hosts.
"""

from __future__ import annotations

import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import requests

from utils import log

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "intel" / "investor_succession.json"
ALT_LATEST = ROOT / "data" / "intel" / "investor_alt_signals.json"

# Allowlisted public feed URLs only (HTTPS news/RSS/API).
ALLOWLISTED_SOURCES: list[dict[str, Any]] = [
    {
        "id": "cramer_primary",
        "role": "primary",
        "urls": [
            "https://www.cnbc.com/mad-money/",
            "https://www.cnbc.com/jim-cramer/",
            "https://www.cnbc.com/investingclub/",
        ],
        "rss_queries": [
            'Jim Cramer Mad Money',
            'Jim Cramer Investing Club',
        ],
        "weight": 1.0,
    },
    {
        "id": "cnbc_markets",
        "role": "alternate",
        "urls": ["https://www.cnbc.com/markets/"],
        "rss_queries": ["CNBC stock market movers"],
        "weight": 0.55,
    },
    {
        "id": "yahoo_finance_news",
        "role": "alternate",
        "urls": ["https://finance.yahoo.com/topic/stock-market-news/"],
        "rss_queries": ["stock market news site:finance.yahoo.com"],
        "weight": 0.45,
    },
    {
        "id": "sec_edgar_atom",
        "role": "alternate",
        "urls": ["https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&output=atom"],
        "rss_queries": [],
        "weight": 0.35,
        "note": "Factual filings pulse — not opinion",
    },
    {
        "id": "federal_reserve",
        "role": "alternate",
        "urls": ["https://www.federalreserve.gov/json/ne-press.json"],
        "rss_queries": [],
        "weight": 0.30,
        "note": "Macro regime — not stock picks",
    },
]

CASHTAG = re.compile(r"\$([A-Z]{1,5})\b")
BULL = re.compile(r"\b(buy|bullish|upgrade|outperform|raised|surge|rally)\b", re.I)
BEAR = re.compile(r"\b(sell|bearish|downgrade|underperform|cut|plunge|crash)\b", re.I)


def _stale_hours() -> float:
    try:
        return float(os.getenv("INVESTOR_PRIMARY_STALE_HOURS", "36"))
    except ValueError:
        return 36.0


def _enabled() -> bool:
    return os.getenv("USE_INVESTOR_SUCCESSION", "true").lower() in ("1", "true", "yes")


def _parse_rss(xml_text: str) -> list[dict]:
    items: list[dict] = []
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return items
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        published = None
        if pub:
            try:
                published = parsedate_to_datetime(pub).astimezone(timezone.utc).isoformat()
            except Exception:
                published = pub
        if title:
            items.append({"title": title, "link": link, "published": published})
    # Atom
    ns = {"a": "http://www.w3.org/2005/Atom"}
    for entry in root.findall(".//{http://www.w3.org/2005/Atom}entry") or root.findall("a:entry", ns):
        title_el = entry.find("{http://www.w3.org/2005/Atom}title")
        title = (title_el.text or "").strip() if title_el is not None else ""
        link = ""
        for ln in entry.findall("{http://www.w3.org/2005/Atom}link"):
            href = ln.attrib.get("href") or ""
            if href.startswith("http"):
                link = href
                break
        if title:
            items.append({"title": title, "link": link, "published": None})
    return items


def _google_rss(query: str, when: str = "2d") -> list[dict]:
    url = (
        f"https://news.google.com/rss/search?q={quote_plus(query)}+when:{when}"
        f"&hl=en-US&gl=US&ceid=US:en"
    )
    try:
        r = requests.get(url, timeout=12, headers={"User-Agent": "FATE-AlgoBot/1.0 (succession)"})
        if r.status_code != 200:
            return []
        return _parse_rss(r.text)
    except Exception as e:
        log.debug("[SUCCESSION] rss %s: %s", query[:40], e)
        return []


def _url_alive(url: str) -> tuple[bool, str]:
    try:
        r = requests.get(
            url,
            timeout=float(os.getenv("INVESTOR_PROBE_TIMEOUT_SEC", "10")),
            headers={"User-Agent": "FATE-AlgoBot/1.0 (succession-probe)"},
            allow_redirects=True,
        )
        ok = r.status_code == 200 and len(r.text or "") > 200
        return ok, f"http_{r.status_code}"
    except Exception as e:
        return False, str(e)[:80]


def _cramer_transcript_mtime() -> float | None:
    p = Path(os.getenv("CRAMER_TRANSCRIPT_FILE", "data/replay/transcripts/CRAMER.jsonl"))
    if not p.is_file():
        return None
    try:
        return p.stat().st_mtime
    except OSError:
        return None


def _primary_freshness() -> dict[str, Any]:
    """Combine transcript mtime + post-market/hot files."""
    now = datetime.now(timezone.utc).timestamp()
    ages: list[float] = []
    sources_ok: dict[str, Any] = {}

    mt = _cramer_transcript_mtime()
    if mt is not None:
        ages.append((now - mt) / 3600.0)
        sources_ok["transcript_age_h"] = round((now - mt) / 3600.0, 2)

    for rel in (
        "data/intel/cramer_post_market_latest.json",
        "data/intel/morning_club_latest.json",
        "data/intel/cramer_hot_picks.json",
        "data/intel/cramer_cnbc_top10_sync.json",
    ):
        p = ROOT / rel
        if p.is_file():
            try:
                ages.append((now - p.stat().st_mtime) / 3600.0)
                sources_ok[p.name] = round((now - p.stat().st_mtime) / 3600.0, 2)
            except OSError:
                pass

    # Live probe primary URLs
    primary = next(s for s in ALLOWLISTED_SOURCES if s["role"] == "primary")
    url_hits = 0
    for u in primary["urls"]:
        ok, reason = _url_alive(u)
        sources_ok[u] = {"ok": ok, "reason": reason}
        if ok:
            url_hits += 1

    min_age = min(ages) if ages else 9999.0
    stale = min_age > _stale_hours() or url_hits == 0
    return {
        "stale": stale,
        "min_age_hours": round(min_age, 2) if ages else None,
        "stale_threshold_h": _stale_hours(),
        "primary_urls_ok": url_hits,
        "details": sources_ok,
    }


def _extract_tilts(titles: list[str]) -> dict[str, float]:
    tilts: dict[str, float] = {}
    for t in titles:
        syms = CASHTAG.findall(t.upper())
        if not syms:
            continue
        tilt = 0.0
        if BEAR.search(t):
            tilt = -0.55
        elif BULL.search(t):
            tilt = 0.55
        else:
            tilt = 0.15
        for s in syms[:3]:
            if len(s) < 2:
                continue
            prev = tilts.get(s, 0.0)
            if abs(tilt) >= abs(prev):
                tilts[s] = tilt
    return tilts


def harvest_alternates() -> dict[str, Any]:
    """Pull allowlisted alternate headlines → ticker tilts."""
    headlines: list[dict[str, str]] = []
    for src in ALLOWLISTED_SOURCES:
        if src["role"] != "alternate":
            continue
        for q in src.get("rss_queries") or []:
            for it in _google_rss(q)[:8]:
                headlines.append(
                    {
                        "title": str(it.get("title") or ""),
                        "link": str(it.get("link") or ""),
                        "source": src["id"],
                    }
                )
        for u in src.get("urls") or []:
            if "sec.gov" in u or u.endswith(".json") or "atom" in u:
                try:
                    r = requests.get(
                        u,
                        timeout=12,
                        headers={"User-Agent": "FATE-AlgoBot/1.0 (succession; research)"},
                    )
                    if r.status_code != 200:
                        continue
                    if "atom" in u or "xml" in (r.headers.get("Content-Type") or ""):
                        for it in _parse_rss(r.text)[:10]:
                            headlines.append(
                                {
                                    "title": str(it.get("title") or ""),
                                    "link": str(it.get("link") or u),
                                    "source": src["id"],
                                }
                            )
                    elif u.endswith(".json"):
                        try:
                            data = r.json()
                            # Fed press JSON shape varies — take string fields
                            blob = json.dumps(data)[:4000]
                            headlines.append({"title": blob[:180], "link": u, "source": src["id"]})
                        except Exception:
                            pass
                except Exception as e:
                    log.debug("[SUCCESSION] alt fetch %s: %s", src["id"], e)

    titles = [h["title"] for h in headlines if h.get("title")]
    tilts = _extract_tilts(titles)
    doc = {
        "synced_at_utc": datetime.now(timezone.utc).isoformat(),
        "date": date.today().isoformat(),
        "n_headlines": len(headlines),
        "tickers": {k: {"tilt": v, "source": "investor_alt"} for k, v in tilts.items()},
        "headlines": titles[:20],
    }
    ALT_LATEST.parent.mkdir(parents=True, exist_ok=True)
    ALT_LATEST.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return doc


def refresh_succession(*, force_alt: bool = False) -> dict[str, Any]:
    if not _enabled():
        return {"ok": False, "reason": "USE_INVESTOR_SUCCESSION=false"}

    primary = _primary_freshness()
    failover = bool(primary.get("stale")) or force_alt
    alt_doc: dict[str, Any] = {}
    if failover:
        alt_doc = harvest_alternates()

    # Weight schedule
    primary_w = 0.15 if failover else 1.0
    alt_w = 0.85 if failover else 0.10
    try:
        primary_w = float(os.getenv("INVESTOR_PRIMARY_WEIGHT", str(primary_w)))
        alt_w = float(os.getenv("INVESTOR_ALT_WEIGHT", str(alt_w)))
    except ValueError:
        pass

    state = {
        "ok": True,
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "failover_active": failover,
        "primary": primary,
        "weights": {"primary_cramer": primary_w, "alternates": alt_w},
        "roster": [
            {"id": s["id"], "role": s["role"], "urls": s["urls"], "weight": s["weight"]}
            for s in ALLOWLISTED_SOURCES
        ],
        "alt_n_tickers": len((alt_doc or {}).get("tickers") or {}),
        "eternal": True,
        "note": "Lives as long as markets + allowlisted public feeds exist",
    }
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
    log.info(
        "[SUCCESSION] failover=%s primary_age_h=%s alt_tickers=%s",
        failover,
        primary.get("min_age_hours"),
        state["alt_n_tickers"],
    )
    return state


def succession_boost_for(symbol: str) -> float:
    """Alternate-feed boost when failover is active (or mild blend always)."""
    if not _enabled():
        return 0.0
    if not STATE_PATH.is_file():
        refresh_succession()
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return 0.0
    alt_w = float((state.get("weights") or {}).get("alternates") or 0.0)
    if alt_w <= 0:
        return 0.0
    if not ALT_LATEST.is_file():
        return 0.0
    try:
        doc = json.loads(ALT_LATEST.read_text(encoding="utf-8"))
        meta = (doc.get("tickers") or {}).get(symbol.strip().upper())
        if not meta:
            return 0.0
        return max(-1.0, min(1.0, float(meta.get("tilt") or 0.0) * alt_w))
    except Exception:
        return 0.0


def status() -> dict[str, Any]:
    if STATE_PATH.is_file():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return refresh_succession()
