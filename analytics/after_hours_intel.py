"""After-hours / pre-market sneak peek — overnight investor lean before the next open.

Uses yfinance extended quote fields (postMarket / preMarket vs regular close).
Cached per symbol; no disk writes.

Env:
- USE_AFTER_HOURS=true
- AH_CACHE_SEC=900
"""

from __future__ import annotations

import os
import time
from typing import Any

import numpy as np

_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def after_hours_enabled() -> bool:
    return os.getenv("USE_AFTER_HOURS", "true").lower() in ("1", "true", "yes")


def _clip11(x: float) -> float:
    return float(np.clip(x, -1.0, 1.0))


def _investor_read(ah_ret: float, session: str) -> str:
    pct = ah_ret * 100.0
    if ah_ret >= 0.015:
        return f"{session} buyers active (+{pct:.1f}%) — sneak peek bullish into next open"
    if ah_ret <= -0.015:
        return f"{session} sellers active ({pct:.1f}%) — caution into next open"
    if ah_ret >= 0.004:
        return f"{session} slightly green — mild optimism overnight"
    if ah_ret <= -0.004:
        return f"{session} slightly red — mild worry overnight"
    return f"{session} quiet — no strong overnight lean"


def fetch_after_hours_snapshot(symbol: str, *, force: bool = False) -> dict[str, Any]:
    """Return AH/pre snapshot: ah_return_pct, ah_tilt [-1,1], investor_read."""
    sym = (symbol or "").strip().upper()
    neutral: dict[str, Any] = {
        "ok": False,
        "symbol": sym,
        "session": "closed",
        "ah_return_pct": 0.0,
        "ah_tilt": 0.0,
        "investor_read": "no extended-hours data",
        "regular_close": None,
        "extended_price": None,
    }
    if not sym:
        return neutral
    if not after_hours_enabled() and not force:
        return neutral

    ttl = float(os.getenv("AH_CACHE_SEC", "900"))
    now = time.time()
    if not force and sym in _CACHE and (now - _CACHE[sym][0]) < ttl:
        return dict(_CACHE[sym][1])

    out = dict(neutral)
    try:
        import yfinance as yf

        info = yf.Ticker(sym).info or {}
        reg_close = info.get("regularMarketPreviousClose") or info.get("previousClose")
        post_p = info.get("postMarketPrice")
        post_chg = info.get("postMarketChangePercent")
        pre_p = info.get("preMarketPrice")
        pre_chg = info.get("preMarketChangePercent")

        ext_p = post_p if post_p not in (None, 0) else pre_p
        ext_chg = post_chg if post_chg is not None else pre_chg
        session = "post_market" if post_p not in (None, 0) else ("pre_market" if pre_p not in (None, 0) else "regular")

        ah_ret = 0.0
        if ext_chg is not None:
            ah_ret = float(ext_chg) / 100.0
        elif ext_p is not None and reg_close not in (None, 0):
            ah_ret = float(ext_p) / float(reg_close) - 1.0
        else:
            _CACHE[sym] = (now, neutral)
            return neutral

        ah_tilt = _clip11(float(np.tanh(ah_ret * 18.0)))
        out = {
            "ok": True,
            "symbol": sym,
            "session": session,
            "ah_return_pct": float(ah_ret),
            "ah_tilt": ah_tilt,
            "investor_read": _investor_read(ah_ret, session.replace("_", " ")),
            "regular_close": float(reg_close) if reg_close is not None else None,
            "extended_price": float(ext_p) if ext_p is not None else None,
        }
    except Exception:
        out = neutral

    _CACHE[sym] = (now, out)
    return dict(out)


def ah_rank_boost(ah: dict[str, Any]) -> float:
    if not ah.get("ok"):
        return 0.0
    return float(np.tanh(float(ah.get("ah_tilt", 0.0)) * 1.3))
