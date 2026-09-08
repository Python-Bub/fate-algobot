"""Global Yahoo Finance throttle — avoids 429 rate limits under parallel paper sim."""

from __future__ import annotations

import os
import threading
import time

_lock = threading.Lock()
_last_call = 0.0
_cooldown_until = 0.0


def _min_interval_sec() -> float:
    return float(os.getenv("YAHOO_MIN_INTERVAL_SEC", "0.35"))


def _cooldown_sec() -> float:
    # Shorter default — long cooldowns cascade into fortress "No price data" storms
    return float(os.getenv("YAHOO_RATE_LIMIT_COOLDOWN_SEC", "45"))


def is_rate_limited() -> bool:
    return time.time() < _cooldown_until


def note_rate_limit() -> None:
    global _cooldown_until
    _cooldown_until = time.time() + _cooldown_sec()


def _sleep_until_open() -> None:
    while is_rate_limited():
        time.sleep(min(1.0, max(0.05, _cooldown_until - time.time())))


def wait_turn(*, block: bool | None = None) -> bool:
    """Block until allowed to call Yahoo. When block=False, skip during cooldown."""
    global _last_call
    if block is None:
        try:
            from data_platform.price_fetch_policy import price_fetch_blocking

            block = price_fetch_blocking()
        except ImportError:
            block = False
    if is_rate_limited():
        if not block:
            return False
        _sleep_until_open()
    with _lock:
        if is_rate_limited():
            if not block:
                return False
            _sleep_until_open()
        gap = time.time() - _last_call
        need = _min_interval_sec() - gap
        if need > 0:
            time.sleep(need)
        _last_call = time.time()
    return True


def should_skip_yahoo_fetch() -> bool:
    try:
        from data_platform.price_fetch_policy import price_fetch_blocking

        if price_fetch_blocking():
            return False
    except ImportError:
        pass
    if os.getenv("YAHOO_SKIP_WHEN_LIMITED", "true").lower() not in ("1", "true", "yes"):
        return False
    return is_rate_limited()
