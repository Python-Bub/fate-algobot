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


def _as_equity(equity: float) -> float:
    try:
        return float(equity or 0)
    except (TypeError, ValueError):
        return 0.0


def register_equity_snapshot(equity: float) -> None:
    global _DAY_START_EQUITY, _CURRENT_DAY, _TRADING_HALTED
    eq = _as_equity(equity)
    # Empty/failed get_account() snapshots must not lock the day at -100%.
    if eq < 100.0:
        return
    today = date.today()
    try:
        from analytics.day_trade_risk import session_et_date

        today = date.fromisoformat(session_et_date())
    except Exception:
        today = date.today()
    if _CURRENT_DAY != today:
        _CURRENT_DAY = today
        _DAY_START_EQUITY = eq
        if _TRADING_HALTED:
            log.info("[KILL] New day — start equity=%.2f (prior halt cleared)", eq)
        else:
            log.info("[KILL] New day — start equity=%.2f", eq)
        _TRADING_HALTED = False
        return
    if _DAY_START_EQUITY is None:
        _DAY_START_EQUITY = eq
        return
    limit = float(os.getenv("KILL_DAILY_LOSS_PCT", "0.008"))
    dd = (_DAY_START_EQUITY - eq) / max(_DAY_START_EQUITY, 1e-9)
    if _TRADING_HALTED:
        if dd < limit:
            _TRADING_HALTED = False
            log.info(
                "[KILL] halt cleared — drawdown %.3f%% < %.3f%%",
                100 * dd,
                100 * limit,
            )
        return
    if dd >= limit:
        _TRADING_HALTED = True
        log.error(
            "[KILL] Daily loss %.2f%% ≥ %.2f%% — HALT (overnight book kept)",
            100 * dd,
            100 * limit,
        )
        if os.getenv("KILL_FLATTEN_ON_HALT", "false").lower() in ("1", "true", "yes"):
            try:
                from fortress_portfolio import flatten_all_positions

                result = flatten_all_positions()
                log.error("[KILL] flatten result: %s", result)
            except Exception as e:
                log.error("[KILL] flatten failed — close positions manually: %s", e)


def force_halt() -> None:
    global _TRADING_HALTED
    _TRADING_HALTED = True
