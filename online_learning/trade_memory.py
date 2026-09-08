"""Trade memory: remembers entry-state vectors so we can run the online update on exit."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, asdict
from pathlib import Path


_MEM_FILE = Path(os.getenv("TRADE_MEMORY_FILE", "data/online_learning/open_trades.json"))


@dataclass
class TradeMemoryEntry:
    ticker: str
    side: str
    entry_ts: float
    entry_px: float
    state: dict


def _load() -> dict:
    if not _MEM_FILE.is_file():
        return {}
    try:
        with open(_MEM_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(data: dict) -> None:
    _MEM_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_MEM_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=0)


def record_entry(ticker: str, side: str, entry_px: float, state: dict) -> None:
    data = _load()
    data[ticker] = asdict(
        TradeMemoryEntry(
            ticker=ticker,
            side=side,
            entry_ts=float(time.time()),
            entry_px=float(entry_px),
            state={k: float(v) for k, v in state.items() if isinstance(v, (int, float))},
        )
    )
    _save(data)


def pop_entry(ticker: str) -> TradeMemoryEntry | None:
    data = _load()
    raw = data.pop(ticker, None)
    if raw is None:
        return None
    _save(data)
    try:
        return TradeMemoryEntry(**raw)
    except Exception:
        return None


def get_entry(ticker: str) -> TradeMemoryEntry | None:
    raw = _load().get(ticker)
    if raw is None:
        return None
    try:
        return TradeMemoryEntry(**raw)
    except Exception:
        return None
