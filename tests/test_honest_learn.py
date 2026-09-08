"""Honest hist: one credit per trade, lagged features, leak map is forbidden."""

from analytics.honest_learn import already_credited, credit_once, trade_key
from analytics.honest_walkforward import leaked_edge, lagged_edge, run_synthetic
from analytics.asymmetric_loss import asymmetric_reward


def test_credit_once_blocks_retry(tmp_path, monkeypatch):
    monkeypatch.setenv("HONEST_CREDIT_FILE", str(tmp_path / "keys.json"))
    key = trade_key("AAPL", entry_ts="2024-01-03", side="LONG")
    n = {"n": 0}

    def bump():
        n["n"] += 1
        return n["n"]

    a = credit_once(key, bump)
    b = credit_once(key, bump)
    assert a["applied"] is True
    assert b["applied"] is False
    assert b["reason"] == "already_credited"
    assert n["n"] == 1
    assert already_credited(key)


def test_lag_is_not_same_bar():
    import pandas as pd

    rets = pd.Series([0.10, -0.05, 0.20, 0.01])
    lag = lagged_edge(rets)
    leak = leaked_edge(rets)
    assert float(lag.iloc[-1]) == 0.20
    assert float(lag.iloc[-1]) != float(rets.iloc[-1])
    # Look-ahead: bar -2's "feature" is tomorrow's return (the label).
    assert float(leak.iloc[-2]) == float(rets.iloc[-1])


def test_asymmetric_reward_penalizes_losses_harder():
    win = asymmetric_reward("LONG", 0.02, bars_held=1)
    loss = asymmetric_reward("LONG", -0.02, bars_held=1)
    assert win.correct is True
    assert loss.correct is False
    assert abs(loss.reward) > abs(win.reward)


def test_synthetic_walkforward_does_not_cook_the_map(tmp_path, monkeypatch):
    monkeypatch.setenv("HONEST_CREDIT_FILE", str(tmp_path / "keys.json"))
    monkeypatch.setenv("ASYM_POSITION_PNL", "true")
    rep = run_synthetic(n=180, seed=11)
    # Leak uses same-bar return as a feature — that is the forbidden perfect map.
    assert rep.leak_beats_honest
    # Honest path is allowed to be red. We record why; we do not flip labels.
    if rep.red:
        assert "friction" in rep.why_red
        assert "relabel" in rep.why_red
    assert rep.n_trades >= 1
    # Never claim the leak path is the live book.
    assert rep.leak_pnl != 0.0 or rep.net_pnl <= 0.0
