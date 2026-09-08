"""CNBC Jim Cramer Top 10 — direct URL poll (date + weekday slug)."""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from utils import log

ROOT = Path(__file__).resolve().parents[1]
ET = ZoneInfo("America/New_York")
SYNC_PATH = ROOT / "data" / "intel" / "cramer_email_sync.json"
CNBC_SYNC_PATH = ROOT / "data" / "intel" / "cramer_cnbc_top10_sync.json"

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday")
TOP10_MARKERS = re.compile(
    r"(my top 10 things to watch|top 10 things to watch in the stock market)",
    re.I,
)
NUMBERED_ITEM = re.compile(r"\b\d+\.\s+")


def _enabled() -> bool:
    return os.getenv("CRAMER_CNBC_TOP10_ENABLED", "true").lower() in ("1", "true", "yes")


def _parse_et_time(raw: str, default: time) -> time:
    s = (raw or "").strip()
    if not s:
        return default
    parts = s.split(":")
    try:
        if len(parts) >= 2:
            return time(int(parts[0]), int(parts[1]))
    except ValueError:
        pass
    return default


def now_et() -> datetime:
    return datetime.now(ET)


def cnbc_top10_url(for_day: date | None = None) -> str:
    """Build today's CNBC Top 10 URL — e.g. .../2026/06/04/jim-cramers-top-10-...-thursday.html"""
    d = for_day or now_et().date()
    wd = d.weekday()
    if wd > 4:
        raise ValueError("CNBC Top 10 publishes on weekdays only")
    day_name = WEEKDAYS[wd]
    template = os.getenv(
        "CRAMER_CNBC_URL_TEMPLATE",
        "https://www.cnbc.com/{year}/{month:02d}/{day:02d}/"
        "jim-cramers-top-10-things-to-watch-in-the-stock-market-{weekday}.html",
    )
    return template.format(year=d.year, month=d.month, day=d.day, weekday=day_name)


def poll_window_open(dt: datetime | None = None) -> tuple[bool, str]:
    """True between CRAMER_CNBC_POLL_START_ET and END on a weekday."""
    dt = dt or now_et()
    if dt.weekday() >= 5:
        return False, "weekend"
    start = _parse_et_time(os.getenv("CRAMER_CNBC_POLL_START_ET", "09:00"), time(9, 0))
    end = _parse_et_time(os.getenv("CRAMER_CNBC_POLL_END_ET", "11:30"), time(11, 30))
    t = dt.time()
    if t < start:
        return False, f"before_{start.strftime('%H:%M')}_ET"
    if t >= end:
        return False, f"after_{end.strftime('%H:%M')}_ET"
    return True, "poll_open"


def _load_cnbc_sync() -> dict:
    if not CNBC_SYNC_PATH.is_file():
        return {}
    try:
        return json.loads(CNBC_SYNC_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cnbc_sync(data: dict) -> None:
    CNBC_SYNC_PATH.parent.mkdir(parents=True, exist_ok=True)
    CNBC_SYNC_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def already_ingested_today(for_day: date | None = None) -> bool:
    d = (for_day or now_et().date()).isoformat()
    st = _load_cnbc_sync()
    if st.get("date") != d or not st.get("ingested"):
        return False
    if st.get("ai_pending"):
        return False
    return True


def _strip_html(html: str) -> str:
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.I | re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _extract_article_body(html: str) -> str:
    """Pull Top 10 prose from CNBC HTML."""
    for m in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        re.I | re.S,
    ):
        try:
            blob = json.loads(m.group(1))
            items = blob if isinstance(blob, list) else [blob]
            for item in items:
                if not isinstance(item, dict):
                    continue
                body = item.get("articleBody") or item.get("description") or ""
                if body and TOP10_MARKERS.search(body):
                    return str(body).strip()
        except Exception:
            continue
    text = _strip_html(html)
    for marker in (
        r"My top 10 things to watch",
        r"top 10 things to watch in the stock market",
    ):
        m = re.search(marker, text, re.I)
        if m:
            chunk = text[m.start() : m.start() + 14000]
            end = chunk.lower().find("sign up for my top 10 morning thoughts")
            if end > 200:
                chunk = chunk[:end]
            return chunk.strip()
    return ""


def _is_valid_top10(text: str) -> bool:
    if len(text) < 400:
        return False
    if not TOP10_MARKERS.search(text):
        return False
    if len(NUMBERED_ITEM.findall(text)) < 3:
        return False
    return True


def _normalize_for_parser(raw: str) -> str:
    """Ensure numbered items 1–10 are on separate lines for the morning_club parser."""
    t = raw.replace("\u00a0", " ").replace("&amp;", "&").replace("&#39;", "'")
    m = re.search(r"\b1\.\s+", t)
    if m:
        t = t[m.start() :]
    end = t.lower().find("sign up for my top 10 morning thoughts")
    if end > 100:
        t = t[:end]

    def _item_break(match: re.Match) -> str:
        n = int(match.group(1))
        if 1 <= n <= 10:
            return f"\n\n{n}. "
        return match.group(0)

    t = re.sub(r"(?<=\.)\s+(\d{1,2})\.\s+", _item_break, t)
    return t.strip()


def fetch_cnbc_top10(for_day: date | None = None) -> tuple[str, str] | None:
    """
    GET today's CNBC Top 10 URL. Returns (url, body) if published, else None.
    """
    if not _enabled():
        return None
    try:
        url = cnbc_top10_url(for_day)
    except ValueError:
        return None
    try:
        r = requests.get(
            url,
            timeout=float(os.getenv("CRAMER_FETCH_TIMEOUT_SEC", "12")),
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml",
            },
            allow_redirects=True,
        )
    except Exception as e:
        log.debug("[CRAMER_CNBC] fetch %s: %s", url, e)
        return None
    if r.status_code == 404:
        return None
    if r.status_code != 200:
        log.debug("[CRAMER_CNBC] HTTP %s for %s", r.status_code, url)
        return None
    body = _extract_article_body(r.text)
    if not _is_valid_top10(body):
        return None
    return url, _normalize_for_parser(body)


def poll_and_ingest_cnbc_top10(*, force: bool = False) -> dict:
    """Fetch today's CNBC Top 10 if live; ingest into morning_club + conviction."""
    report: dict = {
        "ok": False,
        "ingested": False,
        "skipped": False,
        "url": "",
        "reason": "",
    }
    if not _enabled():
        report["reason"] = "CRAMER_CNBC_TOP10_ENABLED=false"
        return report

    today = now_et().date()
    if today.weekday() >= 5:
        report["reason"] = "weekend"
        return report

    if not force and already_ingested_today(today):
        st = _load_cnbc_sync()
        report["ok"] = True
        report["skipped"] = True
        report["url"] = st.get("url", "")
        report["reason"] = "already_ingested_today"
        return report

    hit = fetch_cnbc_top10(today)
    if not hit:
        report["reason"] = "not_published_yet"
        report["url"] = cnbc_top10_url(today)
        return report

    url, body = hit
    report["url"] = url

    from intel.morning_club_intel import ingest_morning_email

    doc = ingest_morning_email(body, source=f"cnbc_top10:{url}")
    ai_pending = (
        "ai" not in str(doc.get("parser", ""))
        and os.getenv("USE_CRAMER_AI_ANALYSIS", "true").lower() in ("1", "true", "yes")
    )
    try:
        from intel.club_conviction_engine import refresh_dynamic_conviction

        refresh_dynamic_conviction()
    except Exception:
        pass

    _save_cnbc_sync(
        {
            "date": today.isoformat(),
            "ingested": not ai_pending,
            "ai_pending": ai_pending,
            "url": url,
            "ingested_at_utc": datetime.now(timezone.utc).isoformat(),
            "tickers": len(doc.get("tickers") or {}),
            "market_tone": doc.get("market_tone"),
            "parser": doc.get("parser"),
            "ai_confidence": doc.get("ai_confidence"),
            "chars": len(body),
        }
    )
    # Mirror into main sync file
    try:
        from intel.cramer_email_fetcher import _save_sync, _text_hash

        _save_sync(
            {
                "date": today.isoformat(),
                "content_hash": _text_hash(body),
                "synced_at_utc": datetime.now(timezone.utc).isoformat(),
                "source": "cnbc_top10",
                "url": url,
                "tickers": len(doc.get("tickers") or {}),
                "market_tone": doc.get("market_tone"),
            }
        )
    except Exception:
        pass

    report["ok"] = True
    report["ingested"] = True
    report["tickers"] = len(doc.get("tickers") or {})
    report["market_tone"] = doc.get("market_tone")
    log.warning(
        "[CRAMER_CNBC] ingested Top 10 from %s — %d tickers tone=%s",
        url,
        report["tickers"],
        doc.get("market_tone"),
    )
    return report
