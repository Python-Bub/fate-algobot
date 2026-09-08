"""Today's liquid gainers — scan them; do not chase post-print exhaust rips."""

from __future__ import annotations

import os
import time
from typing import Any

_CACHE: tuple[float, list[str]] = (0.0, [])
_TTL = 900.0

_YAHOO = (
    "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
    "?count=25&formatted=false&scrIds=day_gainers"
)


def _f(v: Any) -> float:
    if v is None:
        return 0.0
    if isinstance(v, dict):
        v = v.get("raw")
    try:
        return float(v or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _liquid(q: dict[str, Any]) -> bool:
    sym = str(q.get("symbol") or "").strip().upper()
    if not sym or "." in sym or "-" in sym or "/" in sym:
        return False
    if len(sym) > 5:
        return False
    px = _f(q.get("regularMarketPrice"))
    chg = _f(q.get("regularMarketChangePercent"))
    vol = _f(q.get("regularMarketVolume"))
    if px < float(os.getenv("DAY_MOVER_MIN_PX", "8")):
        return False
    # Real session pop, not a +100% print gap and not a 0.4% drift.
    if chg < float(os.getenv("DAY_MOVER_MIN_PCT", "4")):
        return False
    if chg > float(os.getenv("DAY_MOVER_MAX_PCT", "22")):
        return False
    if vol < float(os.getenv("DAY_MOVER_MIN_VOL", "800000")):
        return False
    return True


def skip_post_print_chase(
    ticker: str,
    *,
    ret_1d: float | None = None,
    mom_5d: float | None = None,
) -> tuple[bool, str]:
    """True when a live Phase-3 / binary already printed and the tape is exhausted."""
    try:
        from analytics.event_calendar import exhaustion, ticker_row

        rec = ticker_row(ticker) or {}
        live = float(rec.get("live_binary") or 0.0)
        ex = exhaustion(ret_1d, mom_5d, live=live)
        if ex >= 0.45:
            return True, f"post_print_exhaust={ex:.2f}"
    except Exception:
        return False, ""
    return False, ""


def today_liquid_gainers(*, limit: int = 12, fetch=None) -> list[str]:
    """Yahoo day-gainers, filtered to names we can actually trade this session."""
    global _CACHE
    now = time.time()
    if fetch is None and now - _CACHE[0] < _TTL and _CACHE[1]:
        return list(_CACHE[1])[:limit]
    quotes: list[dict[str, Any]] = []
    if fetch is not None:
        quotes = list(fetch() or [])
    else:
        try:
            from intel.http_scheduler import get_json

            js = get_json(_YAHOO, ttl_sec=_TTL) or {}
            quotes = (((js.get("finance") or {}).get("result") or [{}])[0]).get("quotes") or []
        except Exception:
            quotes = []
    out: list[str] = []
    seen: set[str] = set()
    for q in quotes:
        if not isinstance(q, dict) or not _liquid(q):
            continue
        sym = str(q.get("symbol") or "").strip().upper()
        if sym in seen:
            continue
        chg = _f(q.get("regularMarketChangePercent")) / 100.0
        skip, _why = skip_post_print_chase(sym, ret_1d=chg, mom_5d=chg)
        if skip:
            continue
        seen.add(sym)
        out.append(sym)
        if len(out) >= int(limit):
            break
    if fetch is None:
        _CACHE = (now, out)
    return out
