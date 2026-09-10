"""Overnight 1.0× cash gap — never 4× PDT, never $144 clips from a 500-name book."""

from __future__ import annotations

import pytest

from analytics.buying_power import (
    clip_ceiling_usd,
    fortress_ticket_usd,
    plan_from_account,
    sizing_slots,
)
from fortress_portfolio import deploy_budget_usd, fortress_order_notional


@pytest.fixture(autouse=True)
def _calculator_env(monkeypatch):
    monkeypatch.setenv("HARD_MAX_ORDER_NOTIONAL", "0")
    monkeypatch.setenv("MAX_ORDER_NOTIONAL", "0")
    monkeypatch.setenv("FORTRESS_GO_LIVE_MAX_NOTIONAL", "0")
    monkeypatch.setenv("ORDER_NOTIONAL", "0")
    monkeypatch.setenv("MIN_ORDER_NOTIONAL", "200")
    monkeypatch.setenv("FORTRESS_MAX_SINGLE_FRAC", "0.10")
    monkeypatch.setenv("MAX_SINGLE_ASSET_FRAC", "0.12")
    monkeypatch.setenv("FORTRESS_TARGET_DEPLOY_FRAC", "1.0")
    monkeypatch.setenv("FORTRESS_MAX_GROSS_FRAC", "1.0")
    monkeypatch.setenv("MAX_GROSS_LEVERAGE", "1.0")
    monkeypatch.setenv("FORTRESS_CASH_RESERVE_USD", "0")
    monkeypatch.setenv("HFT_MAX_ORDER_NOTIONAL", "0")
    monkeypatch.setenv("HFT_MIN_ORDER_NOTIONAL", "200")
    monkeypatch.setenv("HFT_MAX_CONCURRENT_SLOTS", "16")
    monkeypatch.setenv("HFT_BP_USE_FRAC", "0.85")
    monkeypatch.setenv("HFT_BP_RESERVE_USD", "200")
    monkeypatch.setenv("HFT_USE_DTBP", "true")
    monkeypatch.setenv("DAY_TRADE_MAX_NOTIONAL", "0")



def test_sizing_slots_ignores_500_placeholder(monkeypatch):
    monkeypatch.setenv("FORTRESS_MAX_POSITIONS", "500")
    monkeypatch.setenv("MAX_LIVE_SYMBOLS", "40")
    monkeypatch.setenv("FORTRESS_TOP_BUYS_PER_PASS", "24")
    n = sizing_slots()
    assert 8 <= n <= 80
    assert n == 24


def test_clip_ceiling_hard_max_zero_is_single_cap(monkeypatch):
    cap = clip_ceiling_usd(72_000.0)
    assert abs(cap - 72_000.0 * 0.10 * 0.995) < 1.0
    assert cap > 6_000
    assert cap < 8_000


def test_plan_idle_cash_is_equity_gap_not_margin(monkeypatch):
    monkeypatch.setenv("FORTRESS_MAX_POSITIONS", "500")
    monkeypatch.setenv("FORTRESS_TOP_BUYS_PER_PASS", "24")
    plan = plan_from_account(
        {
            "equity": 72_000.0,
            "cash": 19_000.0,
            "buying_power": 224_000.0,
            "daytrading_buying_power": 224_000.0,
            "long_market_value": 53_000.0,
        },
        [{"symbol": "AAPL", "qty": "10", "market_value": "53000"}],
    )
    assert abs(plan.overnight_budget - 19_000.0) < 1.0
    assert plan.overnight_budget < 50_000.0
    assert plan.overnight_clip >= 2_500.0
    assert plan.overnight_clip <= plan.single_cap + 1.0
    assert plan.overnight_budget != 224_000.0
    assert plan.hft_day_budget > 50_000.0
    assert plan.hft_clip >= 200.0
    assert plan.hft_clip <= plan.single_cap + 1.0


def test_plan_uses_get_v2_account_buying_power_without_dtbp(monkeypatch):
    """Alpaca removed daytrading_buying_power on 2026-07-06 — live field is buying_power."""
    plan = plan_from_account(
        {
            "equity": "72000",
            "last_equity": "71000",
            "cash": "19000",
            "buying_power": "224000",
            "regt_buying_power": "144000",
            "long_market_value": "53000",
        },
        [{"symbol": "AAPL", "qty": "10", "market_value": "53000"}],
    )
    assert abs(plan.overnight_budget - 19_000.0) < 1.0
    assert abs(plan.buying_power - 224_000.0) < 1.0
    assert abs(plan.day_buying_power - 224_000.0) < 1.0
    assert plan.daily_pnl > 0
    assert plan.hft_day_budget > 50_000.0
    assert plan.to_dict()["source"] == "GET /v2/account"


def test_hold_is_green_skips_red_and_allows_new(monkeypatch):
    from analytics.buying_power import hold_is_green

    monkeypatch.setenv("FORTRESS_WINNERS_ONLY", "true")
    monkeypatch.setenv("FORTRESS_MIN_ADD_GAIN", "0")
    assert hold_is_green(None) is True
    assert hold_is_green(0.04) is True
    assert hold_is_green(0.0) is False
    assert hold_is_green(-0.08) is False


def test_plan_infers_cash_when_alpaca_omits_it():
    plan = plan_from_account(
        {
            "equity": 72_000.0,
            "cash": 0.0,
            "buying_power": 224_000.0,
            "long_market_value": 53_000.0,
        },
        [{"symbol": "MSFT", "qty": "1", "market_value": "53000"}],
    )
    assert abs(plan.cash - 19_000.0) < 1.0
    assert abs(plan.overnight_budget - 19_000.0) < 1.0


def test_deploy_budget_still_19k(monkeypatch):
    monkeypatch.setenv("FORTRESS_TARGET_DEPLOY_USE_EQUITY", "true")
    monkeypatch.setenv("FORTRESS_TARGET_DEPLOY_FRAC", "1.0")
    monkeypatch.setenv("FORTRESS_MAX_GROSS_FRAC", "1.0")
    monkeypatch.setenv("FORTRESS_BP_USE_FRAC", "1.0")
    monkeypatch.setenv("FORTRESS_FILL_IDLE_CASH", "true")
    monkeypatch.setenv("USE_BUYING_POWER", "true")
    monkeypatch.setenv("FORTRESS_EXPOSURE_USE_BP", "false")
    bud = deploy_budget_usd(
        {
            "equity": 72_000.0,
            "cash": 19_000.0,
            "buying_power": 224_000.0,
            "gross_mv": 53_000.0,
            "multiplier": 4.0,
        }
    )
    assert abs(bud["budget"] - 19_000.0) < 1.0
    assert bud["clip_ceiling"] > 6_000


def test_fortress_ticket_uses_leftover_not_slot_crumbs():
    n = fortress_ticket_usd(equity=72_000.0, existing_mv=0.0, leftover_budget=19_000.0)
    assert n >= 6_000
    assert n <= 7_200


def test_fortress_order_notional_fills_idle_cash(monkeypatch):
    monkeypatch.setenv("FORTRESS_MAX_POSITIONS", "500")
    monkeypatch.setenv("MAX_LIVE_SYMBOLS", "40")
    monkeypatch.setenv("FORTRESS_TOP_BUYS_PER_PASS", "24")
    monkeypatch.setenv("FORTRESS_ALLOW_DCA", "false")
    monkeypatch.setenv("FORTRESS_TARGET_DEPLOY_FRAC", "1.0")
    monkeypatch.setenv("FORTRESS_MAX_GROSS_FRAC", "1.0")
    monkeypatch.setenv("FORTRESS_TARGET_DEPLOY_USE_EQUITY", "true")
    monkeypatch.setenv("FORTRESS_SINGLE_CAP_USE_EQUITY", "true")
    monkeypatch.setenv("FORTRESS_MAX_SINGLE_FRAC", "0.10")
    monkeypatch.setenv("MAX_SINGLE_ASSET_FRAC", "0.12")
    monkeypatch.setenv("FORTRESS_BP_USE_FRAC", "1.0")
    monkeypatch.setenv("USE_BUYING_POWER", "true")
    monkeypatch.setenv("FORTRESS_EXPOSURE_USE_BP", "false")
    monkeypatch.setenv("TOP100_NOTIONAL_MULT", "1.0")
    monkeypatch.setattr("intel.downward_pressure.exit_adjustments", lambda *_a, **_k: {"pressure_score": 0.0})
    monkeypatch.setattr("analytics.conviction_exit.conviction_size_mult", lambda *_a, **_k: 1.0)
    monkeypatch.setattr("analytics.catalyst_horizon.max_equity_size_mult", lambda *_a, **_k: 1.0)
    monkeypatch.setattr("fortress_universe.is_top100_equity", lambda *_a, **_k: False)
    n = fortress_order_notional(
        ticker="ZZZZ",
        p_adj=0.72,
        scale=1.0,
        portfolio={
            "equity": 72_000.0,
            "cash": 19_000.0,
            "buying_power": 500.0,
            "gross_mv": 53_000.0,
            "multiplier": 4.0,
        },
        existing_mv=0.0,
        existing_gain=None,
    )
    assert n >= 2_500
    assert n <= 7_300


def test_last_wins_buying_power_calculator():
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "data" / "deploy_scale.env").read_text()
    last = text.rsplit("buying-power calculator", 1)[-1]
    assert "HARD_MAX_ORDER_NOTIONAL=0" in last
    assert "FORTRESS_GO_LIVE_MAX_NOTIONAL=0" in last
    assert "ORDER_NOTIONAL=0" in last
    assert "FORTRESS_MAX_POSITIONS=40" in last
    assert "FORTRESS_ALLOW_DCA=false" in last
    assert "FORTRESS_WINNERS_ONLY=true" in last
    assert "HFT_MAX_ORDER_NOTIONAL=0" in last
    assert "HFT_BLOCK_ADD_TO_BROKER_LONG=true" in last
    assert "MAX_GROSS_LEVERAGE=1.0" in last
    assert "ALPACA_OPTIONS_ENABLED=false" in last


def test_run_all_sources_deploy_scale_after_dotenv():
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "run_all.sh").read_text()
    head = text.split("Yahoo-first")[0]
    assert 'ROOT/.env' in head
    assert "deploy_scale.env" in head
    assert head.find(".env") < head.find("deploy_scale.env")

