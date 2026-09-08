"""Per-timeframe conviction ranking — horizons do not have to agree."""

from analytics.horizon_picks import (
    directional_conviction,
    horizon_independent,
    pick_top_conviction,
    sleeve_native_probability,
)


def test_down_call_outranks_weak_up():
    rows = [
        {"ticker": "WEAK", "p_up": 0.61},
        {"ticker": "FALL", "p_up": 0.18},
        {"ticker": "MEH", "p_up": 0.55},
    ]
    top = pick_top_conviction(rows, k=2, allow_short=True, min_p_long=0.55, min_p_short=0.55)
    assert [r["ticker"] for r in top] == ["FALL", "WEAK"]
    assert top[0]["horizon_side"] == "short"
    assert top[1]["horizon_side"] == "long"
    assert top[0]["conviction"] > top[1]["conviction"]


def test_long_only_skips_high_conviction_down():
    rows = [
        {"ticker": "FALL", "p_up": 0.12},
        {"ticker": "UP", "p_up": 0.70},
    ]
    top = pick_top_conviction(rows, k=2, allow_short=False, min_p_long=0.55)
    assert [r["ticker"] for r in top] == ["UP"]


def test_sleeve_native_p_does_not_average_other_heads():
    p = sleeve_native_probability(
        1, p_daily=0.72, p_short=0.31, p_long=0.40, p_xlong=0.80, fused=0.50
    )
    assert abs(float(p) - 0.72) < 1e-9
    p5 = sleeve_native_probability(
        5, p_daily=0.72, p_short=0.31, p_long=0.40, p_xlong=0.80, fused=0.50
    )
    assert abs(float(p5) - 0.31) < 1e-9


def test_conviction_symmetric():
    assert abs(directional_conviction(0.80) - directional_conviction(0.20)) < 1e-9


def test_independent_default_is_on():
    assert horizon_independent() is True


def test_exec_conf_disagreement_ok_when_independent(monkeypatch):
    monkeypatch.setenv("HORIZON_INDEPENDENT", "true")
    monkeypatch.setenv("MIN_EXECUTION_CONFIDENCE", "0.62")
    from analytics.execution_confidence import execution_confidence, min_execution_confidence

    c, d = execution_confidence(0.78, 0.80, 0.22)
    assert d["horizon_independent"] is True
    assert c >= min_execution_confidence()


def test_short_horizon_not_blocked_when_independent(monkeypatch):
    monkeypatch.setenv("HORIZON_INDEPENDENT", "true")
    from analytics.family_horizons import short_horizon_blocked

    row = {
        "p_daily_model_raw": 0.72,
        "p_short_model_raw": 0.53,
        "p_xlong_model_raw": 0.86,
        "ur_detected": True,
        "ur_rationale": "undercut_and_rally",
        "dip_signal": 0.28,
    }
    assert short_horizon_blocked(row, hold_days=1) is False
