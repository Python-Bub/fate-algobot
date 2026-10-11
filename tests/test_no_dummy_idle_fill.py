"""Zero-score names must not eat leftover cash."""

import numpy as np

from analytics.rank_pipeline import vectorized_target_weights


def test_zero_scores_leave_cash_idle():
    w = vectorized_target_weights([0.0, 0.0, 0.0], total_capital=39_121.0, min_score=0.0)
    assert float(np.sum(w)) == 0.0


def test_min_score_floor_does_not_fallback_to_all():
    w = vectorized_target_weights([0.01, 0.0, -0.2], total_capital=10_000.0, min_score=0.02)
    assert float(np.sum(w)) == 0.0


def test_positive_scores_still_allocate():
    w = vectorized_target_weights([0.4, 0.1, 0.0], total_capital=1_000.0, min_score=0.05)
    assert float(w[0]) > 0 and float(w[1]) > 0
    assert float(w[2]) == 0.0
    assert float(np.sum(w)) > 0
    assert float(np.sum(w)) <= 1000.0 + 1e-6


def test_last_wins_refuses_dummy_idle_dump():
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "data" / "deploy_scale.env").read_text()
    dummy = text.rsplit("stop dummy idle-cash dumps", 1)[-1]
    assert "FORTRESS_RELAX_GATES_ON_FILL=false" in dummy
    halt = text.rsplit("stop false halt", 1)[-1]
    assert "FORTRESS_RELAX_GATES_ON_FILL=false" in halt
    assert "FORTRESS_OVERNIGHT_CASH_DEPLOY=true" in halt
