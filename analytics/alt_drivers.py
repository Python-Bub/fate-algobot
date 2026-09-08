"""Unified rank boost for crypto + commodities + miners.

Equities get 0 — this does not steal NVDA's score. HFT sleeve stays 0
(the experimental crypto HFT daemon has its own gate). Fortress / weekly /
longterm mix this in via RANK_W_ALT_DRIVERS.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from crypto_universe import is_crypto_symbol

ROOT = Path(__file__).resolve().parents[1]
SNAP_PATH = ROOT / "data" / "intel" / "alt_drivers_latest.json"

_CRYPTO_ETFS = frozenset({"IBIT", "BITO", "GBTC", "ETHA", "ETHE"})


def _news_tilt(ticker: str) -> float:
    if os.getenv("ALT_DRIVERS_NEWS", "true").lower() not in ("1", "true", "yes", "on"):
        return 0.0
    try:
        from intel.open_web_intel import open_web_boost_for

        v = float(open_web_boost_for(ticker) or 0.0)
        if abs(v) > 1.5:
            v = max(-1.0, min(1.0, v / 5.0))
        return max(-1.0, min(1.0, v))
    except Exception:
        return 0.0


def alt_rank_boost(
    ticker: str,
    row: Any | None = None,
    *,
    fetch=None,
) -> tuple[float, dict[str, Any]]:
    """Return (boost in [-1,1], meta). 0 for ordinary equities."""
    t = (ticker or "").strip().upper()
    if not t:
        return 0.0, {"reason": "empty"}
    news = 0.0
    try:
        if row is not None:
            if isinstance(row, dict):
                news = float(row.get("sent") or row.get("sentiment") or 0.0 or 0)
            else:
                news = float(getattr(row, "sent", 0.0) or 0.0)
    except (TypeError, ValueError):
        news = 0.0
    if abs(news) < 1e-9:
        news = _news_tilt(t)

    if is_crypto_symbol(t) or t in _CRYPTO_ETFS:
        from analytics.crypto_math import score_crypto

        cs = score_crypto(t if is_crypto_symbol(t) else ("ETH-USD" if t in ("ETHA", "ETHE") else "BTC-USD"), fetch=fetch, news_tilt=news)
        meta = {"family": "crypto", **cs.as_dict()}
        _maybe_snap(t, meta)
        return float(cs.score), meta

    from analytics.commodity_math import classify_commodity, score_commodity

    if not classify_commodity(t):
        return 0.0, {"reason": "not_alt", "ticker": t}
    cm = score_commodity(t, fetch=fetch)
    meta = {"family": "commodity", **cm.as_dict()}
    _maybe_snap(t, meta)
    return float(cm.score), meta


_LAST_SNAP = 0.0


def _maybe_snap(ticker: str, meta: dict[str, Any]) -> None:
    global _LAST_SNAP
    now = time.time()
    if now - _LAST_SNAP < 20.0:
        return
    _LAST_SNAP = now
    try:
        SNAP_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {}
        if SNAP_PATH.is_file():
            try:
                payload = json.loads(SNAP_PATH.read_text(encoding="utf-8")) or {}
            except Exception:
                payload = {}
        if not isinstance(payload, dict):
            payload = {}
        by = payload.get("by_ticker") if isinstance(payload.get("by_ticker"), dict) else {}
        by[ticker] = {"ts": now, **meta}
        SNAP_PATH.write_text(
            json.dumps({"ts": now, "by_ticker": by}, indent=0)[:80_000],
            encoding="utf-8",
        )
    except Exception:
        pass
