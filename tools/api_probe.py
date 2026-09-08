#!/usr/bin/env python3
"""HTTP probes for ./run_all.sh keys/status — avoids burning NewsAPI quota on every status."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
PROBE_CACHE = ROOT / "data" / "cache" / "api_probe_cache.json"
_FRED_HEADERS = {"User-Agent": os.getenv("FRED_USER_AGENT", "FATE_AlgoBot/1.0 (macro)")}


def _load_cache() -> dict:
    if not PROBE_CACHE.is_file():
        return {}
    try:
        return json.loads(PROBE_CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(data: dict) -> None:
    PROBE_CACHE.parent.mkdir(parents=True, exist_ok=True)
    PROBE_CACHE.write_text(json.dumps(data, indent=0), encoding="utf-8")


def _fred_observations(key: str) -> tuple[int, str]:
    try:
        r = requests.get(
            "https://api.stlouisfed.org/fred/series/observations",
            params={
                "series_id": "DGS10",
                "api_key": key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 1,
            },
            headers=_FRED_HEADERS,
            timeout=12,
        )
        if r.status_code == 200:
            obs = (r.json() or {}).get("observations") or []
            if obs:
                return 200, "OK"
            return 200, "OK (empty)"
        if r.status_code == 403 and "Access Denied" in (r.text or ""):
            return 403, "BLOCKED (WAF)"
        try:
            err = (r.json() or {}).get("error_message") or ""
        except Exception:
            err = (r.text or "")[:80]
        return r.status_code, err or "FAIL"
    except Exception as e:
        return 0, f"{type(e).__name__}"


def _fred_yfinance_ok() -> bool:
    if os.getenv("FRED_YFINANCE_FALLBACK", "true").lower() not in ("1", "true", "yes"):
        return False
    try:
        import yfinance as yf

        d10 = yf.download("^TNX", period="5d", interval="1d", progress=False, auto_adjust=True)
        d5 = yf.download("^FVX", period="5d", interval="1d", progress=False, auto_adjust=True)
        if d10 is None or d10.empty or d5 is None or d5.empty:
            return False
        return True
    except Exception:
        return False


def probe_fred() -> tuple[str, str]:
    key = os.getenv("FRED_API_KEY", "").strip()
    if not key:
        return "FRED", "no key"
    code, detail = _fred_observations(key)
    if code == 200:
        return "FRED", f"HTTP {code} {detail}"
    if _fred_yfinance_ok():
        suffix = "OK (yfinance fallback)"
        if code == 403:
            suffix = "OK (yfinance fallback; FRED WAF blocked — renew key at fred.stlouisfed.org)"
        return "FRED", suffix
    return "FRED", f"HTTP {code} {detail}"


def probe_newsapi() -> tuple[str, str]:
    key = os.getenv("NEWSAPI_KEY", "").strip()
    if not key:
        return "NewsAPI", "no key"
    if os.getenv("USE_NEWSAPI", "true").lower() in ("0", "false", "no"):
        return "NewsAPI", "disabled (USE_NEWSAPI=false)"

    ttl = float(os.getenv("NEWSAPI_PROBE_CACHE_SECONDS", str(24 * 3600)))
    cache = _load_cache()
    ent = cache.get("newsapi") or {}
    if ent.get("t") and time.time() - float(ent["t"]) < ttl:
        return "NewsAPI", str(ent.get("label", "cached"))

    if os.getenv("NEWSAPI_STATUS_PROBE", "false").lower() not in ("1", "true", "yes"):
        return "NewsAPI", "OK (probe skipped — Finnhub primary; saves free-tier quota)"

    try:
        r = requests.get(
            "https://newsapi.org/v2/everything",
            params={"q": "markets", "pageSize": 1, "apiKey": key},
            timeout=8,
        )
        label: str
        if r.status_code == 200:
            label = "HTTP 200 OK"
        elif r.status_code == 429:
            label = "HTTP 429 QUOTA (key valid; Finnhub-only until reset — not a hard fail)"
        elif r.status_code == 401:
            label = "HTTP 401 invalid key"
        else:
            label = f"HTTP {r.status_code} FAIL"
        cache["newsapi"] = {"t": time.time(), "label": label}
        _save_cache(cache)
        return "NewsAPI", label
    except Exception as e:
        return "NewsAPI", f"ERR {type(e).__name__}"


def main() -> int:
    sys.path.insert(0, str(ROOT))
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")

    probes = [
        probe_fred(),
        probe_newsapi(),
    ]
    for name, label in probes:
        print(f"{name}\t{label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
