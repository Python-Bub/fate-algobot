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
    # Through the daily-loss line a scratch loser is cut. A small red session
    # still keeps a name that is only a few bps underwater.
    deep = decide_exit(
        "MSFT",
        p_adj=0.70,
        gain=-0.001,
        take_profit_pct=0.035,
        stop_loss_pct=0.028,
        session_pnl=-0.012,
    )
    assert deep.action == "stop_loss"
    assert "red_day_cut" in deep.reason
    scratch = decide_exit(
        "AMD",
        p_adj=0.70,
        gain=-0.001,
        take_profit_pct=0.035,
        stop_loss_pct=0.028,
        session_pnl=-0.006,
    )
    assert scratch.action != "stop_loss"
    mild = decide_exit(
        "META",
        p_adj=0.70,
        gain=-0.004,
        take_profit_pct=0.035,
        stop_loss_pct=0.028,
        session_pnl=-0.006,
    )
    assert mild.action == "stop_loss"
    # A book of -0.2% losers was the "down so much" day. The old -0.3% gate kept them.
    small = decide_exit(
        "AMZN",
        p_adj=0.70,
        gain=-0.002,
        take_profit_pct=0.035,
        stop_loss_pct=0.028,
        session_pnl=-0.006,
    )
    assert small.action == "stop_loss"
    assert "red_day_cut" in small.reason


def test_loss_then_win_clears_penalty(monkeypatch, tmp_path):
    monkeypatch.setenv("LOSS_MEMORY_PATH", str(tmp_path / "loss.json"))
    from analytics.loss_memory import advise, record_outcome

    later = datetime.now(timezone.utc) + timedelta(days=2)
    record_outcome("TSLA", -0.02, source="test")
    one = advise("TSLA", now=later)
    assert one["same_day"] is False
    assert one["size_mult"] == 0.45
    assert one["extra_conviction"] == 0.06
    record_outcome("TSLA", -0.01, source="test")
    two = advise("TSLA", now=later)
    assert two["size_mult"] == 0.25
    assert two["extra_conviction"] == 0.10
    record_outcome("TSLA", 0.015, source="test")
    assert advise("TSLA", now=later)["size_mult"] == 1.0


def test_same_day_loss_is_not_reopened(monkeypatch, tmp_path):
    monkeypatch.setenv("LOSS_MEMORY_PATH", str(tmp_path / "loss.json"))
    from analytics.loss_memory import advise, record_outcome

    record_outcome("NVDA", -0.03, source="test")
    hit = advise("NVDA")
    assert hit["same_day"] is True
    assert hit["size_mult"] == 0.0
    assert hit["extra_conviction"] == 1.0
    assert "today" in hit["reason"]


def test_down_day_uses_last_equity_when_the_session_file_is_empty(monkeypatch, tmp_path):
    monkeypatch.setenv("DAY_TRADE_SESSION_PATH", str(tmp_path / "missing.json"))
    import fortress_live as fl

    fl._PASS_SESSION_PNL = None
    pnl = fl._remember_session_pnl(69_000.0, 70_000.0)
    assert pnl is not None and pnl < -0.01


def test_session_pnl_frac_uses_today_anchor(monkeypatch, tmp_path):
    monkeypatch.setenv("DAY_TRADE_SESSION_PATH", str(tmp_path / "sess.json"))
    from analytics.day_trade_risk import session_et_date, session_pnl_frac
    import fortress_live as fl

    (tmp_path / "sess.json").write_text(
        '{"date": "%s", "start_equity": 100000}' % session_et_date(),
        encoding="utf-8",
    )
    pnl = session_pnl_frac(99000)
    assert pnl is not None and abs(pnl - (-0.01)) < 1e-9
    remembered = fl._remember_session_pnl(99000)
    assert remembered is not None and abs(remembered - (-0.01)) < 1e-9
    (tmp_path / "sess.json").write_text(
        '{"date": "2000-01-01", "start_equity": 100000}',
        encoding="utf-8",
    )
    assert session_pnl_frac(99000) is None
    assert fl._remember_session_pnl(98000) == remembered


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
