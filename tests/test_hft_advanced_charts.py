"""Unit tests for the 4-chart HFT stack (no lookahead, no network)."""

from __future__ import annotations

import numpy as np

from analytics.hft_advanced_charts import (
    PointAndFigure,
    candle_vote,
    fuse_votes,
    hloc_vote,
    line_vote,
    vote_series,
)
from analytics.sleeve_weights import HFT_PCT, pct_sum


def _marubozu_up(n: int = 30) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    c = np.linspace(100.0, 106.0, n)
    o = c - 0.4
    h = c + 0.02
    l = o - 0.02
    return o, h, l, c


def test_green_marubozu_is_bullish_candle():
    o, h, l, c = _marubozu_up()
    v = candle_vote(o, h, l, c, len(c) - 1, jp_bias=0)
    assert v > 0.2


def test_line_vote_fires_on_range_break_not_every_up_bar():
    c = np.zeros(40)
    for i in range(30):
        c[i] = 100.0 + np.sin(i) * 0.4
    c[30] = 101.3
    c[31:] = 101.3 + np.arange(9) * 0.01
    assert line_vote(c, 30) > 0.2
    # Continuation after the first break is not a new event.
    assert abs(line_vote(c, 35)) < 0.2


def test_hloc_key_reversal_bullish():
    n = 12
    o = np.array([10.0] * n)
    h = np.array([10.2] * n)
    l = np.array([9.8] * n)
    c = np.array([9.9] * n)
    o[-2], h[-2], l[-2], c[-2] = 10.0, 10.1, 9.5, 9.55
    o[-1], h[-1], l[-1], c[-1] = 9.6, 10.4, 9.55, 10.25
    v = hloc_vote(o, h, l, c, n - 1)
    assert v > 0.3


def test_pnf_tracks_x_column_on_rise():
    p = PointAndFigure(box_pct=0.01, reversal=3)
    px = 100.0
    votes = []
    for _ in range(20):
        px *= 1.015
        votes.append(p.on_close(px))
    assert p.dir == 1
    assert max(votes) > 0


def test_hidden_requires_cross_family():
    lone = fuse_votes(0.9, 0.0, 0.0, 0.0)
    assert lone.n_agree < 2
    assert lone.cross_family is False
    assert lone.bias == 0
    # candle+hloc only = same family, no close-path → not a live signal
    bar_only = fuse_votes(0.5, 0.0, 0.4, 0.0)
    assert bar_only.cross_family is False
    agree = fuse_votes(0.5, 0.5, 0.4, 0.3)
    assert agree.n_agree >= 2
    assert agree.cross_family is True
    assert abs(agree.score) > abs(lone.score)


def test_vote_series_no_lookahead_length():
    o, h, l, c = _marubozu_up(80)
    vs = vote_series(o, h, l, c)
    assert len(vs) == 80
    assert vs[0].n_agree == 0 or vs[0].bias == 0


def test_walk_forward_synthetic_has_signals():
    from tools.hft_chart_historical import planted_synthetic, walk_forward

    o, h, l, c = planted_synthetic(4000, seed=3)
    st = walk_forward(o, h, l, c, cost_bps=6.0, min_agree=2, min_abs=0.18, horizons=(1, 3, 5), cooldown=3)
    assert st["bars"] == 4000
    assert st["signals"] > 10
    h3 = st["horizons"]["h3"]
    assert h3["n"] > 0


def test_hft_sleeve_still_100_with_chart_patterns():
    assert HFT_PCT["chart_patterns"] == 3.0
    assert HFT_PCT["obi"] >= 32.0
    assert HFT_PCT["tape"] >= 22.0
    assert pct_sum("hft") == 100.0
