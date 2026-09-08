"""Feature IC weights: dead columns stay, but get floor weight."""

from __future__ import annotations

import numpy as np
import pandas as pd

from analytics.feature_decision_weights import apply_column_weights, column_ic_weights, row_weighted_score
from analytics.sleeve_weights import FORTRESS_PCT, WEEKLY_PCT, LONGTERM_PCT, DAY_TRADE_PCT, pct_sum


def test_dead_sentiment_gets_floor_not_deleted():
    n = 80
    rng = np.random.default_rng(0)
    signal = rng.normal(size=n)
    y = (signal + rng.normal(scale=0.3, size=n) > 0).astype(float)
    X = pd.DataFrame(
        {
            "mom": signal,
            "sentiment": np.zeros(n),
            "noise": rng.normal(scale=3.0, size=n),
        }
    )
    w = column_ic_weights(X, y, floor=0.05)
    assert set(w) == {"mom", "sentiment", "noise"}
    assert w["sentiment"] == 0.05
    assert w["mom"] > w["sentiment"]


def test_apply_weights_shrinks_dead_col():
    X = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [9.0, 9.0, 9.0]})
    out = apply_column_weights(X, {"a": 1.0, "b": 0.05})
    assert abs(out["b"].iloc[0] - 0.45) < 1e-9


def test_row_weighted_score():
    s = row_weighted_score({"mom": 2.0, "dead": 99.0}, {"mom": 1.0, "dead": 0.05})
    assert abs(s) < 2.0


def test_derivatives_now_weighted_on_non_hft():
    assert FORTRESS_PCT["derivatives_context"] > 0
    assert WEEKLY_PCT["derivatives_context"] > 0
    assert LONGTERM_PCT["derivatives_context"] > 0
    assert DAY_TRADE_PCT["derivatives_context"] > 0
    for s in ("fortress", "weekly", "longterm", "day_trade", "hft"):
        assert abs(pct_sum(s) - 100.0) < 0.01
