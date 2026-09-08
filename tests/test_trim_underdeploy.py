"""Do not sell overweight names while the book is under the deploy target."""

from analytics.market_session import Session


def test_trim_skipped_when_cash_idle(monkeypatch):
    from fortress_portfolio import trim_overweight_singles

    closed: list = []
    monkeypatch.setenv("FORTRESS_TRIM_OVERWEIGHT", "true")
    monkeypatch.setenv("FORTRESS_TARGET_DEPLOY_FRAC", "1.0")
    monkeypatch.setenv("FORTRESS_MAX_SINGLE_FRAC", "0.10")
    monkeypatch.setattr("analytics.market_session.current_session", lambda: Session.REGULAR)
    monkeypatch.setattr("alpaca_broker.get_account", lambda: {"equity": 72_000.0})
    monkeypatch.setattr(
        "alpaca_broker.list_positions",
        lambda: [{"symbol": "SBUX", "qty": "80", "market_value": "8000"}],
    )
    monkeypatch.setattr(
        "alpaca_broker.close_position_alpaca",
        lambda *a, **k: closed.append(1) or True,
    )
    assert trim_overweight_singles() == 0
    assert closed == []


def test_trim_runs_when_near_target(monkeypatch):
    from fortress_portfolio import trim_overweight_singles

    closed: list = []
    monkeypatch.setenv("FORTRESS_TRIM_OVERWEIGHT", "true")
    monkeypatch.setenv("FORTRESS_TARGET_DEPLOY_FRAC", "1.0")
    monkeypatch.setenv("FORTRESS_MAX_SINGLE_FRAC", "0.10")
    monkeypatch.setattr("analytics.market_session.current_session", lambda: Session.REGULAR)
    monkeypatch.setattr("alpaca_broker.get_account", lambda: {"equity": 72_000.0})
    monkeypatch.setattr(
        "alpaca_broker.list_positions",
        lambda: [{"symbol": "SBUX", "qty": "80", "market_value": "68000"}],
    )
    monkeypatch.setattr(
        "alpaca_broker.close_position_alpaca",
        lambda *a, **k: closed.append(1) or True,
    )
    assert trim_overweight_singles() == 1
    assert closed
