"""Family horizon model mapping + bounce-back timeframe fit."""

from analytics.family_horizons import horizon_timeframe_fit, resolve_model_probability


def test_isrg_longer_horizon_stronger_than_daily(monkeypatch):
    monkeypatch.setenv("HORIZON_INDEPENDENT", "false")
    row = {
        "ticker": "ISRG",
        "p_daily_model_raw": 0.54,
        "p_short_model_raw": 0.53,
        "p_long_model_raw": 0.61,
        "p_xlong_model_raw": 0.86,
        "top100": True,
        "fund_score": 0.6,
        "ur_score": 0.2,
        "ur_detected": True,
        "ur_rationale": "undercut_and_rally",
    }
    daily, _ = resolve_model_probability(row, "p_daily")
    xlong, _ = resolve_model_probability(row, "p_xlong")
    assert daily is not None and xlong is not None
    assert xlong > daily + 0.2
    assert horizon_timeframe_fit(row, hold_days=1) < 0
    assert horizon_timeframe_fit(row, hold_days=126) > 0.8
    from analytics.family_horizons import (
        horizon_effective_probability,
        is_bounce_back_candidate,
        short_horizon_blocked,
    )

    assert is_bounce_back_candidate(row)
    assert short_horizon_blocked(row, hold_days=1)
    assert short_horizon_blocked(row, hold_days=5)
    month_p, head = horizon_effective_probability(row, "p_long", hold_days=21)
    assert head == "model_bounce_blend"
    assert month_p is not None and month_p > daily + 0.05


def test_ultra_long_proxy():
    row = {
        "p_xlong_model_raw": 0.8,
        "fund_score": 0.7,
        "quality_score": 0.65,
        "top100": True,
        "ur_score": 0.3,
        "dip_signal": 0.2,
    }
    raw, head = resolve_model_probability(row, "p_ultra")
    assert head == "fundamental_proxy"
    assert raw is not None
    assert 0.5 <= raw <= 0.88
