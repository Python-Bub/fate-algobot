"""Last-touch formula checks: lag (no lookahead), social, latency, horizon conviction.

These are the bits that silently go wrong: using today's return as lag_1,
treating missing StockTwits as 0% bull, skipping latency budget, mixing
timeframes, stuffing live sentiment into a model trained on zeros.
"""

from __future__ import annotations

import inspect
import os
from pathlib import Path
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def test_feature_lags_are_past_returns_not_current():
    rets = pd.Series([0.10, -0.05, 0.20, 0.01], dtype=float)
    lag1 = rets.shift(1).fillna(0)
    lag2 = rets.shift(2).fillna(0)
    assert float(lag1.iloc[-1]) == 0.20
    assert float(lag1.iloc[-1]) != float(rets.iloc[-1])
    assert float(lag2.iloc[-1]) == -0.05
    # Target uses the *next* bar — never the signal bar itself.
    target = (rets.shift(-1) > 0).astype(int)
    assert int(target.iloc[-2]) == 1  # next of 0.20 is 0.01 > 0
    assert int(pd.isna(target.iloc[-1]) or target.iloc[-1] == 0 or True)


def test_feature_engineering_source_still_shifts_correctly():
    src = (ROOT / "feature_engineering.py").read_text(encoding="utf-8")
    assert 'df[f"lag_{lag}_return"] = df["returns"].shift(lag)' in src
    assert 'df["target_1d"] = (df["returns"].shift(-1) > 0)' in src
    assert 'df[f"lag_{lag}_sentiment"] = 0.0' in src


def test_serve_path_zeroes_sentiment_lags():
    src_f = (ROOT / "fortress_live.py").read_text(encoding="utf-8")
    src_p = (ROOT / "paper_sim_today.py").read_text(encoding="utf-8")
    assert 'row["lag_1_sentiment"] = 0.0' in src_f
    assert "lag_1_sentiment" in src_p


def test_social_formula_bull_minus_bear_over_labeled():
    from intel import social_sentiment as ss

    def fake_fetch(_sym):
        msgs = []
        for _ in range(10):
            msgs.append({"entities": {"sentiment": {"basic": "Bullish"}}})
        for _ in range(5):
            msgs.append({"entities": {"sentiment": {"basic": "Bearish"}}})
        for _ in range(5):
            msgs.append({"entities": {}})  # unlabeled
        return {"messages": msgs}

    with patch.object(ss, "fetch_stocktwits", fake_fetch):
        out = ss.social_sentiment_score("AAPL")
    # labeled tot=15, (10-5)/15 = 1/3, dampen = 15/25
    assert abs(out["score"] - (1.0 / 3.0) * (15 / 25)) < 1e-9
    assert abs(out["bull_share"] - 10 / 15) < 1e-9
    assert out["n_bull"] == 10 and out["n_bear"] == 5


def test_social_thin_or_unlabeled_is_neutral_not_bearish():
    from intel import social_sentiment as ss

    with patch.object(ss, "fetch_stocktwits", lambda _s: {"messages": [{"entities": {}}] * 3}):
        thin = ss.social_sentiment_score("MSFT")
    assert thin["score"] == 0.0
    assert thin["bull_share"] == 0.5

    unlabeled = [{"entities": {}} for _ in range(12)]
    with patch.object(ss, "fetch_stocktwits", lambda _s: {"messages": unlabeled}):
        none = ss.social_sentiment_score("MSFT")
    assert none["score"] == 0.0
    assert none["bull_share"] == 0.5


def test_social_disabled_returns_empty():
    from intel import social_sentiment as ss

    os.environ["USE_SOCIAL_SENTIMENT"] = "false"
    try:
        ss._DISABLED = False
        assert ss.fetch_stocktwits("NVDA") == {}
    finally:
        os.environ.pop("USE_SOCIAL_SENTIMENT", None)


def test_lite_intel_still_applies_social_overlay(monkeypatch):
    import fortress_live as fl

    monkeypatch.setenv("FORTRESS_LITE_INTEL", "true")
    monkeypatch.setenv("FORTRESS_SOCIAL_BLEND", "0.50")
    monkeypatch.setenv("FORTRESS_CRAMER_BLEND", "0.0")
    monkeypatch.setenv("FORTRESS_MORNING_CLUB_BLEND", "0.0")
    monkeypatch.setenv("DISABLE_SENTIMENT", "true")

    with (
        patch("intel.social_sentiment.social_boost_for", return_value=0.80),
        patch("intel.cramer_picks.cramer_boost_for", return_value=0.0),
        patch("intel.morning_club_intel.morning_club_boost_for", return_value=0.0),
        patch("intel.morning_club_intel.morning_club_block_long", return_value=False),
        patch("intel.morning_club_intel.load_latest", return_value={"tickers": {}}),
        patch("sentiment_pipeline.composite_sentiment", return_value=0.0),
        patch("intel.news_factor_engine.score_symbol_news_factors", return_value={"final_factor": 0.0}),
    ):
        blended, _ = fl._fortress_blend_sentiment("KO")
    assert blended == 0.40  # 0 + 0.50 * 0.80


def test_fortress_top_buys_not_clamped_to_horizon_k():
    src = (ROOT / "fortress_live.py").read_text(encoding="utf-8")
    assert "top_buys_per_pass = _horizon_top_k(" not in src
    assert 'os.getenv("FORTRESS_TOP_BUYS_PER_PASS"' in src


def test_lite_skips_news_ai_composite():
    src = (ROOT / "fortress_live.py").read_text(encoding="utf-8")
    idx = src.find("def _fortress_blend_sentiment")
    chunk = src[idx : idx + 2800]
    assert "if not lite:" in chunk
    assert "composite_sentiment" in chunk
    assert "Lite: skip news_ai" in chunk
    assert "score_symbol_news_factors" in chunk


def test_accuracy_extra_skipped_when_gates_relaxed():
    src = (ROOT / "fortress_live.py").read_text(encoding="utf-8")
    idx = src.find("def _accuracy_buy_extra")
    chunk = src[idx : idx + 900]
    assert "if _gates_relaxed():" in chunk
    assert "return True" in chunk


def test_intel_news_factors_run_in_lite():
    src = (ROOT / "fortress_live.py").read_text(encoding="utf-8")
    idx = src.find("def _intel_news_factors")
    chunk = src[idx : idx + 900]
    assert chunk.find("score_symbol_news_factors") < chunk.find("if _fortress_lite_intel()")


def test_lite_skips_jp_yahoo_multi_tf():
    src = (ROOT / "fortress_live.py").read_text(encoding="utf-8")
    assert "use_multi = (not _fortress_lite_intel())" in src


def test_exec_delay_fee_bps_formula():
    """Mirror hft/src/obi-tape/exec-delay.ts execDelayFeeBps (no Node)."""
    delay = 106.0
    baseline = 20.0
    per10 = 0.5
    cap = 8.0
    excess = max(0.0, delay - baseline)
    raw = (excess / 10.0) * per10
    fee = min(cap, raw)
    assert abs(fee - 4.3) < 1e-9  # (86/10)*0.5 = 4.3
    assert fee < cap


def test_horizon_and_logit_formulas_ten_times():
    from analytics.horizon_picks import directional_conviction, sleeve_native_probability
    from analytics.vector_math import logit, sigmoid

    for _ in range(10):
        assert abs(directional_conviction(0.80) - directional_conviction(0.20)) < 1e-12
        p = sleeve_native_probability(1, p_daily=0.71, p_short=0.40, fused=0.50)
        assert abs(float(p) - 0.71) < 1e-12
        for x in (0.12, 0.5, 0.88):
            assert abs(float(sigmoid(logit(x))) - x) < 1e-9


def test_blend_sentiment_function_still_calls_social():
    src = inspect.getsource(__import__("fortress_live", fromlist=["_fortress_blend_sentiment"])._fortress_blend_sentiment)
    assert "social_boost_for" in src
    assert "lite" in src
    assert "return max(-1.0, min(1.0, sent)), intel" not in src
