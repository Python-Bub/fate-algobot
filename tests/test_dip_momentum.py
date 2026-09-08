"""Tests for buy-the-dip momentum guard."""

from __future__ import annotations

import os

import pandas as pd

from signals.dip_momentum import (
    apply_dip_momentum_filter,
    assess_dip_momentum,
    assess_rally_momentum,
    blocks_bottom_fisher_trade,
    family_momentum_ok,
    rally_score_bonus,
)


def _closes_from_rets(rets: list[float], start: float = 100.0) -> pd.Series:
    prices = [start]
    for r in rets:
        prices.append(prices[-1] * (1.0 + r))
    return pd.Series(prices)


def test_falling_knife_blocks_dip():
    # Three down days in a row + fresh 1d drop
    rets = [0.01] * 30 + [-0.03, -0.04, -0.035]
    closes = _closes_from_rets(rets)
    ctx = assess_dip_momentum(closes)
    assert ctx.falling_knife
    filtered, _ = apply_dip_momentum_filter(closes, 0.9)
    assert filtered < 0.2


def test_stabilized_longer_term_allows_partial_dip():
    # Multi-week drift down then flat / slight bounce
    rets = [-0.008] * 25 + [0.002, 0.003, 0.004, -0.001, 0.005]
    closes = _closes_from_rets(rets)
    ctx = assess_dip_momentum(closes, ret_20d=-0.10, drawdown_52w=-0.15)
    assert ctx.longer_term_dip
    assert not ctx.falling_knife
    filtered, _ = apply_dip_momentum_filter(closes, 0.8, ret_20d=-0.10, drawdown_52w=-0.15)
    assert filtered > 0.3


def test_bottom_fisher_blocks_fresh_drop():
    blocked, reason = blocks_bottom_fisher_trade(
        ret_1d=-0.05,
        ret_5d=-0.12,
        ret_20d=-0.18,
        recovery_score=0.5,
        reversal_bar=0.1,
    )
    assert blocked
    assert "fresh drop" in reason


def test_rally_continuation_bonus():
    rets = [0.01] * 25 + [0.015, 0.012, 0.008, 0.006, 0.005]
    closes = _closes_from_rets(rets)
    ctx = assess_rally_momentum(closes)
    assert ctx.rally_continuation or ctx.rally_bonus > 0.3
    bonus = rally_score_bonus(ctx, hold_days=1)
    assert bonus > 0.25


def test_family_momentum_allows_55_with_mild_pullback():
    row = {"momentum_5d": -0.04, "rally_signal": 0.85, "momentum_ret_1d": -0.02}
    ok, _ = family_momentum_ok(row, 1)
    assert ok


def test_family_momentum_blocks_severe_knife_when_enabled():
    os.environ["FAMILY_MOMENTUM_GATE"] = "true"
    try:
        row = {"momentum_5d": -0.10, "momentum_ret_1d": -0.03}
        ok, reason = family_momentum_ok(row, 1)
        assert not ok
        assert reason
    finally:
        os.environ.pop("FAMILY_MOMENTUM_GATE", None)
