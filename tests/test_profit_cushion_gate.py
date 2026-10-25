import json
import os
from unittest.mock import patch

import pytest

from analytics import profit_cushion_gate as gate


@pytest.fixture
def gate_path(tmp_path, monkeypatch):
    p = tmp_path / "profit_cushion_gate.json"
    monkeypatch.setenv("PROFIT_CUSHION_GATE_PATH", str(p))
    gate._LAST = None
    return p


def test_refresh_writes_earned_symbols(gate_path):
    positions = [
        {"symbol": "NVDA", "qty": 10, "unrealized_plpc": 0.005},
        {"symbol": "MSFT", "qty": 5, "unrealized_plpc": 0.001},
    ]
    with patch("alpaca_broker.list_positions", return_value=positions), patch(
        "alpaca_broker.get_account", return_value={"equity": 100_000}
    ):
        out = gate.refresh_profit_gate()
    assert "NVDA" in out["earned"]
    assert "MSFT" not in out["earned"]
    assert gate_path.is_file()
    saved = json.loads(gate_path.read_text())
    assert saved["earned"]["NVDA"] == pytest.approx(0.005)


def test_phantom_cost_basis_is_not_earned(gate_path):
    positions = [
        {
            "symbol": "AAPL",
            "qty": 0.01,
            "avg_entry_price": -3280.0,
            "unrealized_plpc": 1.76,
            "current_price": 337.0,
        },
        {"symbol": "NVDA", "qty": 10, "unrealized_plpc": 0.005},
    ]
    with patch("alpaca_broker.list_positions", return_value=positions), patch(
        "alpaca_broker.get_account", return_value={"equity": 71_000}
    ):
        out = gate.refresh_profit_gate()
    assert "AAPL" not in out["earned"]
    assert "NVDA" in out["earned"]


def test_fortress_take_profit_ignores_earned_cushion(gate_path, monkeypatch):
    monkeypatch.setenv("HFT_PROFIT_CUSHION_MIN_PCT", "0.003")
    monkeypatch.setenv("FORTRESS_EARNED_SELL_PCT", "0.010")
    gate_path.write_text(json.dumps({"earned": {"COST": 0.004}}))
    gate._LAST = None
    # A green earned name must not tighten a wider target or turn 0 back on.
    assert gate.fortress_take_profit_pct("COST", 0.015) == pytest.approx(0.015)
    assert gate.fortress_take_profit_pct("XYZ", 0.015) == pytest.approx(0.015)
    assert gate.fortress_take_profit_pct("COST", 0.0) == pytest.approx(0.0)
    assert gate.fortress_take_profit_pct("XYZ", 0.0) == pytest.approx(0.0)


def test_a_non_positive_take_profit_does_not_sell():
    from analytics.conviction_exit import decide_exit

    off = decide_exit(
        "KO",
        p_adj=0.8,
        gain=0.04,
        take_profit_pct=0.0,
        stop_loss_pct=0.08,
        better_candidate_waiting=True,
    )
    on = decide_exit(
        "KO",
        p_adj=0.8,
        gain=0.04,
        take_profit_pct=0.035,
        stop_loss_pct=0.08,
    )
    stopped = decide_exit(
        "KO",
        p_adj=0.8,
        gain=-0.09,
        take_profit_pct=0.0,
        stop_loss_pct=0.08,
    )
    assert off.action == "hold"
    assert on.action == "take_profit"
    assert stopped.action == "stop_loss"


def test_small_green_holds_without_scale_out(monkeypatch):
    from analytics.conviction_exit import decide_exit, scale_out_qty

    monkeypatch.delenv("FORTRESS_SCALE_OUT_ENABLED", raising=False)
    monkeypatch.delenv("FORTRESS_ROTATE_ON_PROFIT", raising=False)
    held = decide_exit(
        "META",
        p_adj=0.7,
        gain=0.02,
        take_profit_pct=0.0,
        stop_loss_pct=0.08,
        better_candidate_waiting=True,
    )
    assert held.action == "hold"
    assert scale_out_qty(1, 0.5) == pytest.approx(0.5)
    assert scale_out_qty(1.7, 0.5) == pytest.approx(0.85)
    assert scale_out_qty(0.4, 0.5) == pytest.approx(0.2)
    assert scale_out_qty(10, 0.5) == pytest.approx(5)
    assert scale_out_qty(3, 1.5) == pytest.approx(3)


def test_scale_out_still_runs_when_explicitly_armed(monkeypatch):
    from analytics.conviction_exit import decide_exit

    monkeypatch.setenv("FORTRESS_SCALE_OUT_ENABLED", "true")
    monkeypatch.setenv("FORTRESS_ROTATE_ON_PROFIT", "true")
    monkeypatch.setenv("FORTRESS_SCALE_OUT_PCT", "0.008")
    monkeypatch.setenv("FORTRESS_ROTATE_MIN_GAIN", "0.006")
    scaled = decide_exit(
        "META",
        p_adj=0.7,
        gain=0.02,
        take_profit_pct=0.0,
        stop_loss_pct=0.08,
    )
    rotated = decide_exit(
        "META",
        p_adj=0.7,
        gain=0.007,
        take_profit_pct=0.0,
        stop_loss_pct=0.08,
        better_candidate_waiting=True,
    )
    assert scaled.action == "scale_out"
    assert scaled.trim_frac == pytest.approx(0.5)
    assert rotated.action == "scale_out"
    assert rotated.trim_frac == pytest.approx(0.4)
