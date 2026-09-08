"""Tests for LogitEvidence Algebra + vector motif/rolling helpers."""

from __future__ import annotations

import numpy as np

from analytics.vector_math import (
    clip_prob,
    fuse_probs,
    isolation_feature_matrix,
    logit,
    logit_blend,
    logit_pair_blend,
    rolling_mean,
    sigmoid,
    sliding_cosine_motifs,
)


def test_logit_sigmoid_roundtrip():
    for p in (0.01, 0.2, 0.5, 0.8, 0.99):
        assert abs(float(sigmoid(logit(p))) - p) < 1e-6


def test_logit_blend_more_extreme_than_linear_when_confident():
    # Two strong agreeing signals: logit mean stays high; linear also high
    p_lin = 0.7 * 0.95 + 0.3 * 0.9
    p_lea = logit_blend([0.95, 0.9], [0.7, 0.3])
    assert p_lea > 0.9
    assert abs(p_lea - p_lin) > 1e-4  # LEA ≠ arithmetic mix


def test_logit_pair_blend_weight_zero():
    assert abs(logit_pair_blend(0.62, 0.99, 0.0) - 0.62) < 1e-6


def test_fuse_probs_modes():
    probs = [0.8, 0.7, 0.6]
    w = [0.5, 0.3, 0.2]
    a = fuse_probs(probs, w, mode="logit")
    b = fuse_probs(probs, w, mode="linear")
    c = fuse_probs(probs, w, mode="lse")
    assert 0.5 < a < 1.0
    assert 0.5 < b < 1.0
    assert 0.5 < c < 1.0


def test_rolling_mean_matches_naive():
    x = np.random.default_rng(0).normal(size=50)
    m = rolling_mean(x, 5)
    for i in range(4, 50):
        assert abs(m[i] - x[i - 4 : i + 1].mean()) < 1e-9


def test_isolation_feature_matrix_shape():
    r = np.random.default_rng(1).normal(scale=0.01, size=100)
    v = np.abs(np.random.default_rng(2).normal(size=100)) + 1.0
    X = isolation_feature_matrix(r, v, win=20)
    assert X.ndim == 2 and X.shape[1] == 6
    assert X.shape[0] == 100 - 20


def test_sliding_cosine_self_match():
    # Plant a repeated motif
    rng = np.random.default_rng(3)
    motif = rng.normal(size=8)
    hist = np.concatenate([rng.normal(size=40), motif, rng.normal(size=8), motif * 0.01])
    # end with same motif so query matches earlier plant
    rets = np.concatenate([hist[:-8], motif])
    sim, pw, best = sliding_cosine_motifs(rets, w=8, min_sim=0.5, top_k=3)
    assert sim > 0.85


def test_clip_prob_bounds():
    assert float(clip_prob(0.0)) > 0
    assert float(clip_prob(1.0)) < 1
