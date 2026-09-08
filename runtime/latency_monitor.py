"""Latency budget tracking utilities."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from time import perf_counter
from collections import defaultdict


@dataclass
class LatencyStat:
    count: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0

    @property
    def avg_ms(self) -> float:
        return self.total_ms / max(self.count, 1)


class LatencyMonitor:
    def __init__(self):
        self.stats: dict[str, LatencyStat] = defaultdict(LatencyStat)

    @contextmanager
    def track(self, stage: str):
        st = perf_counter()
        try:
            yield
        finally:
            ms = (perf_counter() - st) * 1000.0
            s = self.stats[stage]
            s.count += 1
            s.total_ms += ms
            s.max_ms = max(s.max_ms, ms)

    def summary(self) -> dict:
        return {
            k: {"count": v.count, "avg_ms": round(v.avg_ms, 3), "max_ms": round(v.max_ms, 3)}
            for k, v in self.stats.items()
        }

