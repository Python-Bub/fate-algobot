"""Cycle price/news sources on rate-limit — never sit idle waiting on one API.

Order (prices): polygon → alpaca → yahoo → cache
On 429 / cooldown: mark source cooling, advance cursor, try next.
When cooldown expires, source re-enters the ring.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = Path(os.getenv("SOURCE_ROTATOR_STATE", str(ROOT / "data" / "ops" / "source_rotator_state.json")))

_lock = threading.Lock()
_DEFAULT_COOLDOWN = {
    "yahoo": float(os.getenv("YAHOO_RATE_LIMIT_COOLDOWN_SEC", "90")),
    "alpaca": float(os.getenv("ALPACA_DATA_429_COOLDOWN_SEC", "30")),
    "polygon": float(os.getenv("POLYGON_RATE_LIMIT_COOLDOWN_SEC", "60")),
    "finnhub": float(os.getenv("FINNHUB_429_COOLDOWN_SEC", "45")),
    "newsapi": float(os.getenv("NEWSAPI_COOLDOWN_SEC", str(6 * 3600))),
    "google_cse": float(os.getenv("GOOGLE_CSE_COOLDOWN_SEC", "120")),
}


def _load() -> dict[str, Any]:
    try:
        if STATE_PATH.is_file():
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"cooling_until": {}, "cursor": 0, "hits": {}, "fails": {}}


def _save(st: dict[str, Any]) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(st, indent=2) + "\n", encoding="utf-8")
    except Exception:
        pass


def note_limited(source: str, *, seconds: float | None = None) -> None:
    src = source.strip().lower()
    sec = float(seconds if seconds is not None else _DEFAULT_COOLDOWN.get(src, 60.0))
    with _lock:
        st = _load()
        cool = dict(st.get("cooling_until") or {})
        cool[src] = time.time() + sec
        st["cooling_until"] = cool
        fails = dict(st.get("fails") or {})
        fails[src] = int(fails.get(src, 0)) + 1
        st["fails"] = fails
        _save(st)


def is_cooling(source: str) -> bool:
    src = source.strip().lower()
    with _lock:
        st = _load()
        until = float((st.get("cooling_until") or {}).get(src) or 0)
    return time.time() < until


def available_sources(order: list[str] | None = None) -> list[str]:
    order = order or [
        x.strip().lower()
        for x in os.getenv("PRICE_SOURCE_ROTATION", "polygon,alpaca,yahoo").split(",")
        if x.strip()
    ]
    return [s for s in order if not is_cooling(s)]


def next_source(order: list[str] | None = None) -> str | None:
    """Round-robin among non-cooling sources."""
    order = order or [
        x.strip().lower()
        for x in os.getenv("PRICE_SOURCE_ROTATION", "polygon,alpaca,yahoo").split(",")
        if x.strip()
    ]
    with _lock:
        st = _load()
        cool = st.get("cooling_until") or {}
        now = time.time()
        open_srcs = [s for s in order if now >= float(cool.get(s) or 0)]
        if not open_srcs:
            # All cooling — pick the one that wakes soonest
            soon = sorted(order, key=lambda s: float(cool.get(s) or 0))
            return soon[0] if soon else None
        cur = int(st.get("cursor") or 0) % len(open_srcs)
        pick = open_srcs[cur]
        st["cursor"] = cur + 1
        hits = dict(st.get("hits") or {})
        hits[pick] = int(hits.get(pick, 0)) + 1
        st["hits"] = hits
        _save(st)
        return pick


def fetch_daily_rotated(
    ticker: str,
    start: str,
    end: str | None = None,
    *,
    min_rows: int = 20,
) -> tuple[Any, str]:
    """Try sources in rotation until we get a non-empty OHLCV frame."""
    import pandas as pd
    from multi_source_data import fetch_alpaca_daily, fetch_polygon_daily, fetch_yahoo

    order = [
        x.strip().lower()
        for x in os.getenv("PRICE_SOURCE_ROTATION", "polygon,alpaca,yahoo").split(",")
        if x.strip()
    ]
    tried: list[str] = []
    last_err = ""
    # Try each available source once, then force-try cooling ones if all empty
    candidates = available_sources(order) or list(order)
    for src in candidates:
        tried.append(src)
        try:
            if src == "polygon":
                df = fetch_polygon_daily(ticker, start, end)
            elif src == "alpaca":
                df = fetch_alpaca_daily(ticker, start, end)
            else:
                if is_cooling("yahoo"):
                    continue
                df = fetch_yahoo(ticker, start, end)
            if df is not None and not getattr(df, "empty", True) and len(df) >= min_rows:
                return df, src
        except Exception as e:
            msg = str(e).lower()
            last_err = str(e)
            if "429" in msg or "rate limit" in msg or "too many" in msg:
                note_limited(src)
            continue
    # Last resort: any cache/yahoo ignoring cooldown briefly
    try:
        df = fetch_yahoo(ticker, start, end)
        if df is not None and not df.empty:
            return df, "yahoo_fallback"
    except Exception as e:
        last_err = str(e)
    return pd.DataFrame(), f"empty tried={tried} err={last_err}"


def call_with_rotation(
    fns: dict[str, Callable[[], Any]],
    *,
    order: list[str] | None = None,
    accept: Callable[[Any], bool] | None = None,
) -> tuple[Any, str]:
    """Generic rotator for news/LLM-ish callables keyed by source name."""
    order = order or list(fns.keys())
    accept = accept or (lambda x: x is not None)
    for src in available_sources(order) or order:
        if src not in fns:
            continue
        try:
            out = fns[src]()
            if accept(out):
                return out, src
        except Exception as e:
            msg = str(e).lower()
            if "429" in msg or "rate limit" in msg or "too many" in msg:
                note_limited(src)
            continue
    return None, "exhausted"
