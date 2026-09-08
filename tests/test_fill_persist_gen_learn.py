"""Fill persist + residual momentum + next-gen combiner. No network."""

from __future__ import annotations

import numpy as np
import pandas as pd

from analytics.fill_persist import may_cancel_stale_buy, reprice_buy_limit
from analytics.gen_learn import FEATURE_NAMES, fit_and_deploy, mix_p, vectorize
from analytics.proven_online import CORE_EXPERTS, EXPERTS, expert_votes, tight_pick
from analytics.residual_mom import attach_resid_mom, residual_mom_12_1


def test_reprice_moves_buy_to_bid(monkeypatch):
    monkeypatch.setenv("ALPACA_MAX_QUOTE_SPREAD_PCT", "0.02")
    monkeypatch.setenv("ALPACA_BUY_REPRICE_BELOW_BID_BPS", "25")
    new = reprice_buy_limit(99.00, 100.00, 100.05)
    assert new is not None
    assert abs(new - 100.00) < 1e-9
    # Already at/near bid → leave it.
    assert reprice_buy_limit(100.00, 100.00, 100.05) is None


def test_persist_does_not_cancel_unfillable():
    assert may_cancel_stale_buy(unfillable=True, held_no_addon=False) is False
    assert may_cancel_stale_buy(unfillable=True, held_no_addon=True) is True


def test_resid_mom_positive_vs_spy():
    idx = pd.bdate_range("2020-01-02", periods=400)
    stock = pd.Series(np.linspace(100.0, 180.0, len(idx)), index=idx)
    spy = pd.Series(np.linspace(100.0, 110.0, len(idx)), index=idx)
    rm = residual_mom_12_1(stock, spy)
    assert rm > 0.05
    row = attach_resid_mom({}, stock, spy)
    assert float(row["resid_mom_12_1"]) > 0


def test_resid_mom_expert_votes():
    v = expert_votes(p_up=0.70, exec_c=0.70, mom_5d=0.03, rs_spy=1.01, hmm=0.1, row={"resid_mom_12_1": 0.12})
    assert "resid_mom" in EXPERTS
    assert v["resid_mom"] == 1
    assert "resid_mom" not in CORE_EXPERTS


def test_tight_still_works_with_resid(tmp_path, monkeypatch):
    monkeypatch.setenv("USE_PROVEN_ONLINE", "true")
    monkeypatch.setenv("USE_TIGHT_PICKS", "true")
    monkeypatch.setenv("USE_GEN_LEARN", "false")
    monkeypatch.setattr("analytics.proven_online.STATE_PATH", tmp_path / "st.json")
    strong = tight_pick(
        "NVDA",
        p_up=0.72,
        exec_c=0.70,
        mom_5d=0.04,
        rs_spy=1.02,
        hmm=0.0,
        use_live_events=False,
    )
    assert strong["ok"] is True
    assert "resid_mom" in strong["votes"]


def test_gen_learn_deploys_when_ic_real(tmp_path, monkeypatch):
    monkeypatch.setenv("USE_GEN_LEARN", "true")
    monkeypatch.setenv("GEN_LEARN_MIN_IC", "0.02")
    monkeypatch.setattr("analytics.gen_learn.STATE_PATH", tmp_path / "st.json")
    monkeypatch.setattr("analytics.gen_learn.REPORT_PATH", tmp_path / "rep.json")
    rng = np.random.default_rng(7)
    n = 900
    X = np.zeros((n, len(FEATURE_NAMES)))
    y = np.zeros(n)
    X[:, 0] = 1.0
    # tsmom vote (index 2) predicts the next return.
    votes_ts = rng.choice([-1.0, 1.0], size=n)
    X[:, 2] = votes_ts
    y = 0.004 * votes_ts + rng.normal(0, 0.001, n)
    out = fit_and_deploy(X, y, min_train=400)
    assert out.get("ok") is True
    assert float(out.get("ic") or 0) > 0.05
    assert float(out.get("skill") or 0) > 0.02
    p, meta = mix_p(0.55, {"tsmom": 1}, p_up=0.55, mom_5d=0.03, rs_spy=1.02)
    assert meta.get("applied") is True
    assert 0.01 < p < 0.99


def test_vectorize_shape():
    x = vectorize({"model": 1, "tsmom": 1}, resid_raw=0.1, mom_5d=0.02, rs_spy=1.01, p_up=0.7)
    assert x.shape == (len(FEATURE_NAMES),)
    assert x[0] == 1.0
