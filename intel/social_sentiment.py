"""StockTwits public sentiment factor (no API key required for the public stream).

The StockTwits public endpoint `https://api.stocktwits.com/api/2/streams/symbol/{SYM}.json`
returns recent messages tagged with that symbol; many messages carry a `entities.sentiment.basic`
field ("Bullish" / "Bearish"). We aggregate to a `[-1, 1]` score with a small bull/bear bias.

Cached per process to avoid hammering the endpoint inside a single ranker pass.

Toggles:
- `USE_SOCIAL_SENTIMENT=true`   – enable factor (default true)
- `STOCKTWITS_TIMEOUT_SEC=6`    – HTTP timeout
- `STOCKTWITS_MIN_MSGS=8`       – return 0 when fewer messages exist
"""

from __future__ import annotations

import os
import time
from typing import Any

import requests

from utils import log

_STREAM_URL = "https://api.stocktwits.com/api/2/streams/symbol/{sym}.json"
_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_TTL = 900.0  # 15 min
_COOL_UNTIL = 0.0
_DISABLED = False


def _disable(reason: str) -> None:
    global _DISABLED
    if _DISABLED:
        return
    _DISABLED = True
    log.warning("[STOCKTWITS] disabled for this process: %s", reason[:160])


def fetch_stocktwits(symbol: str) -> dict:
    global _COOL_UNTIL
    if _DISABLED:
        return {}
    if time.time() < _COOL_UNTIL:
        return {}
    if os.getenv("USE_SOCIAL_SENTIMENT", "true").lower() not in ("1", "true", "yes"):
        return {}
    sym = symbol.strip().upper()
    now = time.time()
    if sym in _CACHE and (now - _CACHE[sym][0]) < _CACHE_TTL:
        return _CACHE[sym][1]
    try:
        from intel.http_scheduler import wait_host

        if not wait_host("api.stocktwits.com", block=False):
            return {}
    except Exception:
        pass
    try:
        r = requests.get(
            _STREAM_URL.format(sym=sym),
            timeout=float(os.getenv("STOCKTWITS_TIMEOUT_SEC", "6")),
            headers={"User-Agent": "FATE_AlgoBot/1.3"},
        )
        if r.status_code in (401, 403):
            _disable(f"HTTP {r.status_code}")
            return {}
        if r.status_code == 429:
            # Cooldown this process; do not kill the social sleeve for the rest of the day.
            _COOL_UNTIL = time.time() + float(os.getenv("STOCKTWITS_429_COOLDOWN_SEC", "900"))
            log.warning("[STOCKTWITS] 429 — cooling %.0fs (not process-killed)", _COOL_UNTIL - time.time())
            try:
                from intel.http_scheduler import note_limited

                note_limited("api.stocktwits.com", seconds=_COOL_UNTIL - time.time())
            except Exception:
                pass
            return {}
        r.raise_for_status()
        js = r.json()
        _CACHE[sym] = (now, js)
        return js
    except Exception as e:
        log.debug("[STOCKTWITS] fetch failed for %s: %s", sym, e)
        return {}


def social_sentiment_score(symbol: str) -> dict:
    """Aggregate bull/bear basic-sentiment counts from StockTwits messages."""
    js = fetch_stocktwits(symbol)
    msgs: list[dict[str, Any]] = list(js.get("messages") or [])
    n_min = int(os.getenv("STOCKTWITS_MIN_MSGS", "8"))
    if len(msgs) < n_min:
        return {
            "score": 0.0,
            "n_messages": len(msgs),
            "n_bull": 0,
            "n_bear": 0,
            "bull_share": 0.5,  # thin sample is neutral, not a fake 0% bull crowd
        }
    bull = 0
    bear = 0
    for m in msgs:
        ent = (m.get("entities") or {}).get("sentiment") or {}
        s = (ent.get("basic") or "").strip().lower()
        if s == "bullish":
            bull += 1
        elif s == "bearish":
            bear += 1
    tot = bull + bear
    if tot == 0:
        return {
            "score": 0.0,
            "n_messages": len(msgs),
            "n_bull": 0,
            "n_bear": 0,
            "bull_share": 0.5,  # unlabeled ≠ bearish
        }
    bull_share = bull / tot
    # Map (bull - bear)/tot to [-1, 1] then dampen tiny samples.
    base = (bull - bear) / tot
    dampen = min(1.0, tot / 25.0)
    return {
        "score": float(base * dampen),
        "n_messages": int(len(msgs)),
        "n_bull": int(bull),
        "n_bear": int(bear),
        "bull_share": float(bull_share),
    }


def social_boost_for(symbol: str) -> float:
    info = social_sentiment_score(symbol)
    gain = float(os.getenv("SOCIAL_BOOST_GAIN", "0.4"))
    return max(-1.0, min(1.0, info.get("score", 0.0) * gain))
