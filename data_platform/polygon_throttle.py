"""Global Polygon.io throttle — avoids 429 under parallel paper sim."""

from __future__ import annotations

import os
import threading
import time

_lock = threading.Lock()
_last_call = 0.0
_cooldown_until = 0.0


def _min_interval_sec() -> float:
    return float(os.getenv("POLYGON_MIN_INTERVAL_SEC", "0.35"))


def _cooldown_sec() -> float:
    return float(os.getenv("POLYGON_RATE_LIMIT_COOLDOWN_SEC", "45"))


def is_rate_limited() -> bool:
    return time.time() < _cooldown_until


def note_rate_limit() -> None:
    global _cooldown_until
    _cooldown_until = time.time() + _cooldown_sec()


def _sleep_until_open() -> None:
    """Wait out rate-limit cooldown, but never stall a live trading thread forever."""
    max_block = float(os.getenv("POLYGON_MAX_BLOCK_SEC", "8"))
    t0 = time.time()
    while is_rate_limited():
        if time.time() - t0 >= max_block:
            # Give up waiting — caller should skip Polygon / use cache/Yahoo.
            return
        remain = _cooldown_until - time.time()
        time.sleep(min(1.0, max(0.05, remain, 0.0)))


def wait_turn(*, block: bool | None = None) -> bool:
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
        if is_rate_limited():
            return False
    with _lock:
        if is_rate_limited():
            if not block:
                return False
            _sleep_until_open()
            if is_rate_limited():
                return False
        gap = time.time() - _last_call
        need = _min_interval_sec() - gap
        if need > 0:
            time.sleep(need)
        _last_call = time.time()
    return True


def should_skip_polygon_fetch() -> bool:
    try:
        from data_platform.price_fetch_policy import price_fetch_blocking

        if price_fetch_blocking():
            return False
    except ImportError:
        pass
    if os.getenv("POLYGON_SKIP_WHEN_LIMITED", "true").lower() not in ("1", "true", "yes"):
        return False
    return is_rate_limited()
