"""Fortress ranking must include proven / event / industry — not only edge+exec."""

from analytics.rank_pipeline import fortress_buy_score, fortress_learner_delta


def test_learner_delta_is_finite(monkeypatch):
    monkeypatch.setenv("USE_PROVEN_ONLINE", "true")
    monkeypatch.setenv("USE_EVENT_LEARN", "true")
    monkeypatch.setenv("USE_INDUSTRY_PIPELINE", "true")
    d = fortress_learner_delta(ticker="AAPL", p_up=0.62, exec_c=0.61, mom_5d=0.01, rs_spy=1.02)
    assert isinstance(d, float)
    assert d == d  # not NaN


def test_fortress_buy_score_accepts_ticker(monkeypatch):
    monkeypatch.setenv("USE_UNIFIED_RANK_PIPELINE", "true")
    a = fortress_buy_score(p_adj=0.62, exec_c=0.61, sent=0.1, nf_f=0.05, top100=True)
    b = fortress_buy_score(
        p_adj=0.62,
        exec_c=0.61,
        sent=0.1,
        nf_f=0.05,
        top100=True,
        ticker="AAPL",
        mom_5d=0.02,
        rs_spy=1.01,
    )
    assert isinstance(a, float) and isinstance(b, float)
