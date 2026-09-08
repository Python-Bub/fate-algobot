"""Shared LLM cooldown — honor 429 / Retry-After instead of stampeding the same key."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "data" / "ops" / "llm_cooldown.json"
LEGACY = ROOT / "data" / "agi" / "llm_cooldown.ts"


def remaining() -> float:
    now = time.time()
    until = 0.0
    if PATH.is_file():
        try:
            until = float(json.loads(PATH.read_text(encoding="utf-8")).get("until_unix") or 0)
        except Exception:
            until = 0.0
    if LEGACY.is_file():
        try:
            until = max(until, float(LEGACY.read_text(encoding="utf-8").strip()))
        except Exception:
            pass
    return max(0.0, until - now)


def active() -> bool:
    return remaining() > 0


def trip(seconds: float, *, reason: str = "429") -> float:
    wait = max(15.0, min(float(seconds), 900.0))
    until = time.time() + wait
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(
        json.dumps({"until_unix": until, "reason": reason[:80], "ts": time.time()}, indent=2),
        encoding="utf-8",
    )
    try:
        LEGACY.parent.mkdir(parents=True, exist_ok=True)
        LEGACY.write_text(str(until), encoding="utf-8")
    except Exception:
        pass
    return wait


def retry_after_seconds(headers: dict | None, *, default: float = 120.0) -> float:
    if not headers:
        return default
    raw = headers.get("Retry-After") or headers.get("retry-after") or ""
    try:
        return max(15.0, min(float(raw), 900.0))
    except (TypeError, ValueError):
        return default
