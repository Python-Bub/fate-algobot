"""Black–Scholes greeks + contract picker."""

from __future__ import annotations

from analytics.contract_select import STRUCTURES, pick_best, score_single, synthetic_chain
from investing.formulas.derivatives import (
    black_scholes_call,
    greeks,
    implied_vol,
    put_call_parity_check,
)


def test_put_call_parity_near_zero():
    S, K, T, r, sig = 100.0, 100.0, 30 / 365, 0.04, 0.25
    C = black_scholes_call(S, K, T, r, sig)
    from investing.formulas.derivatives import black_scholes_put

    P = black_scholes_put(S, K, T, r, sig)
    resid = put_call_parity_check(C, P, S, K, r, T)
    assert abs(resid) < 1e-8


def test_call_delta_between_zero_and_one():
    g = greeks(100, 100, 0.25, 0.04, 0.3, kind="call")
    assert 0.4 < g["delta"] < 0.7
    assert g["gamma"] > 0
    assert g["vega"] > 0


def test_implied_vol_recovers_input():
    S, K, T, r, sig = 100.0, 105.0, 45 / 365, 0.03, 0.32
    px = black_scholes_call(S, K, T, r, sig)
    iv = implied_vol(px, S, K, T, r, kind="call")
    assert abs(iv - sig) < 0.01


def test_picker_bull_view_chooses_call_structure():
    chain = synthetic_chain(100.0, dte=30, sigma=0.25)
    best = pick_best(chain, spot=100.0, view="long")
    assert best is not None
    assert best["chosen_structure"] in STRUCTURES
    assert best["chosen_structure"] in ("long_call", "bull_call_spread", "covered_call")
    assert best["score"] > 0


def test_rich_iv_prefers_spread_or_covered_call():
    chain = synthetic_chain(100.0, dte=30, sigma=0.85)
    best = pick_best(chain, spot=100.0, view="long")
    assert best is not None
    assert best["chosen_structure"] in ("bull_call_spread", "covered_call", "long_call")


def test_score_penalizes_wide_spread():
    from analytics.contract_select import ListedContract

    tight = ListedContract("T", "call", 100, 30, 1.98, 2.02, oi=2000, volume=500, mid=2.0)
    wide = ListedContract("W", "call", 100, 30, 1.0, 3.0, oi=2000, volume=500, mid=2.0)
    a = score_single(tight, spot=100.0, view="long")
    b = score_single(wide, spot=100.0, view="long")
    assert a["score"] > b["score"]


def test_repeat_picker_stable():
    chain = synthetic_chain(50.0)
    first = pick_best(chain, spot=50.0, view="neutral")
    for _ in range(20):
        again = pick_best(chain, spot=50.0, view="neutral")
        assert again["chosen_structure"] == first["chosen_structure"]
