"""Insider sells, pre-earnings defensive language, liquidity impact."""

from __future__ import annotations

import os

import pytest


def test_defensive_phrase_detection():
    from intel.earnings_defensive_signals import scan_documents

    scan = scan_documents(
        [
            "CEO said the rollout didn't work but don't worry earnings might not be that high",
            "We see headwinds in the quarter ahead",
        ]
    )
    assert scan["n_hits"] >= 2
    assert scan["intensity"] > 0.4


def test_defensive_inactive_far_from_earnings():
    from intel.earnings_defensive_signals import assess_pre_earnings_defensive

    res = assess_pre_earnings_defensive(
        "TEST",
        documents=["didn't work don't worry earnings might not be that high"],
        days_to_earnings=60,
    )
    assert not res["active"]


def test_defensive_active_near_earnings():
    from intel.earnings_defensive_signals import assess_pre_earnings_defensive

    res = assess_pre_earnings_defensive(
        "TEST",
        documents=["Management said this didn't work and earnings may not be as high as hoped"],
        days_to_earnings=5,
    )
    assert res["active"]
    assert res["score_delta"] < 0


def test_insider_disabled_returns_neutral():
    os.environ["ENABLE_INSIDER_PROXY"] = "false"
    try:
        from intel.insider_signals import assess_insider_flow

        flow = assess_insider_flow("AAPL")
        assert flow["factor"] == 0.0
        assert not flow["block_long"]
    finally:
        os.environ["ENABLE_INSIDER_PROXY"] = "true"


def test_liquidity_caps_large_order():
    from analytics.liquidity_impact import assess_order_liquidity

    liq = assess_order_liquidity("TEST", 50_000_000, 100.0)
    assert liq["participation_rate"] > liq["max_participation"]
    assert liq["effective_notional_usd"] < 50_000_000
    assert liq["fill_ratio"] < 1.0


def test_liquidity_small_order_ok():
    from analytics.liquidity_impact import assess_order_liquidity

    liq = assess_order_liquidity("TEST", 500, 50.0)
    assert liq["fill_ratio"] >= 0.35
    assert not liq["block_order"]


def test_family_rank_bias_light_no_pipeline(monkeypatch):
    monkeypatch.setenv("FAMILY_LIGHT_INDUSTRY", "true")
    monkeypatch.setenv("USE_CATEGORY_DECISION", "true")
    from analytics.industries import pipeline as pipe_mod

    calls = {"n": 0}
    orig = pipe_mod.run_industry_pipeline

    def _spy(*a, **k):
        calls["n"] += 1
        return orig(*a, **k)

    monkeypatch.setattr(pipe_mod, "run_industry_pipeline", _spy)
    bias = pipe_mod.family_rank_bias("AAPL", row={"ticker": "AAPL"}, macro_bundle={"macro_score": 0.1})
    assert isinstance(bias, float)
    assert calls["n"] == 0


def test_factor_snapshot_cached():
    from analytics.industries import engine as eng

    eng._SNAP_CACHE = None
    a = eng.get_factor_snapshot({"macro_score": 0.42})
    b = eng.get_factor_snapshot()
    assert a["macro_score"] == pytest.approx(0.42)
    assert b["macro_score"] == pytest.approx(0.42)
