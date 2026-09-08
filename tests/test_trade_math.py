"""Trade math + TPM plumbing (no network)."""

from __future__ import annotations

import math

import numpy as np

from analytics.trade_math import (
    audit_trade_gates,
    distress_score,
    expected_bps,
    falling_knife,
    fuse_logits,
    kelly_fraction,
    ou_half_life,
    should_enter,
    tpm_capacity,
    zscore,
)


def test_expected_bps_positive_when_edge_clears_cost():
    ev = expected_bps(0.62, tp_bps=12.0, cost_bps=3.0)
    assert ev > 0
    ok, meta = should_enter(0.62, tp_bps=12.0, cost_bps=3.0, min_ev_bps=0.4)
    assert ok
    assert meta["ev_bps"] == ev
    two_sided = expected_bps(0.62, tp_bps=12.0, stop_bps=12.0, cost_bps=3.0)
    assert two_sided < ev


def test_expected_bps_rejects_coin_flip_into_wide_spread():
    ok, _ = should_enter(0.51, tp_bps=4.0, cost_bps=8.0, min_ev_bps=0.4)
    assert not ok


def test_fuse_logits_weights():
    p = fuse_logits([(0.8, 0.6), (0.55, 0.4)])
    assert 0.6 < p < 0.85


def test_kelly_is_fractional_and_clipped():
    f = kelly_fraction(0.58, 1.2, fraction=0.25)
    assert 0.0 <= f <= 0.25


def test_falling_knife_and_distress():
    assert falling_knife(-0.03, -0.12, -0.08)
    knife = distress_score(
        ret_60d=-0.25,
        ret_20d=-0.18,
        ret_5d=-0.12,
        ret_1d=-0.04,
        drawdown_52w=-0.4,
        rsi=28,
        dollar_vol=5_000_000,
    )
    assert knife == 0.0
    rec = distress_score(
        ret_60d=-0.22,
        ret_20d=-0.08,
        ret_5d=0.03,
        ret_1d=0.01,
        drawdown_52w=-0.35,
        rsi=32,
        ou_hl=12.0,
        dollar_vol=8_000_000,
    )
    assert rec > 0.15


def test_ou_half_life_mean_reverting_series():
    rng = np.random.default_rng(0)
    xs = [0.0]
    for _ in range(200):
        xs.append(0.85 * xs[-1] + float(rng.normal(scale=0.01)))
    logp = [math.log(100.0 * math.exp(x)) for x in xs]
    hl = ou_half_life(logp)
    assert 1.0 < hl < 20.0


def test_zscore_extremes():
    z = zscore([1.0] * 19 + [3.0], window=20)
    assert z > 1.5


def test_tpm_capacity_hits_185():
    cap = tpm_capacity(n_names=50, cooldown_s=18.0, orders_per_roundtrip=2, cap_per_min=185)
    assert cap["orders_per_min"] > 185
    assert cap["hits_cap"] == 1.0
    thin = tpm_capacity(n_names=8, cooldown_s=90.0, orders_per_roundtrip=2, cap_per_min=185)
    assert thin["hits_cap"] == 0.0


def test_tpm_capacity_hits_200_ofi_ws():
    cap = tpm_capacity(n_names=15, cooldown_s=6.0, orders_per_roundtrip=2, cap_per_min=200)
    assert cap["orders_per_min"] == 300.0
    assert cap["hits_cap"] == 1.0
    thin = tpm_capacity(n_names=15, cooldown_s=90.0, orders_per_roundtrip=2, cap_per_min=200)
    assert thin["hits_cap"] == 0.0


def test_audit_trade_gates_order():
    bad = audit_trade_gates(
        dual_ok=True,
        p_up=0.6,
        ev_bps=2.0,
        min_ev_bps=0.4,
        spread_ok=True,
        already_long=True,
        slot_ok=True,
        tape_authentic=True,
    )
    assert bad["ok"] is False
    assert "already_long" in bad["reasons"]
    good = audit_trade_gates(
        dual_ok=True,
        p_up=0.6,
        ev_bps=2.0,
        min_ev_bps=0.4,
        spread_ok=True,
        already_long=False,
        slot_ok=True,
        tape_authentic=True,
    )
    assert good["ok"] is True


def test_repeated_tpm_math_is_stable():
    for _ in range(25):
        cap = tpm_capacity(n_names=50, cooldown_s=18.0, cap_per_min=185)
        assert cap["capped_per_min"] == 185.0
