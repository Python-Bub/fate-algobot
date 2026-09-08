"""Polygon batch snapshots — one request covers many tickers."""

from __future__ import annotations

import os

import requests

from utils import log


def fetch_snapshots(symbols: list[str]) -> dict[str, dict]:
    key = (os.getenv("POLYGON_API_KEY") or "").strip()
    if not key or os.getenv("POLYGON_USE_SNAPSHOTS", "true").lower() not in ("1", "true", "yes"):
        return {}
    syms = [s.strip().upper() for s in symbols if s][:50]
    if not syms:
        return {}
    cache_key = ",".join(sorted(syms))
    from intel.api_budget import cache_get, cache_set

    cached = cache_get("polygon_snap", cache_key)
    if isinstance(cached, dict):
        return cached
    from intel.api_coverage import allow_provider

    ok, reason = allow_provider("polygon")
    if not ok:
        log.debug("[POLYGON] snapshots skipped: %s", reason)
        return {}
    tickers = ",".join(syms)
    url = f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers"
    try:
        r = requests.get(
            url,
            params={"tickers": tickers, "apiKey": key},
            timeout=float(os.getenv("POLYGON_TIMEOUT_SEC", "12")),
        )
        if r.status_code != 200:
            return {}
        from intel.api_budget import record

        record("polygon")
        body = r.json() or {}
        out: dict[str, dict] = {}
        for row in body.get("tickers") or []:
            t = str(row.get("ticker") or "").upper()
            if t:
                out[t] = row
        ttl = float(os.getenv("INTEL_CACHE_POLYGON_TTL_SEC", "300"))
        cache_set("polygon_snap", cache_key, out, ttl_sec=ttl)
        return out
    except Exception as e:
        log.debug("[POLYGON] batch snapshot failed: %s", e)
        return {}
