"""Multi-TF JP candle intel + lightweight RL weights."""

from __future__ import annotations

import pandas as pd

from analytics.jp_candle_intel import _three_white_soldiers, assess_advanced
from analytics.jp_candle_rl import adjust_boost, pattern_weight, record_outcome, record_signal


def test_three_white_soldiers_detect():
    df = pd.DataFrame(
        {
            "Open": [10, 11, 12],
            "High": [11, 12, 13],
            "Low": [9.8, 10.8, 11.8],
            "Close": [10.8, 11.8, 12.8],
        }
    )
    assert _three_white_soldiers(df) is True


def test_rl_weight_neutral_without_data():
    w = pattern_weight("HAMMER")
    assert 0.5 <= w <= 1.3


def test_rl_learns_from_outcome(tmp_path, monkeypatch):
    state = tmp_path / "jp_candle_rl_state.json"
    monkeypatch.setenv("JP_CANDLE_RL_ENABLED", "true")
    monkeypatch.setattr("analytics.jp_candle_rl.STATE_PATH", state)
    record_signal("TEST", pattern="HAMMER", bias=1, composite_bias=1, p_adj=0.6)
    record_outcome("TEST", 0.02)
    boost, w = adjust_boost(0.05, "HAMMER")
    assert boost > 0
    assert w >= 0.55


def test_assess_advanced_empty_daily(monkeypatch):
    monkeypatch.setenv("FORTRESS_JP_MULTI_TF", "false")
    df = pd.DataFrame(
        {
            "Open": [100, 99, 98, 97, 96, 95.5],
            "High": [101, 100, 99, 98, 97, 96],
            "Low": [99, 98, 97, 96, 95, 90],
            "Close": [99.5, 98.5, 97.5, 96.5, 95.5, 95.8],
        }
    )
    intel = assess_advanced("TEST", df, use_daily=False)
    assert intel.pattern in intel.intraday.get("effective_pattern", intel.pattern)


def test_doji_does_not_veto_model_buy(monkeypatch):
    from analytics.jp_candle_intel import AdvancedCandleIntel, apply_to_p_adj

    monkeypatch.setenv("FORTRESS_JP_CANDLE_REQUIRE_BULL", "true")
    intel = AdvancedCandleIntel(
        intraday={"bias": 0, "pattern": "DOJI"},
        daily={"pattern": "HANGING_MAN", "bias": -1},
        composite_bias=0,
        composite_score=-0.12,
        pattern="DOJI",
        trend=0,
        daily_confirms=True,
        rl_weight=1.0,
    )
    p, want, msg = apply_to_p_adj(0.82, intel, want_buy=True)
    assert want is True
    assert "bearish composite" not in msg
    assert p >= 0.80


def test_bearish_engulf_still_hard_skips(monkeypatch):
    from analytics.jp_candle_intel import AdvancedCandleIntel, apply_to_p_adj

    monkeypatch.setenv("FORTRESS_RELAX_GATES", "false")
    intel = AdvancedCandleIntel(
        intraday={"bias": -1, "pattern": "BEARISH_ENGULF"},
        daily={"pattern": "BEARISH_ENGULF", "bias": -1},
        composite_bias=-1,
        composite_score=-1.0,
        pattern="BEARISH_ENGULF",
        trend=-1,
        daily_confirms=True,
        rl_weight=1.0,
    )
    _p, want, msg = apply_to_p_adj(0.80, intel, want_buy=True)
    assert want is False
    assert "bearish composite" in msg
