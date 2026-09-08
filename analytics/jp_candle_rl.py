"""Lightweight pattern outcome tracker — learns which JP candles help (eyeball + EMA)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "intel" / "jp_candle_rl_state.json"

_PATTERN_KEYS = (
    "NONE",
    "HAMMER",
    "INV_HAMMER",
    "SHOOTING_STAR",
    "HANGING_MAN",
    "DOJI",
    "BULLISH_ENGULF",
    "BEARISH_ENGULF",
    "THREE_WHITE",
    "MORNING_STAR",
    "PIERCING",
    "DARK_CLOUD",
    "BULL_MARUBOZU",
)


def _enabled() -> bool:
    return os.getenv("JP_CANDLE_RL_ENABLED", "true").lower() in ("1", "true", "yes")


def _load() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {"patterns": {}, "pending": {}, "updated_at_utc": None}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"patterns": {}, "pending": {}, "updated_at_utc": None}


def _save(doc: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    doc["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    tmp = STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    tmp.replace(STATE_PATH)


def _pat_key(pattern: str) -> str:
    p = (pattern or "NONE").strip().upper()
    return p if p in _PATTERN_KEYS else "NONE"


def pattern_stats(pattern: str) -> dict[str, float]:
    doc = _load()
    rec = (doc.get("patterns") or {}).get(_pat_key(pattern), {})
    n = float(rec.get("n", 0))
    wins = float(rec.get("wins", 0))
    ema = float(rec.get("ema_pnl", 0.0))
    hit = wins / n if n > 0 else 0.5
    return {"n": n, "hit_rate": hit, "ema_pnl": ema}


def pattern_weight(pattern: str) -> float:
    """Scale boost/notional: weak patterns down-weighted, strong ones up (RL eyeball)."""
    if not _enabled():
        return 1.0
    st = pattern_stats(pattern)
    n = st["n"]
    hit = st["hit_rate"]
    ema = st["ema_pnl"]
    min_n = float(os.getenv("JP_CANDLE_RL_MIN_SAMPLES", "8"))
    if n < min_n:
        # Not enough data — neutral with slight skepticism on exotic patterns
        return 0.92 if _pat_key(pattern) not in ("HAMMER", "INV_HAMMER", "BULLISH_ENGULF", "NONE") else 1.0
    # Map hit_rate 0.35–0.65 → weight 0.65–1.25; ema_pnl nudges ±10%
    base = 0.65 + max(0.0, min(1.0, (hit - 0.35) / 0.30)) * 0.60
    if ema > 0.002:
        base *= 1.08
    elif ema < -0.002:
        base *= 0.88
    lo = float(os.getenv("JP_CANDLE_RL_WEIGHT_MIN", "0.55"))
    hi = float(os.getenv("JP_CANDLE_RL_WEIGHT_MAX", "1.30"))
    return max(lo, min(hi, base))


def record_signal(
    ticker: str,
    *,
    pattern: str,
    bias: int,
    composite_bias: int,
    p_adj: float,
) -> None:
    if not _enabled():
        return
    doc = _load()
    pending = doc.setdefault("pending", {})
    pending[ticker.strip().upper()] = {
        "pattern": _pat_key(pattern),
        "bias": int(bias),
        "composite_bias": int(composite_bias),
        "p_adj": float(p_adj),
        "ts_utc": datetime.now(timezone.utc).isoformat(),
    }
    _save(doc)


def record_outcome(ticker: str, pnl_frac: float) -> None:
    """Call on exit — updates pattern EMA/hit rate. Patterns aren't perfect; RL learns that."""
    if not _enabled():
        return
    sym = ticker.strip().upper()
    doc = _load()
    pending = doc.setdefault("pending", {})
    sig = pending.pop(sym, None)
    if not sig:
        return
    key = str(sig.get("pattern") or "NONE")
    patterns = doc.setdefault("patterns", {})
    rec = patterns.setdefault(key, {"n": 0, "wins": 0, "ema_pnl": 0.0})
    lr = float(os.getenv("JP_CANDLE_RL_LEARN_RATE", "0.12"))
    pf = float(pnl_frac)
    rec["n"] = int(rec.get("n", 0)) + 1
    if pf > 0:
        rec["wins"] = int(rec.get("wins", 0)) + 1
    prev = float(rec.get("ema_pnl", 0.0))
    rec["ema_pnl"] = prev + lr * (pf - prev)
    _save(doc)


def adjust_boost(base_boost: float, pattern: str) -> tuple[float, float]:
    w = pattern_weight(pattern)
    return base_boost * w, w
