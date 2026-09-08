"""Local HTTP scheduler — stay online without burning provider quotas.

This is our own rate-limit software: per-host token buckets, disk cache,
and 429 cooldown. We never bypass a provider's 429; we wait, rotate, or
serve cache so the bot keeps reading news/wiki/SEC instead of going idle.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "data" / "intel_cache" / "http"
STATE_PATH = ROOT / "data" / "ops" / "http_scheduler.json"

_lock = threading.Lock()
_last: dict[str, float] = {}
_cool: dict[str, float] = {}

# Polite defaults (requests per second). Override with HTTP_RPS_<HOST>.
_DEFAULT_RPS = {
    "en.wikipedia.org": 1.0,
    "www.sec.gov": 8.0,
    "data.sec.gov": 8.0,
    "efts.sec.gov": 2.0,
    "query2.finance.yahoo.com": 1.5,
    "query1.finance.yahoo.com": 1.5,
    "news.google.com": 0.8,
    "api.stocktwits.com": 0.3,
    "api.duckduckgo.com": 0.5,
    "clinicaltrials.gov": 0.4,
    "feeds.bbci.co.uk": 0.4,
    "feeds.bbci.co.uk": 0.4,
    "rss.cnn.com": 0.4,
    "www.npr.org": 0.4,
}


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _rps(host: str) -> float:
    env = os.getenv(f"HTTP_RPS_{host.replace('.', '_').upper()}", "").strip()
    if env:
        try:
            return max(0.05, float(env))
        except ValueError:
            pass
    return float(_DEFAULT_RPS.get(host, float(os.getenv("HTTP_RPS_DEFAULT", "1.0"))))


def _min_interval(host: str) -> float:
    return 1.0 / max(_rps(host), 0.05)


def is_cooling(host: str) -> bool:
    until = _cool.get(host, 0.0)
    return time.time() < until


def note_limited(host: str, *, seconds: float | None = None) -> None:
    sec = float(seconds if seconds is not None else os.getenv("HTTP_429_COOLDOWN_SEC", "45"))
    _cool[host] = time.time() + max(5.0, sec)
    try:
        from data_platform.source_rotator import note_limited as _rot

        _rot(host.split(".")[0], seconds=sec)
    except Exception:
        pass


def wait_host(host: str, *, block: bool = True) -> bool:
    """Pace calls to `host`. Return False if cooling and non-blocking."""
    if not host:
        return True
    if is_cooling(host):
        if not block:
            return False
        time.sleep(max(0.05, _cool[host] - time.time()))
    need = _min_interval(host)
    with _lock:
        last = _last.get(host, 0.0)
        gap = time.time() - last
        if gap < need:
            if not block:
                return False
            time.sleep(need - gap)
        _last[host] = time.time()
    return True


def _cache_path(url: str, extra: str = "") -> Path:
    h = hashlib.sha256(f"{url}|{extra}".encode()).hexdigest()[:32]
    return CACHE_DIR / f"{h}.json"


def cache_get(url: str, *, extra: str = "", ttl_sec: float = 1800.0) -> Any | None:
    if os.getenv("HTTP_CACHE_ENABLED", "true").lower() not in ("1", "true", "yes"):
        return None
    p = _cache_path(url, extra)
    if not p.is_file():
        return None
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    ttl = float(doc.get("ttl_sec", ttl_sec))
    if time.time() - float(doc.get("ts", 0)) > ttl:
        return None
    return doc.get("payload")


def cache_set(url: str, payload: Any, *, extra: str = "", ttl_sec: float = 1800.0) -> None:
    if os.getenv("HTTP_CACHE_ENABLED", "true").lower() not in ("1", "true", "yes"):
        return
    p = _cache_path(url, extra)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(
        json.dumps({"ts": time.time(), "ttl_sec": ttl_sec, "payload": payload}, indent=0),
        encoding="utf-8",
    )
    os.replace(tmp, p)


def get_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 12.0,
    ttl_sec: float = 1800.0,
    cache_key: str = "",
    allow_cache_on_error: bool = True,
) -> Any | None:
    """GET JSON with cache + host pacing. Returns parsed JSON or None."""
    import requests

    host = _host(url)
    extra = cache_key or (json.dumps(params, sort_keys=True) if params else "")
    hit = cache_get(url, extra=extra, ttl_sec=ttl_sec)
    if hit is not None:
        return hit
    if host and not wait_host(host, block=os.getenv("HTTP_BLOCK_ON_COOLDOWN", "false").lower() in ("1", "true", "yes")):
        if allow_cache_on_error:
            stale = _stale_cache(url, extra)
            if stale is not None:
                return stale
        return None
    hdrs = {
        "User-Agent": os.getenv(
            "FATE_HTTP_USER_AGENT",
            "FATE-AlgoBot/1.4 (research; paper-trading; +https://github.com/local)",
        ),
        "Accept": "application/json, text/html;q=0.8, */*;q=0.5",
    }
    if headers:
        hdrs.update(headers)
    try:
        r = requests.get(url, params=params, headers=hdrs, timeout=timeout)
        if r.status_code == 429:
            note_limited(host or "unknown")
            if allow_cache_on_error:
                return _stale_cache(url, extra)
            return None
        if r.status_code >= 400:
            return _stale_cache(url, extra) if allow_cache_on_error else None
        ct = (r.headers.get("content-type") or "").lower()
        if "json" in ct or (r.text or "").lstrip()[:1] in ("{", "["):
            payload = r.json()
        else:
            payload = {"_text": r.text[:200_000]}
        cache_set(url, payload, extra=extra, ttl_sec=ttl_sec)
        return payload
    except Exception:
        return _stale_cache(url, extra) if allow_cache_on_error else None


def get_text(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 12.0,
    ttl_sec: float = 1800.0,
    max_chars: int = 120_000,
) -> str:
    doc = get_json(url, headers=headers, timeout=timeout, ttl_sec=ttl_sec)
    if not isinstance(doc, dict):
        return ""
    if "_text" in doc:
        return str(doc.get("_text") or "")[:max_chars]
    return json.dumps(doc)[:max_chars]


def _stale_cache(url: str, extra: str) -> Any | None:
    """Serve expired cache rather than going dark after a 429."""
    p = _cache_path(url, extra)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("payload")
    except Exception:
        return None
