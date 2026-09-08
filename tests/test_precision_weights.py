"""Precision-weighted fusion, agreement gates, and normalized sleeve math."""

from __future__ import annotations

import os

import numpy as np

from analytics.vector_math import (
    heads_are_independent,
    l1_weighted_sum,
    logit_blend,
    normalize_weights,
    precision_fuse,
    precision_weights,
    signed_agreement,
)


def test_normalize_weights_sum_to_one():
    w = normalize_weights([0.85, 0.38, 0.22, -0.05])
    assert abs(float(w.sum()) - 1.0) < 1e-9
    assert float(w.min()) >= 0.0


def test_precision_weights_prefer_low_variance():
    w = precision_weights(variances=[0.04, 0.25], skills=[1.0, 1.0])
    assert float(w[0]) > float(w[1])
    assert abs(float(w.sum()) - 1.0) < 1e-9


def test_precision_fuse_agreeing_heads_stay_high():
    p = precision_fuse([0.80, 0.78, 0.82], variances=[0.04, 0.04, 0.09])
    assert p > 0.75


def test_precision_fuse_disagreement_is_less_extreme_than_best_head():
    p = precision_fuse([0.90, 0.20], variances=[0.04, 0.04])
    assert 0.45 < p < 0.75


def test_logit_blend_not_linear():
    lin = 0.7 * 0.95 + 0.3 * 0.55
    lea = logit_blend([0.95, 0.55], [0.7, 0.3])
    assert abs(lea - lin) > 1e-4


def test_l1_weighted_sum_is_convex_combo():
    s = l1_weighted_sum([1.0, -1.0], [0.75, 0.25])
    assert abs(s - 0.5) < 1e-9


def test_signed_agreement_requires_both_heads():
    assert signed_agreement(0.70, 0.72, 0.71) > 0.3
    assert signed_agreement(0.70, 0.30, 0.71) == 0.0


def test_copies_of_fused_p_are_not_independent():
    assert heads_are_independent(0.75, 0.75, 0.75) is False
    assert heads_are_independent(0.62, 0.71, 0.68) is True


def test_exec_conf_certainty_only_can_clear_gate(monkeypatch):
    monkeypatch.setenv("MIN_EXECUTION_CONFIDENCE", "0.62")
    monkeypatch.setenv("EXEC_AGREE_BLEND", "0.60")
    from analytics.execution_confidence import execution_confidence, min_execution_confidence

    c, d = execution_confidence(0.78)
    assert d["independent_heads"] is False
    assert c >= min_execution_confidence()


def test_exec_conf_fake_copies_do_not_count_as_agree(monkeypatch):
    monkeypatch.setenv("MIN_EXECUTION_CONFIDENCE", "0.62")
    from analytics.execution_confidence import execution_confidence

    c_real, d_real = execution_confidence(0.78, 0.78, 0.78)
    c_only, _ = execution_confidence(0.78)
    assert d_real["independent_heads"] is False
    assert abs(c_real - c_only) < 1e-6


def test_exec_conf_disagreement_fails_dual(monkeypatch):
    monkeypatch.setenv("HORIZON_INDEPENDENT", "false")
    monkeypatch.setenv("MIN_EXECUTION_CONFIDENCE", "0.62")
    monkeypatch.setenv("EXEC_MIN_AGREE", "0.10")
    monkeypatch.setenv("EXEC_AGREE_BLEND", "0.60")
    from analytics.execution_confidence import execution_confidence, passes_confidence_gates

    c, d = execution_confidence(0.70, 0.72, 0.28)
    assert d["independent_heads"] is True
    assert (d["agree_score"] or 0) < 0.10
    assert c < 0.62
    assert passes_confidence_gates(0.70, c, 0.55, 0.62) is False


def test_hf_weights_sum_to_one_after_normalize(monkeypatch):
    monkeypatch.setenv("HF_NORMALIZE_WEIGHTS", "true")
    monkeypatch.setenv("HF_LOCK_LIQUIDITY_MM_ZERO", "true")
    monkeypatch.setenv("HF_LOCK_ETF_DISLOC_ZERO", "true")
    monkeypatch.setenv("FATE_SLEEVE", "fortress")
    from analytics.hedge_fund_stack import hedge_fund_rank_boost

    idx = __import__("pandas").date_range("2024-01-01", periods=40, freq="D")
    closes = __import__("pandas").Series(np.linspace(50, 55, 40), index=idx)
    row = {"rsi": 48, "rs_spy": 1.05, "volume_ratio": 1.8, "volatility": 0.02}
    hf = hedge_fund_rank_boost("AAPL", row=row, closes=closes, bench_closes=closes)
    wsum = float(hf.meta.get("weights_sum") or 0)
    assert abs(wsum - 1.0) < 1e-6


def test_forecast_combination_chapter_loaded():
    from investing.knowledge import get_chapter

    ch = get_chapter("forecast_combination")
    assert ch is not None
    assert "Bates" in ch.philosophy
    assert any("logit" in f.latex.lower() or "logit" in f.name.lower() for f in ch.formulas)
