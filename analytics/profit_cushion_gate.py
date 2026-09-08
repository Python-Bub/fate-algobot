"""Earn-then-scalp gate: fortress marks green legs; HFT scalps only those names."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from utils import log

_LAST: dict | None = None


def _gate_path() -> Path:
    return Path(os.getenv("PROFIT_CUSHION_GATE_PATH", "data/intel/profit_cushion_gate.json"))


def _env_f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _require_cushion() -> bool:
    return os.getenv("HFT_REQUIRE_PROFIT_CUSHION", "true").lower() not in ("0", "false", "no")


def _position_gain_frac(pos: dict) -> float | None:
    uplpc = pos.get("unrealized_plpc")
    if uplpc is not None:
        return float(uplpc)
    try:
        entry = float(pos.get("avg_entry_price") or 0)
        cur = float(pos.get("current_price") or 0)
        if entry > 0 and cur > 0:
            return (cur - entry) / entry
    except (TypeError, ValueError):
        pass
    return None


def refresh_profit_gate() -> dict:
    """Scan Alpaca longs; publish symbols with unrealized gain >= cushion min."""
    global _LAST
    min_pct = _env_f("HFT_PROFIT_CUSHION_MIN_PCT", 0.003)
    earned: dict[str, float] = {}
    equity = 0.0
    try:
        from alpaca_broker import get_account, list_positions

        acct = get_account()
        if acct:
            equity = float(acct.get("equity") or acct.get("last_equity") or 0.0)
        for p in list_positions():
            sym = str(p.get("symbol", "")).replace("/", "-").upper()
            qty = float(p.get("qty") or 0)
            if not sym or qty <= 0:
                continue
            gain = _position_gain_frac(p)
            if gain is None or gain < min_pct:
                continue
            earned[sym] = round(gain, 6)
    except Exception as e:
        log.debug("[PROFIT-GATE] refresh failed: %s", e)

    payload = {
        "earned": earned,
        "min_pct": min_pct,
        "require_cushion": _require_cushion(),
        "hft_boost": len(earned) > 0,
        "equity": equity,
        "updated_ms": int(time.time() * 1000),
    }
    try:
        p = _gate_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(p)
    except Exception as e:
        log.debug("[PROFIT-GATE] write failed: %s", e)

    _LAST = payload
    if earned:
        log.info(
            "[PROFIT-GATE] earned=%d names (min %.2f%%) — HFT may scalp: %s",
            len(earned),
            100 * min_pct,
            ", ".join(sorted(earned)[:8]),
        )
    return payload


def load_gate() -> dict:
    global _LAST
    if _LAST is not None:
        return _LAST
    try:
        p = _gate_path()
        if p.is_file():
            _LAST = json.loads(p.read_text(encoding="utf-8"))
            return _LAST
    except Exception:
        pass
    return {}


def earned_gain(symbol: str) -> float | None:
    sym = str(symbol or "").replace("/", "-").upper()
    earned = load_gate().get("earned") or {}
    if sym in earned:
        return float(earned[sym])
    return None


def is_earned(symbol: str) -> bool:
    return earned_gain(symbol) is not None


def fortress_take_profit_pct(symbol: str, default: float) -> float:
    """Once a leg is green enough to scalp, sell the swing at the earned target."""
    min_pct = _env_f("HFT_PROFIT_CUSHION_MIN_PCT", 0.003)
    earned_sell = _env_f("FORTRESS_EARNED_SELL_PCT", 0.012)
    gain = earned_gain(symbol)
    if gain is not None and gain >= min_pct:
        return min(float(default), earned_sell)
    return float(default)
