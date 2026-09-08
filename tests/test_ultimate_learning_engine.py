"""Smoke tests for Ultimate Learning Engine + LEA hub."""

from __future__ import annotations

import os


def test_skill_weights_sum_to_one():
    os.environ["USE_ULE"] = "true"
    from analytics.ultimate_learning_engine import skill_weights, _DEFAULT_SKILL

    w = skill_weights({"skill": dict(_DEFAULT_SKILL)})
    assert abs(sum(w.values()) - 1.0) < 1e-6
    assert set(w) >= {"base", "hidden", "neural", "overlay", "cortex"}


def test_credit_outcome_bumps_skill(tmp_path, monkeypatch):
    monkeypatch.setenv("USE_ULE", "true")
    monkeypatch.setenv("ULE_LEARN_RATE", "0.2")
    import analytics.ultimate_learning_engine as ule

    monkeypatch.setattr(ule, "STATE_PATH", tmp_path / "ule_state.json")
    monkeypatch.setattr(ule, "HIST_PATH", tmp_path / "ule_history.jsonl")
    before = ule.skill_weights()["hidden"]
    out = ule.credit_outcome(success=True, active=["hidden", "base"], reward=0.05)
    assert out["applied"]
    after = ule.skill_weights()["hidden"]
    assert after >= before


def test_remember_active_survives_process_boundary(tmp_path, monkeypatch):
    monkeypatch.setenv("USE_ULE", "true")
    import analytics.ultimate_learning_engine as ule

    monkeypatch.setattr(ule, "_ACTIVE_PATH", tmp_path / "ule_last_active.json")
    ule.remember_active("NVDA", ["base", "neural", "lstm", "proven"])
    assert "neural" in ule.active_for_symbol("NVDA")
    assert "lstm" in ule.active_for_symbol("NVDA")
    assert ule.active_for_symbol("ZZZZNOPE") == []


def test_apply_to_p_up_returns_in_unit_interval(monkeypatch, tmp_path):
    monkeypatch.setenv("USE_ULE", "true")
    import analytics.ultimate_learning_engine as ule

    monkeypatch.setattr(ule, "_ACTIVE_PATH", tmp_path / "ule_last_active.json")
    from analytics.ultimate_learning_engine import apply_to_p_up, last_active

    p, meta = apply_to_p_up(
        "AAPL",
        0.62,
        context={
            "rsi_14": 45.0,
            "news_factor": 0.1,
            "crowd_pressure": 0.2,
            "neural_p_up": 0.55,
            "bull_bear_score": 0.3,
        },
    )
    assert 0.01 <= p <= 0.99
    assert meta.get("ule") is True
    assert meta.get("math") == "LEA"
    assert "base" in (meta.get("active") or [])
    assert last_active()


def test_delta_p_to_delta_ell_and_apply():
    from analytics.vector_math import apply_logit_tilt, delta_p_to_delta_ell, logit

    p0 = 0.6
    dp = 0.05
    dell = delta_p_to_delta_ell(p0, dp)
    p1 = apply_logit_tilt(p0, dell)
    assert abs(p1 - (p0 + dp)) < 1e-6
    # positive tilt raises logit
    assert logit(p1) > logit(p0)


def test_pattern_evidence_no_fuse(monkeypatch):
    from analytics.hidden_pattern_learn import pattern_evidence

    # No hits file / stale → not applied, but function must not raise
    ev = pattern_evidence("ZZZZNOPE")
    assert isinstance(ev, dict)
    assert "applied" in ev
