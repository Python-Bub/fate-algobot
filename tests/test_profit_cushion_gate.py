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


def test_fortress_take_profit_uses_earned_target(gate_path, monkeypatch):
    monkeypatch.setenv("HFT_PROFIT_CUSHION_MIN_PCT", "0.003")
    monkeypatch.setenv("FORTRESS_EARNED_SELL_PCT", "0.010")
    gate_path.write_text(json.dumps({"earned": {"COST": 0.004}}))
    gate._LAST = None
    assert gate.fortress_take_profit_pct("COST", 0.015) == pytest.approx(0.010)
    assert gate.fortress_take_profit_pct("XYZ", 0.015) == pytest.approx(0.015)
