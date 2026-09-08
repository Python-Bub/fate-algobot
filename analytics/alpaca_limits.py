"""Alpaca hard limits — single source of truth for pacing & pre-trade checks.

Basic Trading API market data (free): **200 historical/data HTTP calls per minute**.
We keep a shared token bucket (~180/min) across quote/bars so fortress+HFT+day don't
stampede into HTTP 429. Trading REST also returns X-RateLimit-* headers — honor them.

See data/ops/ALPACA_LIMITS.md for the full catalog.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class LimitHit:
    ok: bool
    reason: str
    retry_after_sec: float = 0.0


# --- Data API RPM (Basic plan = 200/min) ---
_DATA_LOCK = threading.Lock()
_DATA_TOKENS = float(os.getenv("ALPACA_DATA_RPM_BUDGET", "180"))
_DATA_LAST = time.monotonic()
_DATA_COOLDOWN_UNTIL = 0.0
_QUOTE_CACHE: dict[str, tuple[float, tuple[float, float]]] = {}
_ASSET_CACHE: dict[str, tuple[float, dict]] = {}


def data_rpm_budget() -> float:
    return float(os.getenv("ALPACA_DATA_RPM_BUDGET", "180"))


def note_data_429(retry_after: float | None = None) -> None:
    """Call when data.alpaca returns 429 — global cool-down."""
    global _DATA_COOLDOWN_UNTIL
    wait = float(retry_after) if retry_after and retry_after > 0 else float(
        os.getenv("ALPACA_DATA_429_COOLDOWN_SEC", "35")
    )
    with _DATA_LOCK:
        _DATA_COOLDOWN_UNTIL = max(_DATA_COOLDOWN_UNTIL, time.monotonic() + wait)


def acquire_data_token(*, cost: float = 1.0) -> LimitHit:
    """Token-bucket gate before any data.alpaca.markets HTTP call."""
    global _DATA_TOKENS, _DATA_LAST
    rpm = data_rpm_budget()
    with _DATA_LOCK:
        now = time.monotonic()
        if now < _DATA_COOLDOWN_UNTIL:
            return LimitHit(False, "data_429_cooldown", _DATA_COOLDOWN_UNTIL - now)
        # refill
        elapsed = now - _DATA_LAST
        _DATA_LAST = now
        _DATA_TOKENS = min(rpm, _DATA_TOKENS + elapsed * (rpm / 60.0))
        if _DATA_TOKENS < cost:
            need = (cost - _DATA_TOKENS) * (60.0 / rpm)
            return LimitHit(False, "data_rpm_exhausted", need)
        _DATA_TOKENS -= cost
        return LimitHit(True, "ok")


def quote_cache_get(symbol: str) -> tuple[float, float] | None:
    ttl = float(os.getenv("ALPACA_QUOTE_CACHE_SEC", "8"))
    row = _QUOTE_CACHE.get(symbol.upper())
    if not row:
        return None
    ts, qa = row
    if time.time() - ts > ttl:
        return None
    return qa


def quote_cache_put(symbol: str, bid: float, ask: float) -> None:
    _QUOTE_CACHE[symbol.upper()] = (time.time(), (bid, ask))


def honor_rate_limit_headers(resp: Any) -> None:
    """If Alpaca sends Retry-After / X-RateLimit-Remaining=0, cool down."""
    try:
        ra = resp.headers.get("Retry-After")
        rem = resp.headers.get("X-RateLimit-Remaining")
        if resp.status_code == 429:
            note_data_429(float(ra) if ra else None)
            return
        if rem is not None and float(rem) <= 0:
            note_data_429(float(ra) if ra else 15.0)
    except Exception:
        pass


# --- Trading constraints ---

def min_order_notional() -> float:
    return float(os.getenv("ALPACA_MIN_ORDER_NOTIONAL", os.getenv("MIN_ORDER_NOTIONAL", "1")))


def max_open_orders_soft() -> int:
    """Soft cap — Alpaca doesn't publish a hard number; we self-limit spam."""
    return int(os.getenv("ALPACA_MAX_OPEN_ORDERS", "200"))


def trading_orders_per_min_soft() -> int:
    return int(os.getenv("ALPACA_ORDERS_PER_MIN_SOFT", "200"))


_ORDER_TS: list[float] = []
_ORDER_LOCK = threading.Lock()


def can_submit_order_pace(now: float | None = None) -> LimitHit:
    """Soft trade-API pacing — rolling 60s window, not a calendar-minute wall.

    A submit at :59 and a fill at :01 are one trade, not a new minute bucket.
    """
    lim = trading_orders_per_min_soft()
    ts = time.time() if now is None else float(now)
    with _ORDER_LOCK:
        while _ORDER_TS and ts - _ORDER_TS[0] > 60.0:
            _ORDER_TS.pop(0)
        if len(_ORDER_TS) >= lim:
            wait = 60.0 - (ts - _ORDER_TS[0])
            return LimitHit(False, "orders_per_min_soft", max(0.1, wait))
        _ORDER_TS.append(ts)
        return LimitHit(True, "ok")


def available_qty_for_sell(pos: dict | None, *, open_sell_qty: float = 0.0) -> float:
    """Qty free to sell = position qty − held_for_orders / open sells."""
    if not pos:
        return 0.0
    qty = abs(float(pos.get("qty") or 0))
    held = float(pos.get("held_for_orders") or 0)
    # Some payloads omit held_for_orders — use open_sell_qty from order book
    locked = max(held, open_sell_qty)
    return max(0.0, qty - locked)


def asset_fractionable(symbol: str, asset: dict | None = None) -> bool:
    if asset and "fractionable" in asset:
        return bool(asset.get("fractionable"))
    # Unknown → assume True for mega liquid names; False for microcaps if flagged
    return os.getenv("ALPACA_ASSUME_FRACTIONABLE", "true").lower() in ("1", "true", "yes")


def snap_qty_for_asset(qty: float, *, fractionable: bool) -> float:
    if fractionable:
        return float(qty)
    # Whole shares only
    return float(int(qty))


def intraday_margin_notes() -> dict[str, Any]:
    """PDT retired July 2026 — use dynamic buying_power / IMD instead of daytrade_count."""
    return {
        "pdt_retired": True,
        "pdt_retire_date": "2026-07-06",
        "use_field": "buying_power",
        "deprecated_fields": [
            "pattern_day_trader",
            "daytrade_count",
            "daytrading_buying_power",
            "last_daytrading_buying_power",
            "dtbp_check",
        ],
        "imd": "Intraday Margin Deficit — resolve within ~5 business days or 90-day freeze risk",
        "min_equity_margin": 2000.0,
    }


def preflight_buy(
    *,
    symbol: str,
    notional: float,
    buying_power: float,
    fractionable: bool = True,
) -> LimitHit:
    if notional < min_order_notional():
        return LimitHit(False, f"below_min_notional_{min_order_notional()}")
    if notional > buying_power * float(os.getenv("ALPACA_BP_USE_FRAC", "0.95")):
        return LimitHit(False, "insufficient_buying_power")
    # Pace is reserved only at the actual POST (submit_limit_order). Checking
    # here used to consume 2–3 slots per order and stall far below 200/min.
    if not fractionable and notional < 5.0:
        return LimitHit(False, "non_fractionable_notional_too_small")
    return LimitHit(True, "ok")


def summarize_for_ops() -> dict[str, Any]:
    return {
        "data_rpm_budget": data_rpm_budget(),
        "data_tokens": _DATA_TOKENS,
        "data_cooldown_left": max(0.0, _DATA_COOLDOWN_UNTIL - time.monotonic()),
        "quote_cache_n": len(_QUOTE_CACHE),
        "orders_last_min": len(_ORDER_TS),
        "intraday_margin": intraday_margin_notes(),
        "basic_data_plan_rpm": 200,
        "ws_symbol_limit_basic": 30,
    }
