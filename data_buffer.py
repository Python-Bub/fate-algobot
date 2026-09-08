"""
In-memory ring buffer for streaming quotes (5-minute look-back default).
Wire your WebSocket (Alpaca/Polygon/IBKR) to DataBuffer.push().
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from threading import Lock
from typing import Deque, List


@dataclass
class Tick:
    ts: float
    price: float
    size: float = 0.0


class DataBuffer:
    def __init__(self, lookback_seconds: float = 300.0, max_ticks: int = 50_000):
        self.lookback = lookback_seconds
        self.max_ticks = max_ticks
        self._buf: Deque[Tick] = deque()
        self._lock = Lock()

    def push(self, price: float, size: float = 0.0, ts: float | None = None) -> None:
        t = ts if ts is not None else time.time()
        with self._lock:
            self._buf.append(Tick(ts=t, price=price, size=size))
            cutoff = t - self.lookback
            while self._buf and self._buf[0].ts < cutoff:
                self._buf.popleft()
            while len(self._buf) > self.max_ticks:
                self._buf.popleft()

    def snapshot(self) -> List[Tick]:
        with self._lock:
            return list(self._buf)

    def vwap_window(self) -> float | None:
        ticks = self.snapshot()
        if not ticks:
            return None
        num = sum(t.price * max(t.size, 1.0) for t in ticks)
        den = sum(max(t.size, 1.0) for t in ticks)
        return num / den if den else None

    def last_price(self) -> float | None:
        with self._lock:
            return self._buf[-1].price if self._buf else None
