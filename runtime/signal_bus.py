"""Simple in-process event bus for concurrent runtime coordination."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable


@dataclass
class SignalEvent:
    topic: str
    symbol: str
    payload: dict
    ts_utc: str


class SignalBus:
    def __init__(self):
        self._subs: dict[str, list[Callable[[SignalEvent], None]]] = defaultdict(list)
        self._history: list[SignalEvent] = []

    def subscribe(self, topic: str, fn: Callable[[SignalEvent], None]) -> None:
        self._subs[topic].append(fn)

    def publish(self, topic: str, symbol: str, payload: dict) -> SignalEvent:
        evt = SignalEvent(
            topic=topic,
            symbol=symbol,
            payload=payload,
            ts_utc=datetime.now(timezone.utc).isoformat(),
        )
        self._history.append(evt)
        for fn in self._subs.get(topic, []):
            fn(evt)
        return evt

    @property
    def history(self) -> list[SignalEvent]:
        return self._history[-5000:]

