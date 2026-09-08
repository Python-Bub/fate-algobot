"""Honest credit: one realized outcome per trade key. No retries, no in-sample rewrite.

Walk-forward and live fill-replay share this so the learner cannot:
  - take a second attempt at the same (symbol, entry_ts, side)
  - relabel a loss as a win
  - fit a perfect map of a frozen historical path
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "data" / "intel" / "honest_credit_keys.json"


def _path() -> Path:
    return Path(os.getenv("HONEST_CREDIT_FILE", str(DEFAULT_PATH)))


def _load() -> set[str]:
    p = _path()
    if not p.is_file():
        return set()
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return set()
    keys = doc.get("keys") if isinstance(doc, dict) else None
    if not isinstance(keys, list):
        return set()
    return {str(k) for k in keys if str(k).strip()}


def _save(keys: set[str]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    # Cap disk — oldest keys dropped; collisions after cap are acceptable vs growth.
    rows = sorted(keys)[-8000:]
    p.write_text(json.dumps({"keys": rows}, indent=2), encoding="utf-8")


def trade_key(symbol: str, *, entry_ts: str | float | int, side: str) -> str:
    return f"{str(symbol or '').strip().upper()}|{entry_ts}|{str(side or 'LONG').upper()}"


def already_credited(key: str) -> bool:
    return str(key) in _load()


def credit_once(key: str, apply_fn: Callable[[], Any] | None = None) -> dict[str, Any]:
    """Apply a reward update at most once per trade_key."""
    k = str(key or "").strip()
    if not k:
        return {"applied": False, "reason": "empty_key"}
    keys = _load()
    if k in keys:
        return {"applied": False, "reason": "already_credited", "key": k}
    result: Any = None
    if apply_fn is not None:
        result = apply_fn()
    keys.add(k)
    _save(keys)
    return {"applied": True, "key": k, "result": result}
