"""Monthly DD halt must not park idle cash while under the deploy target."""

import json
from datetime import datetime, timezone


def test_monthly_dd_still_halts_when_fully_deployed(monkeypatch, tmp_path):
    from risk_manager import monthly_drawdown_ok

    monkeypatch.setenv("USE_MONTHLY_DRAWDOWN_HALT", "true")
    monkeypatch.setenv("MONTHLY_DRAWDOWN_HALT_PCT", "0.20")
    monkeypatch.setenv("MONTHLY_EQUITY_STATE_FILE", str(tmp_path / "monthly.json"))
    monkeypatch.delenv("FORTRESS_FILL_SKIP_MONTHLY_DD", raising=False)
    monkeypatch.delenv("DOWNPRESS_SOFT_OK_WHEN_UNDERDEPLOY", raising=False)
    mk = f"{datetime.now(timezone.utc).year:04d}-{datetime.now(timezone.utc).month:02d}"
    (tmp_path / "monthly.json").write_text(
        json.dumps({"month_key": mk, "start_equity": 100_000.0, "peak_equity": 100_000.0})
    )
    ok, why = monthly_drawdown_ok(72_000.0)
    assert not ok
    assert "monthly_dd" in why


def test_monthly_dd_allows_fill_when_cash_idle(monkeypatch, tmp_path):
    from risk_manager import monthly_drawdown_ok

    monkeypatch.setenv("USE_MONTHLY_DRAWDOWN_HALT", "true")
    monkeypatch.setenv("MONTHLY_DRAWDOWN_HALT_PCT", "0.20")
    monkeypatch.setenv("FORTRESS_FILL_SKIP_MONTHLY_DD", "true")
    monkeypatch.setenv("MONTHLY_EQUITY_STATE_FILE", str(tmp_path / "monthly.json"))
    mk = f"{datetime.now(timezone.utc).year:04d}-{datetime.now(timezone.utc).month:02d}"
    (tmp_path / "monthly.json").write_text(
        json.dumps({"month_key": mk, "start_equity": 100_000.0, "peak_equity": 100_000.0})
    )
    ok, why = monthly_drawdown_ok(72_000.0)
    assert ok
    assert why == "monthly_dd_fill_idle"


def test_dummy_paper_equity_does_not_raise_live_peak(monkeypatch, tmp_path):
    from risk_manager import monthly_drawdown_ok

    monkeypatch.setenv("USE_MONTHLY_DRAWDOWN_HALT", "true")
    monkeypatch.setenv("MONTHLY_DRAWDOWN_HALT_PCT", "0.15")
    monkeypatch.setenv("PAPER_EQUITY", "100000")
    monkeypatch.setenv("PAPER_SIM_ACTIVE_RUN", "true")
    monkeypatch.setenv("MONTHLY_EQUITY_STATE_FILE", str(tmp_path / "monthly.json"))
    monkeypatch.delenv("FORTRESS_FILL_SKIP_MONTHLY_DD", raising=False)
    monkeypatch.delenv("DOWNPRESS_SOFT_OK_WHEN_UNDERDEPLOY", raising=False)
    mk = f"{datetime.now(timezone.utc).year:04d}-{datetime.now(timezone.utc).month:02d}"
    (tmp_path / "monthly.json").write_text(
        json.dumps({"month_key": mk, "start_equity": 74519.79, "peak_equity": 74519.79})
    )
    ok, why = monthly_drawdown_ok(100_000.0)
    assert ok
    assert why == "monthly_dd_paper_sim_isolated"
    st = json.loads((tmp_path / "monthly.json").read_text())
    assert st["peak_equity"] == 74519.79


def test_underdeploy_flag_does_not_skip_monthly_dd(monkeypatch, tmp_path):
    from risk_manager import monthly_drawdown_ok

    monkeypatch.setenv("USE_MONTHLY_DRAWDOWN_HALT", "true")
    monkeypatch.setenv("MONTHLY_DRAWDOWN_HALT_PCT", "0.20")
    monkeypatch.setenv("DOWNPRESS_SOFT_OK_WHEN_UNDERDEPLOY", "true")
    monkeypatch.delenv("FORTRESS_FILL_SKIP_MONTHLY_DD", raising=False)
    monkeypatch.setenv("MONTHLY_EQUITY_STATE_FILE", str(tmp_path / "monthly.json"))
    mk = f"{datetime.now(timezone.utc).year:04d}-{datetime.now(timezone.utc).month:02d}"
    (tmp_path / "monthly.json").write_text(
        json.dumps({"month_key": mk, "start_equity": 100_000.0, "peak_equity": 100_000.0})
    )
    ok, why = monthly_drawdown_ok(72_000.0)
    assert not ok
    assert "monthly_dd" in why


def test_poisoned_100k_peak_is_rebased(monkeypatch, tmp_path):
    from risk_manager import monthly_drawdown_ok

    monkeypatch.setenv("USE_MONTHLY_DRAWDOWN_HALT", "true")
    monkeypatch.setenv("MONTHLY_DRAWDOWN_HALT_PCT", "0.15")
    monkeypatch.setenv("PAPER_EQUITY", "100000")
    monkeypatch.setenv("PAPER_SIM_ACTIVE_RUN", "false")
    monkeypatch.setenv("MONTHLY_EQUITY_STATE_FILE", str(tmp_path / "monthly.json"))
    monkeypatch.delenv("FORTRESS_FILL_SKIP_MONTHLY_DD", raising=False)
    monkeypatch.delenv("DOWNPRESS_SOFT_OK_WHEN_UNDERDEPLOY", raising=False)
    mk = f"{datetime.now(timezone.utc).year:04d}-{datetime.now(timezone.utc).month:02d}"
    (tmp_path / "monthly.json").write_text(
        json.dumps({"month_key": mk, "start_equity": 74519.79, "peak_equity": 100000.0})
    )
    ok, why = monthly_drawdown_ok(75_000.0)
    assert ok
    assert why == "monthly_dd_ok"
    st = json.loads((tmp_path / "monthly.json").read_text())
    assert st["peak_equity"] == 75000.0

