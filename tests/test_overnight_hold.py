"""Overnight hold: fortress stagnant timeout must not wipe the book in <1 day."""

from __future__ import annotations

import os

from analytics.market_session import minutes_to_rth_close


def _effective_fortress_timeout() -> float:
    allow_overnight = os.getenv("FORTRESS_ALLOW_OVERNIGHT", "true").lower() in ("1", "true", "yes")
    flatten_at_close = os.getenv("FLATTEN_AT_CLOSE", "false").lower() in ("1", "true", "yes")
    timeout_min = float(os.getenv("FORTRESS_EXIT_TIMEOUT_MIN", "0") or 0)
    if timeout_min <= 0:
        timeout_min = float(os.getenv("EXIT_TIMEOUT_MIN", "0") or 0)
    if allow_overnight and not flatten_at_close:
        overnight_floor = float(os.getenv("FORTRESS_OVERNIGHT_EXIT_TIMEOUT_MIN", "4320") or 4320)
        if timeout_min <= 0 or timeout_min < overnight_floor:
            timeout_min = overnight_floor
    return timeout_min


def test_overnight_raises_stale_75min_timeout(monkeypatch):
    monkeypatch.setenv("FORTRESS_ALLOW_OVERNIGHT", "true")
    monkeypatch.setenv("FLATTEN_AT_CLOSE", "false")
    monkeypatch.setenv("FORTRESS_EXIT_TIMEOUT_MIN", "75")
    monkeypatch.setenv("FORTRESS_OVERNIGHT_EXIT_TIMEOUT_MIN", "4320")
    assert _effective_fortress_timeout() == 4320.0


def test_explicit_flatten_at_close_keeps_short_timeout(monkeypatch):
    monkeypatch.setenv("FORTRESS_ALLOW_OVERNIGHT", "true")
    monkeypatch.setenv("FLATTEN_AT_CLOSE", "true")
    monkeypatch.setenv("FORTRESS_EXIT_TIMEOUT_MIN", "75")
    assert _effective_fortress_timeout() == 75.0


def test_minutes_to_rth_close_callable():
    # Just ensure helper is importable / returns float|None
    v = minutes_to_rth_close()
    assert v is None or isinstance(v, float)


def test_premarket_does_not_trim_overnight_book(monkeypatch):
    from analytics.market_session import Session
    from analytics.overnight_risk import in_preclose_window

    monkeypatch.setattr("analytics.market_session.current_session", lambda: Session.PRE_MARKET)
    assert in_preclose_window() is False


def test_phantom_unrealized_gain_is_ignored():
    from fortress_live import _position_unrealized_gain

    assert _position_unrealized_gain({"avg_entry_price": -351.88, "unrealized_plpc": 1.753}, 265.0) is None
    g = _position_unrealized_gain({"avg_entry_price": 100.0, "unrealized_plpc": 0.012}, 101.2)
    assert g is not None and abs(g - 0.012) < 1e-9

