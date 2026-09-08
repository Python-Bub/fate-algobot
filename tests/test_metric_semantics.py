"""Sentiment intensity must not be treated as trade probability."""

from __future__ import annotations

from intel.metric_semantics import (
    headline_contradicts_intensity,
    reconcile_sentiment_with_headline,
    sentiment_rank_impulse,
)


def test_iwm_mixed_headline_dampens_false_positive():
    hl = "Exchange-Traded Funds Lower, Equity Futures Mixed Pre-Bell"
    adjusted, warn = reconcile_sentiment_with_headline(hl, 0.237)
    assert adjusted < 0.2
    assert warn in ("headline_neutral_dampen", "headline_factor_mismatch", "headline_bearish_cap", None) or adjusted < 0.237


def test_sentiment_impulse_is_tiny_not_probability():
    assert sentiment_rank_impulse(0.237) < 0.02
    assert sentiment_rank_impulse(-0.8) >= -0.03


def test_headline_contradicts_positive_on_bearish():
    hl = "Stock plunges on earnings miss"
    assert headline_contradicts_intensity(hl, 0.3)
