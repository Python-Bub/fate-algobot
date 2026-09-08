"""Proven online combiners + tight pick bar. No network."""

from __future__ import annotations

import pytest

from analytics.proven_online import (
    CORE_EXPERTS,
    credit_outcome,
    expert_votes,
    hedge_fuse,
    proven_online_rank_boost,
    tight_pick,
)
from analytics.sleeve_weights import FORTRESS_PCT, HFT_PCT, assert_tables_valid, pct_sum


def test_core_yes_is_tight(tmp_path, monkeypatch):
    monkeypatch.setenv("USE_PROVEN_ONLINE", "true")
    monkeypatch.setenv("USE_TIGHT_PICKS", "true")
    monkeypatch.setenv("USE_GEN_LEARN", "false")
    monkeypatch.setenv("TIGHT_PICK_MIN_P", "0.64")
    monkeypatch.setenv("TIGHT_PICK_MIN_AGREE", "4")
    monkeypatch.setattr("analytics.proven_online.STATE_PATH", tmp_path / "st.json")
    # Weak name: p=0.55, no momentum.
    weak = tight_pick("ZZZ", p_up=0.55, exec_c=0.70, mom_5d=-0.02, rs_spy=0.95, hmm=0.1)
    assert weak["ok"] is False
    # Best-of-best: model + mom + exec + event (hmm abstain still 4).
    strong = tight_pick("NVDA", p_up=0.72, exec_c=0.70, mom_5d=0.04, rs_spy=1.02, hmm=0.0, use_live_events=False)
    assert strong["agree"] >= 4
    assert strong["ok"] is True
    assert strong["p_cal"] >= 0.58


def test_chase_rsi_veto(tmp_path, monkeypatch):
    monkeypatch.setenv("USE_PROVEN_ONLINE", "true")
    monkeypatch.setenv("USE_TIGHT_PICKS", "true")
    monkeypatch.setattr("analytics.proven_online.STATE_PATH", tmp_path / "st.json")
    row = {"rsi_overbought": 1.0, "bb_overbought": 1.0}
    out = tight_pick(
        "MEME",
        p_up=0.80,
        exec_c=0.70,
        mom_5d=0.08,
        rs_spy=1.1,
        hmm=0.2,
        row=row,
    )
    assert out["chase"] is True
    assert out["ok"] is False


def test_stick_force_bypasses_tight(tmp_path, monkeypatch):
    monkeypatch.setenv("USE_TIGHT_PICKS", "true")
    monkeypatch.setattr("analytics.proven_online.STATE_PATH", tmp_path / "st.json")
    out = tight_pick("SBUX", p_up=0.50, exec_c=0.40, mom_5d=-0.03, force_stick=True)
    assert out["ok"] is True
    assert out.get("forced") == "stick"


def test_hedge_and_online_credit(tmp_path, monkeypatch):
    monkeypatch.setenv("USE_PROVEN_ONLINE", "true")
    monkeypatch.setenv("USE_GEN_LEARN", "false")
    monkeypatch.setattr("analytics.proven_online.STATE_PATH", tmp_path / "st.json")
    votes = expert_votes(p_up=0.70, exec_c=0.70, mom_5d=0.03, rs_spy=1.01, hmm=0.1)
    p0, _ = hedge_fuse(votes)
    assert 0.5 < p0 < 0.99
    # Remember votes via evaluate path.
    tight_pick("AAPL", p_up=0.70, exec_c=0.70, mom_5d=0.03, rs_spy=1.01, hmm=0.1)
    before = hedge_fuse(votes)[0]
    credit_outcome("AAPL", 0.04, side="LONG")
    after_st_votes = expert_votes(p_up=0.70, exec_c=0.70, mom_5d=0.03, rs_spy=1.01, hmm=0.1)
    after = hedge_fuse(after_st_votes)
    # Win should not collapse the fused p.
    assert after[0] > 0.5
    b, meta = proven_online_rank_boost("AAPL", p_up=0.70, exec_c=0.70, mom_5d=0.03)
    assert b > 0
    assert "model" in CORE_EXPERTS
    # In-memory state must accumulate (not reload disk each credit).
    from analytics.proven_online import load_state

    st = load_state()
    assert int(st.get("n_updates") or 0) >= 1


def test_hft_skipped(monkeypatch):
    monkeypatch.setenv("USE_PROVEN_ONLINE", "true")
    b, meta = proven_online_rank_boost("NVDA", p_up=0.80, sleeve="hft")
    assert b == 0.0
    assert meta.get("skipped")


def test_sleeve_keeps_proven_and_100():
    assert_tables_valid()
    assert pct_sum("fortress") == pytest.approx(100.0, abs=0.01)
    assert FORTRESS_PCT.get("proven_online", 0.0) >= 2.0
    assert HFT_PCT.get("proven_online", 0.0) == 0.0


def test_peer_backfill_is_causal():
    from datetime import date, timedelta

    from analytics.event_learn import EventSample, backfill_peer_feats, empty_feats

    d0 = date(2024, 1, 10)
    wmt = EventSample("WMT", d0, empty_feats(), y_sign=-1.0, y_abs=0.09, is_event=True)
    cost = EventSample("COST", d0 + timedelta(days=2), empty_feats(), y_sign=-1.0, y_abs=0.02, is_event=True)
    n = backfill_peer_feats([wmt, cost])
    assert n >= 1
    assert cost.feats["peer_printed"] == 1.0
    assert cost.feats["peer_gap_signed"] < 0
    # WMT's own print is not a peer of itself on the same day.
    assert wmt.feats.get("peer_printed", 0.0) == 0.0
