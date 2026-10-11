"""Kill switch must not stick on a missing snapshot or a recovered mark."""

from __future__ import annotations

import kill_switch as ks


def test_zero_equity_snapshot_does_not_halt(monkeypatch):
    ks.reset_for_tests()
    monkeypatch.setenv("KILL_DAILY_LOSS_PCT", "0.008")
    monkeypatch.setenv("KILL_FLATTEN_ON_HALT", "false")
    ks.register_equity_snapshot(70_000.0)
    ks.register_equity_snapshot(0.0)
    assert ks.is_halted() is False


def test_halt_clears_when_drawdown_recovers(monkeypatch):
    ks.reset_for_tests()
    monkeypatch.setenv("KILL_DAILY_LOSS_PCT", "0.008")
    monkeypatch.setenv("KILL_FLATTEN_ON_HALT", "false")
    ks.register_equity_snapshot(70_000.0)
    ks.register_equity_snapshot(69_300.0)  # -1.0%
    assert ks.is_halted() is True
    ks.register_equity_snapshot(69_800.0)  # -0.29%
    assert ks.is_halted() is False


def test_new_session_clears_prior_halt(monkeypatch):
    ks.reset_for_tests()
    monkeypatch.setenv("KILL_DAILY_LOSS_PCT", "0.008")
    monkeypatch.setenv("KILL_FLATTEN_ON_HALT", "false")
    monkeypatch.setattr("analytics.day_trade_risk.session_et_date", lambda: "2026-09-18")
    ks.register_equity_snapshot(70_000.0)
    ks.register_equity_snapshot(69_000.0)
    assert ks.is_halted() is True
    monkeypatch.setattr("analytics.day_trade_risk.session_et_date", lambda: "2026-09-21")
    ks.register_equity_snapshot(69_000.0)
    assert ks.is_halted() is False
