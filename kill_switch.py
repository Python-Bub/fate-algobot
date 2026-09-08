"""
Global kill switch: daily loss vs equity → flatten and halt.
"""

from __future__ import annotations

import os
from datetime import date

from utils import log

_TRADING_HALTED = False
_DAY_START_EQUITY: float | None = None
_CURRENT_DAY: date | None = None


def is_halted() -> bool:
    return _TRADING_HALTED


def reset_for_tests():
    global _TRADING_HALTED, _DAY_START_EQUITY, _CURRENT_DAY
    _TRADING_HALTED = False
    _DAY_START_EQUITY = None
    _CURRENT_DAY = None


def register_equity_snapshot(equity: float) -> None:
    global _DAY_START_EQUITY, _CURRENT_DAY, _TRADING_HALTED
    if _TRADING_HALTED:
        return
    today = date.today()
    if _CURRENT_DAY != today:
        _CURRENT_DAY = today
        _DAY_START_EQUITY = equity
        log.info("[KILL] New day — start equity=%.2f", equity)
        return
    if _DAY_START_EQUITY is None:
        _DAY_START_EQUITY = equity
        return
    limit = float(os.getenv("KILL_DAILY_LOSS_PCT", "0.02"))
    dd = (_DAY_START_EQUITY - equity) / max(_DAY_START_EQUITY, 1e-9)
    if dd >= limit:
        _TRADING_HALTED = True
        log.error(
            "[KILL] Daily loss %.2f%% ≥ %.2f%% — HALT + flatten",
            100 * dd,
            100 * limit,
        )
        if os.getenv("KILL_FLATTEN_ON_HALT", "true").lower() in ("1", "true", "yes"):
            try:
                from fortress_portfolio import flatten_all_positions

                result = flatten_all_positions()
                log.error("[KILL] flatten result: %s", result)
            except Exception as e:
                log.error("[KILL] flatten failed — close positions manually: %s", e)


def force_halt() -> None:
    global _TRADING_HALTED
    _TRADING_HALTED = True
