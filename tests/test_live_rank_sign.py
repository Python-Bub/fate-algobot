"""Live rank sign: invert 1d p_up when the open book is mostly red."""

from datetime import datetime
from zoneinfo import ZoneInfo

from analytics.live_rank_sign import (
    apply_live_sign,
    exit_p_up,
    invert_p_up_enabled,
    reset_invert_cache,
)

ET = ZoneInfo("America/New_York")


def test_explicit_invert(monkeypatch):
    monkeypatch.setenv("FORTRESS_INVERT_P_UP", "true")
    monkeypatch.delenv("DOWNPRESS_SOFT_OK_WHEN_UNDERDEPLOY", raising=False)
    assert invert_p_up_enabled() is True
    assert abs(apply_live_sign(0.80) - 0.20) < 1e-12
    assert abs(apply_live_sign(0.20) - 0.80) < 1e-12
    # Exits never flip — inverted signal_sell dumped ORCL.
    assert exit_p_up(0.80) == 0.80


def test_fill_idle_cash_does_not_invert(monkeypatch):
    monkeypatch.setenv("FORTRESS_INVERT_P_UP", "true")
    monkeypatch.setenv("FORTRESS_FILL_NO_INVERT", "true")
    monkeypatch.setenv("DOWNPRESS_SOFT_OK_WHEN_UNDERDEPLOY", "true")
    reset_invert_cache()
    assert invert_p_up_enabled() is False
    assert apply_live_sign(0.80) == 0.80


def test_fade_entry_still_requires_min_p(monkeypatch):
    from analytics.live_rank_sign import entry_confidence_ok

    monkeypatch.setenv("FORTRESS_INVERT_P_UP", "true")
    monkeypatch.setenv("FORTRESS_FADE_MIN_P", "0.50")
    monkeypatch.delenv("DOWNPRESS_SOFT_OK_WHEN_UNDERDEPLOY", raising=False)
    reset_invert_cache()
    # Inverted 0.50 names used to bypass MIN_MODEL_CONFIDENCE and bleed the book.
    assert entry_confidence_ok(0.502, 0.51, 0.58, 0.55) is False
    assert entry_confidence_ok(0.60, 0.51, 0.58, 0.55) is True


def test_non_fade_still_uses_exec_gate(monkeypatch):
    from analytics.live_rank_sign import entry_confidence_ok

    monkeypatch.setenv("FORTRESS_INVERT_P_UP", "false")
    monkeypatch.setenv("CONFIDENCE_GATE_MODE", "exec_only")
    monkeypatch.setenv("MATH_P_UP_FLOOR", "0.48")
    assert entry_confidence_ok(0.502, 0.51, 0.58, 0.55) is False
    assert entry_confidence_ok(0.60, 0.70, 0.58, 0.55) is True


def test_auto_inverts_when_book_mostly_red(monkeypatch):
    monkeypatch.setenv("FORTRESS_INVERT_P_UP", "auto")
    monkeypatch.setenv("FORTRESS_INVERT_CACHE_SEC", "0")
    monkeypatch.setenv("FORTRESS_INVERT_MIN_NAMES", "4")
    monkeypatch.setenv("FORTRESS_INVERT_RED_FRAC", "0.55")
    monkeypatch.delenv("DOWNPRESS_SOFT_OK_WHEN_UNDERDEPLOY", raising=False)
    reset_invert_cache()
    reds = [
        {"qty": 10, "unrealized_plpc": -0.01},
        {"qty": 10, "unrealized_plpc": -0.02},
        {"qty": 10, "unrealized_plpc": -0.005},
        {"qty": 10, "unrealized_plpc": 0.001},
        {"qty": 10, "unrealized_plpc": -0.003},
    ]
    monkeypatch.setattr("alpaca_broker.list_positions", lambda: reds)
    # Premarket: no session fade, book-red still inverts.
    from analytics import market_session as ms

    monkeypatch.setattr(ms, "now_et", lambda: datetime(2026, 8, 14, 8, 0, tzinfo=ET))
    assert invert_p_up_enabled() is True
    assert abs(apply_live_sign(0.70) - 0.30) < 1e-12
    assert exit_p_up(0.70) == 0.70


def test_auto_stays_when_book_mostly_green(monkeypatch):
    monkeypatch.setenv("FORTRESS_INVERT_P_UP", "auto")
    monkeypatch.setenv("FORTRESS_INVERT_CACHE_SEC", "0")
    monkeypatch.setenv("FORTRESS_INVERT_MIN_NAMES", "4")
    reset_invert_cache()
    greens = [
        {"qty": 10, "unrealized_plpc": 0.01},
        {"qty": 10, "unrealized_plpc": 0.02},
        {"qty": 10, "unrealized_plpc": 0.005},
        {"qty": 10, "unrealized_plpc": -0.001},
    ]
    monkeypatch.setattr("alpaca_broker.list_positions", lambda: greens)
    from analytics import market_session as ms

    monkeypatch.setattr(ms, "now_et", lambda: datetime(2026, 8, 14, 8, 0, tzinfo=ET))
    assert invert_p_up_enabled() is False
    assert apply_live_sign(0.70) == 0.70


def test_auto_inverts_after_open_even_if_book_green(monkeypatch):
    monkeypatch.setenv("FORTRESS_INVERT_P_UP", "auto")
    monkeypatch.setenv("FORTRESS_INVERT_AFTER_OPEN", "true")
    monkeypatch.setenv("FORTRESS_INVERT_CACHE_SEC", "0")
    monkeypatch.setenv("FORTRESS_INVERT_AFTER_ET", "10:15")
    monkeypatch.delenv("DOWNPRESS_SOFT_OK_WHEN_UNDERDEPLOY", raising=False)
    reset_invert_cache()
    greens = [
        {"qty": 10, "unrealized_plpc": 0.01},
        {"qty": 10, "unrealized_plpc": 0.02},
        {"qty": 10, "unrealized_plpc": 0.005},
        {"qty": 10, "unrealized_plpc": 0.001},
    ]
    monkeypatch.setattr("alpaca_broker.list_positions", lambda: greens)
    from analytics import market_session as ms

    monkeypatch.setattr(ms, "now_et", lambda: datetime(2026, 8, 14, 14, 0, tzinfo=ET))
    assert invert_p_up_enabled() is True
    assert abs(apply_live_sign(0.80) - 0.20) < 1e-12
    assert exit_p_up(0.80) == 0.80


def test_after_open_does_not_invert_green_book_by_default(monkeypatch):
    monkeypatch.setenv("FORTRESS_INVERT_P_UP", "auto")
    monkeypatch.setenv("FORTRESS_INVERT_AFTER_OPEN", "false")
    monkeypatch.setenv("FORTRESS_INVERT_CACHE_SEC", "0")
    monkeypatch.setenv("FORTRESS_INVERT_AFTER_ET", "10:15")
    monkeypatch.setenv("FORTRESS_INVERT_MIN_NAMES", "4")
    monkeypatch.delenv("DOWNPRESS_SOFT_OK_WHEN_UNDERDEPLOY", raising=False)
    reset_invert_cache()
    greens = [
        {"qty": 10, "unrealized_plpc": 0.01},
        {"qty": 10, "unrealized_plpc": 0.02},
        {"qty": 10, "unrealized_plpc": 0.005},
        {"qty": 10, "unrealized_plpc": 0.001},
    ]
    monkeypatch.setattr("alpaca_broker.list_positions", lambda: greens)
    from analytics import market_session as ms

    monkeypatch.setattr(ms, "now_et", lambda: datetime(2026, 8, 14, 14, 0, tzinfo=ET))
    assert invert_p_up_enabled() is False
    assert apply_live_sign(0.80) == 0.80


def test_open_window_keeps_raw_sign(monkeypatch):
    monkeypatch.setenv("FORTRESS_INVERT_P_UP", "auto")
    monkeypatch.setenv("FORTRESS_INVERT_CACHE_SEC", "0")
    monkeypatch.setenv("FORTRESS_INVERT_AFTER_ET", "10:15")
    monkeypatch.setenv("FORTRESS_INVERT_MIN_NAMES", "4")
    reset_invert_cache()
    greens = [
        {"qty": 10, "unrealized_plpc": 0.01},
        {"qty": 10, "unrealized_plpc": 0.02},
        {"qty": 10, "unrealized_plpc": 0.005},
        {"qty": 10, "unrealized_plpc": 0.001},
    ]
    monkeypatch.setattr("alpaca_broker.list_positions", lambda: greens)
    from analytics import market_session as ms

    monkeypatch.setattr(ms, "now_et", lambda: datetime(2026, 8, 14, 9, 45, tzinfo=ET))
    assert invert_p_up_enabled() is False
    assert apply_live_sign(0.80) == 0.80
