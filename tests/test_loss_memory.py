"""A down day must cut losers and the next entry on that name must be smaller."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def test_red_day_cuts_loser_and_keeps_winner(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADE_QUALITY_PATH", str(tmp_path / "tq.json"))
    from analytics.conviction_exit import decide_exit

    loser = decide_exit(
        "AAPL",
        p_adj=0.70,
        gain=-0.011,
        take_profit_pct=0.035,
        stop_loss_pct=0.028,
        session_pnl=-0.012,
    )
    assert loser.action == "stop_loss"
    assert "red_day_cut" in loser.reason
    winner = decide_exit(
        "NVDA",
        p_adj=0.70,
        gain=0.02,
        take_profit_pct=0.035,
        stop_loss_pct=0.028,
        session_pnl=-0.012,
    )
    assert winner.action != "stop_loss"


def test_loss_then_win_clears_penalty(monkeypatch, tmp_path):
    monkeypatch.setenv("LOSS_MEMORY_PATH", str(tmp_path / "loss.json"))
    from analytics.loss_memory import advise, record_outcome

    record_outcome("TSLA", -0.02, source="test")
    one = advise("TSLA")
    assert one["size_mult"] == 0.45
    assert one["extra_conviction"] == 0.06
    record_outcome("TSLA", -0.01, source="test")
    two = advise("TSLA")
    assert two["size_mult"] == 0.25
    assert two["extra_conviction"] == 0.10
    record_outcome("TSLA", 0.015, source="test")
    assert advise("TSLA")["size_mult"] == 1.0


def test_add_does_not_reset_position_clock(monkeypatch, tmp_path):
    monkeypatch.setenv("POSITION_CLOCK_PATH", str(tmp_path / "clock.json"))
    from analytics.position_clock import age_minutes, note_open

    note_open("AAPL", 10)
    note_open("AAPL", 25)
    later = datetime.now(timezone.utc) + timedelta(minutes=40)
    age = age_minutes("AAPL", now=later)
    assert age is not None and age >= 39
    note_open("AAPL", 0)
    assert age_minutes("AAPL") is None


def test_saved_votes_credit_without_process_memory(monkeypatch, tmp_path):
    monkeypatch.setenv("PROVEN_VOTES_PATH", str(tmp_path / "votes.json"))
    monkeypatch.setenv("PROVEN_ONLINE_STATE", str(tmp_path / "state.json"))
    import analytics.proven_online as po

    po._LAST_VOTES.clear()
    po._remember_votes("ZZZ", {k: 1 for k in po.EXPERTS})
    po._LAST_VOTES.clear()
    out = po.credit_outcome("ZZZ", -0.02, side="LONG", persist=False)
    assert out["applied"] is True
    assert out["win"] is False


def test_agreed_crash_still_has_a_stop():
    import fortress_live as fl

    gain = fl._position_unrealized_gain(
        {"avg_entry_price": 100, "unrealized_plpc": -0.62},
        38,
    )
    assert gain is not None and gain < -0.50
    phantom = fl._position_unrealized_gain(
        {"avg_entry_price": 100, "unrealized_plpc": 1.75},
        101,
    )
    assert phantom is not None and abs(phantom) < 0.05


def test_protective_exit_ignores_min_hold(monkeypatch):
    import fortress_live as fl

    monkeypatch.setattr(fl, "_respect_min_hold", lambda *_a, **_k: False)
    assert fl._exit_blocked_by_min_hold("stop_loss", "AAPL", -0.02, 0.028) is False
    assert fl._exit_blocked_by_min_hold("take_profit", "AAPL", 0.02, 0.028) is False
    assert fl._exit_blocked_by_min_hold("signal_sell", "AAPL", -0.002, 0.028) is True
