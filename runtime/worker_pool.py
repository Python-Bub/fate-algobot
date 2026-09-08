"""Bounded worker pool with priority scheduling helpers."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import heapq
from typing import Any, Callable, Iterable


@dataclass(order=True)
class PriorityTask:
    priority: int
    item: Any


class BoundedWorkerPool:
    def __init__(self, max_workers: int | None = None):
        self.max_workers = max_workers or 8

    def map_unordered(self, fn: Callable[[Any], Any], items: Iterable[Any]) -> list[Any]:
        out: list[Any] = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as ex:
            futs = [ex.submit(fn, i) for i in items]
            for f in as_completed(futs):
                out.append(f.result())
        return out

    def map_dict(self, fn: Callable[[Any], Any], items: Iterable[Any]) -> dict[Any, Any]:
        out: dict[Any, Any] = {}
        with ThreadPoolExecutor(max_workers=self.max_workers) as ex:
            futs = {ex.submit(fn, i): i for i in items}
            for f in as_completed(futs):
                out[futs[f]] = f.result()
        return out


def take_top_priority(items: Iterable[Any], score_fn: Callable[[Any], float], n: int) -> list[Any]:
    h: list[PriorityTask] = []
    for it in items:
        p = -float(score_fn(it))
        heapq.heappush(h, PriorityTask(priority=int(p * 1_000_000), item=it))
    out: list[Any] = []
    for _ in range(min(n, len(h))):
        out.append(heapq.heappop(h).item)
    return out

