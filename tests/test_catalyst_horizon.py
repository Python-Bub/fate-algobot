"""Catalyst ↔ horizon alignment + max-equity sizing."""

from __future__ import annotations

import pytest

from analytics.catalyst_horizon import (
    catalyst_horizon_fit,
    earnings_rank_boost,
    earnings_size_mult_aligned,
    enrich_earnings_plan,
    max_equity_size_mult,
)
from analytics.sleeve_weights import assert_tables_valid, FORTRESS_PCT, pct_sum


def test_fortress_earnings_stick_weight_raised():
    assert_tables_valid()
    assert pct_sum("fortress") == pytest.approx(100.0, abs=0.01)
    assert FORTRESS_PCT["earnings_stick"] >= 5.0


def test_dte1_routes_to_fortress_not_longterm():
    assert catalyst_horizon_fit(1, "fortress") == pytest.approx(1.0)
    assert catalyst_horizon_fit(1, "longterm") == pytest.approx(0.05)
    assert catalyst_horizon_fit(1, "weekly") < 0.5


def test_earnings_tomorrow_force_on_fortress_not_lt():
    b_f, m_f = earnings_rank_boost(days_to=1, p_adj=0.62, sleeve="fortress", stick=True)
    b_l, m_l = earnings_rank_boost(days_to=1, p_adj=0.62, sleeve="longterm", stick=True)
    assert m_f["force_ok"] is True
    assert m_l["force_ok"] is False
    assert b_f > 0.05
    assert b_l < 0.02
    assert b_f > b_l * 10


def test_size_full_on_match_dampen_on_mismatch():
    match = earnings_size_mult_aligned(
        days_to=1, in_earnings_window=True, sleeve="fortress", encourage=True, playbook_dampen=0.55
    )
    mismatch = earnings_size_mult_aligned(
        days_to=1, in_earnings_window=True, sleeve="longterm", encourage=True, playbook_dampen=0.55
    )
    assert match >= 1.0
    assert mismatch < 0.4


def test_max_equity_shrinks_when_risky():
    strong = max_equity_size_mult(
        p_adj=0.68, exec_conf=0.75, risk_pressure=0.05, force_priority=True, catalyst_fit=1.0
    )
    risky = max_equity_size_mult(
        p_adj=0.55, exec_conf=0.5, risk_pressure=0.85, force_priority=False, catalyst_fit=0.2
    )
    assert strong > 1.0
    assert risky < 0.6


def test_enrich_plan_attaches_fit():
    plan = {
        "days_to": 1,
        "encourage_pre_momentum": True,
        "stick_to_prediction": True,
        "near_event": True,
    }
    out = enrich_earnings_plan(plan, sleeve="fortress")
    assert out["catalyst_horizon_fit"] == pytest.approx(1.0)
    assert out["force_horizon_ok"] is True
    assert out["aligned_size_mult"] >= 1.0
