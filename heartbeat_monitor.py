"""
Heartbeat: ping data/API latency; flips global Reduced Risk Mode if slow.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Callable

import requests

from utils import log

REDUCED_RISK_MODE = False
_LAST_LATENCY_MS = 0.0


def is_reduced_risk() -> bool:
    return REDUCED_RISK_MODE


def _ping_once(url: str, timeout: float) -> float:
    t0 = time.perf_counter()
    requests.get(url, timeout=timeout)
    return (time.perf_counter() - t0) * 1000


def default_ping_url() -> str:
    return os.getenv(
        "HEARTBEAT_URL",
        "http://connectivitycheck.gstatic.com/generate_204",
    )


def heartbeat_loop(
    interval_sec: float | None = None,
    max_latency_ms: float | None = None,
    ping_fn: Callable[[], float] | None = None,
) -> None:
    global REDUCED_RISK_MODE, _LAST_LATENCY_MS
    interval = float(os.getenv("HEARTBEAT_INTERVAL_SEC", str(interval_sec or 10)))
    cap = float(os.getenv("HEARTBEAT_MAX_LATENCY_MS", str(max_latency_ms or 500)))
    # Hysteresis: need N consecutive bad/good samples before flipping (stops 50% size thrash).
    bad_need = max(1, int(os.getenv("HEARTBEAT_BAD_STREAK", "3")))
    good_need = max(1, int(os.getenv("HEARTBEAT_GOOD_STREAK", "2")))
    url = default_ping_url()
    bad_streak = 0
    good_streak = 0

    def _ping() -> float:
        try:
            return _ping_once(url, min(5.0, interval * 0.8))
        except Exception:
            return cap + 1

    fn = ping_fn or _ping

    while True:
        ms = fn()
        _LAST_LATENCY_MS = ms
        bad = ms > cap
        if bad:
            bad_streak += 1
            good_streak = 0
        else:
            good_streak += 1
            bad_streak = 0

        if (not REDUCED_RISK_MODE) and bad_streak >= bad_need:
            REDUCED_RISK_MODE = True
            log.warning(
                "[HEARTBEAT] Reduced risk mode=True (latency=%.1fms cap=%.0fms streak=%d)",
                ms,
                cap,
                bad_streak,
            )
        elif REDUCED_RISK_MODE and good_streak >= good_need:
            REDUCED_RISK_MODE = False
            log.warning(
                "[HEARTBEAT] Reduced risk mode=False (latency=%.1fms cap=%.0fms streak=%d)",
                ms,
                cap,
                good_streak,
            )
        elif not bad:
            log.debug("[HEARTBEAT] ok %.1fms", ms)
        time.sleep(interval)


def start_heartbeat_daemon() -> threading.Thread:
    t = threading.Thread(target=heartbeat_loop, name="heartbeat", daemon=True)
    t.start()
    log.info("[HEARTBEAT] daemon started")
    return t
