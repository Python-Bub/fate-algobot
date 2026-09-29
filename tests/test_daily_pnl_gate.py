"""Account-level +1.5% lock and never-red new-entry halt."""

from __future__ import annotations

from pathlib import Path

import pytest

from analytics.buying_power import plan_from_account
from analytics.day_trade_risk import check_daily_limits, is_trading_halted


@pytest.fixture(autouse=True)
def _session_file(tmp_path, monkeypatch):
    p = tmp_path / "day_trade_session.json"
    monkeypatch.setenv("DAY_TRADE_SESSION_PATH", str(p))
    monkeypatch.setenv("DAY_TRADE_MAX_DAILY_LOSS_PCT", "0.002")
    monkeypatch.setenv("DAY_TRADE_DAILY_PROFIT_PCT", "0.015")
    monkeypatch.setenv("DAILY_RED_NO_NEW_ENTRIES", "true")
    monkeypatch.setenv("DAILY_RED_EPS_PCT", "0.0003")
    monkeypatch.setenv("SESSION_EQUITY_TARGET_USD", "0")
    # Pin a weekday so Saturday's weekend rebase cannot hide red/max-loss cases.
    # Also pin the clock: before 04:00 ET the live anchor ignores a stale prior close.
    monkeypatch.setattr("analytics.day_trade_risk.session_et_date", lambda: "2026-09-18")
    monkeypatch.setattr("analytics.day_trade_risk._before_cash_open_et", lambda: False)
    yield


def test_red_day_blocks_new_entries():
    ok, why = check_daily_limits(69_970.0, last_equity=70_000.0)
    assert ok is False
    assert why == "daily-red"
    assert is_trading_halted() is True


def test_max_loss_is_stickier_than_red():
    ok, why = check_daily_limits(69_800.0, last_equity=70_280.0)
    assert ok is False
    assert why == "max-daily-loss"
    assert is_trading_halted() is True


def test_profit_lock_at_one_point_five_percent():
    start = 70_000.0
    ok, why = check_daily_limits(start * 1.016, last_equity=start)
    assert ok is False
    assert why == "daily-profit-pct"


def test_new_et_day_before_open_does_not_relock_yesterdays_gain(monkeypatch):
    """Stale Alpaca last_equity must not freeze Tuesday on Monday's already-locked gain."""
    monkeypatch.setattr("analytics.day_trade_risk.session_et_date", lambda: "2026-09-21")
    monkeypatch.setattr("analytics.day_trade_risk._before_cash_open_et", lambda: False)
    ok, why = check_daily_limits(72_336.0, last_equity=69_920.0)
    assert ok is False
    assert why == "daily-profit-pct"

    monkeypatch.setattr("analytics.day_trade_risk.session_et_date", lambda: "2026-09-22")
    monkeypatch.setattr("analytics.day_trade_risk._before_cash_open_et", lambda: True)
    ok2, why2 = check_daily_limits(72_336.0, last_equity=69_920.0)
    assert ok2 is True
    assert why2 == ""
    assert is_trading_halted() is False


def test_false_zero_equity_halt_clears_on_live_mark():
    ok, why = check_daily_limits(0.0, last_equity=70_000.0)
    assert ok is True
    # Pretend a prior bad snapshot persisted a max-loss halt.
    from analytics.day_trade_risk import halt_trading

    halt_trading("max daily loss -100.00%")
    assert is_trading_halted() is True
    ok2, why2 = check_daily_limits(70_400.0, last_equity=70_000.0)
    assert ok2 is True
    assert why2 == ""
    assert is_trading_halted() is False


def test_red_can_resume_when_mark_recovers():
    ok, why = check_daily_limits(69_950.0, last_equity=70_000.0)
    assert ok is False
    assert why == "daily-red"
    ok2, why2 = check_daily_limits(70_050.0, last_equity=70_000.0)
    assert ok2 is True
    assert why2 == ""
    assert is_trading_halted() is False


def test_plan_zeros_day_clips_when_account_is_red(monkeypatch):
    monkeypatch.setenv("DAILY_RED_NO_NEW_ENTRIES", "true")
    monkeypatch.setenv("DAY_TRADE_DAILY_PROFIT_PCT", "0.015")
    plan = plan_from_account(
        {
            "equity": 69_500.0,
            "last_equity": 70_280.0,
            "cash": 0.0,
            "buying_power": 154_000.0,
            "long_market_value": 99_800.0,
        },
        [{"symbol": "AAPL", "qty": "10", "market_value": "99800"}],
    )
    assert plan.daily_pnl < 0
    assert plan.hft_clip == 0.0
    assert plan.day_trade_clip == 0.0
    assert plan.micro_scalp_clip == 0.0
    assert any("daily_red" in n for n in plan.notes)


def test_plan_zeros_clips_after_profit_lock(monkeypatch):
    monkeypatch.setenv("DAILY_RED_NO_NEW_ENTRIES", "true")
    monkeypatch.setenv("DAY_TRADE_DAILY_PROFIT_PCT", "0.015")
    plan = plan_from_account(
        {
            "equity": 71_200.0,
            "last_equity": 70_000.0,
            "cash": 1_200.0,
            "buying_power": 160_000.0,
            "long_market_value": 70_000.0,
        },
        [{"symbol": "MSFT", "qty": "20", "market_value": "70000"}],
    )
    assert plan.hft_clip == 0.0
    assert any("daily_profit_lock" in n for n in plan.notes)


def test_last_wins_has_one_point_five_lock():
    last = Path(__file__).resolve().parents[1].joinpath("data/deploy_scale.env").read_text()
    last = last.rsplit("leftover BP quality", 1)[-1]
    assert "DAY_TRADE_DAILY_PROFIT_PCT=0.015" in last
    assert "DAILY_RED_NO_NEW_ENTRIES=true" in last
    assert "KILL_FLATTEN_ON_HALT=false" in last
    assert "DAY_TRADE_MAX_DAILY_LOSS_PCT=0.002" in last
    assert "DAY_TRADE_MAX_DAILY_LOSS_PCT=0.01" not in last


def test_weekend_plan_does_not_zero_clips_from_friday_last_equity(monkeypatch):
    monkeypatch.setattr("analytics.day_trade_risk.session_et_date", lambda: "2026-09-20")
    monkeypatch.setenv("DAILY_RED_NO_NEW_ENTRIES", "true")
    monkeypatch.setenv("DAILY_RED_EPS_PCT", "0.0003")
    plan = plan_from_account(
        {
            "equity": 69_861.0,
            "last_equity": 70_280.0,
            "cash": 36_073.0,
            "buying_power": 154_000.0,
            "long_market_value": 33_788.0,
        },
        [{"symbol": "AAPL", "qty": "10", "market_value": "33788"}],
    )
    assert any("weekend_skip_inherited_last_equity_pnl" in n for n in plan.notes)
    assert not any("daily_red" in n for n in plan.notes)
    assert plan.hft_clip > 0
    assert plan.overnight_budget > 30_000


def test_weekend_does_not_inherit_friday_close_as_red(monkeypatch):
    monkeypatch.setattr("analytics.day_trade_risk.session_et_date", lambda: "2026-09-19")
    monkeypatch.setenv("DAILY_RED_EPS_PCT", "0.005")
    monkeypatch.setenv("DAY_TRADE_MAX_DAILY_LOSS_PCT", "0.008")
    ok, why = check_daily_limits(69_916.0, last_equity=70_280.0)
    assert ok is True
    assert why == ""
    assert is_trading_halted() is False


def test_weekend_still_halts_after_saturday_open_crash(monkeypatch):
    monkeypatch.setattr("analytics.day_trade_risk.session_et_date", lambda: "2026-09-19")
    monkeypatch.setenv("DAILY_RED_EPS_PCT", "0.005")
    monkeypatch.setenv("DAY_TRADE_MAX_DAILY_LOSS_PCT", "0.008")
    ok, why = check_daily_limits(70_000.0, last_equity=70_000.0)
    assert ok is True
    ok2, why2 = check_daily_limits(69_000.0, last_equity=70_000.0)
    assert ok2 is False
    assert why2 == "max-daily-loss"


def test_last_wins_stops_cutting_overnight_book():
    last = Path(__file__).resolve().parents[1].joinpath("data/deploy_scale.env").read_text()
    last = last.rsplit("stop false halt", 1)[-1]
    assert "PAPER_HYGIENE_AGGRESSIVE=false" in last
    assert "KILL_DAILY_LOSS_PCT=0.008" in last
    assert "KILL_FLATTEN_ON_HALT=false" in last
    assert "FORTRESS_OVERNIGHT_CASH_DEPLOY=true" in last
    assert "HFT_PACE_FILL=false" in last
    assert "MAX_GROSS_LEVERAGE=1.0" in last
