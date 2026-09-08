"""Tests for guarded self-improvement overlay."""

from __future__ import annotations

import unittest


class TestSelfImprove(unittest.TestCase):
    def test_overlay_validation_accepts_seed(self):
        from self_modify.code_evolver import _validate_overlay_source
        from self_modify.strategy_overlay import OVERLAY_PATH

        src = OVERLAY_PATH.read_text(encoding="utf-8")
        ok, reason = _validate_overlay_source(src)
        self.assertTrue(ok, reason)

    def test_always_mutate_produces_code(self):
        from self_modify.code_evolver import _rule_based_proposal

        p = _rule_based_proposal({"losing_to_market": True, "alpha": -0.01}, recipe_idx=0)
        self.assertNotEqual(p.get("rationale"), "neutral_hold")
        self.assertTrue(p.get("hf_deltas") or p.get("rank_rules"))

    def test_overlay_loads(self):
        from self_modify.strategy_overlay import (
            beat_market_mode,
            hf_weight_deltas,
            hft_confidence_delta,
            paper_score_boost,
            rank_tilt,
            policy_hints,
        )

        deltas = hf_weight_deltas()
        self.assertIsInstance(deltas, dict)
        tilt = rank_tilt("SPY", 0.6, {"rsi_14": 55, "alpha": -0.01})
        self.assertGreaterEqual(tilt, -0.12)
        self.assertLessEqual(tilt, 0.12)
        self.assertIsInstance(paper_score_boost("AAPL", 0.5, {"alpha": -0.01}), float)
        self.assertIsInstance(hft_confidence_delta({"deployed_frac": 0.3}), float)
        self.assertTrue(beat_market_mode({"alpha": -0.01}))
        hints = policy_hints({"deployed_frac": 0.5})
        self.assertIsInstance(hints, dict)

    def test_rule_proposal_runs(self):
        from self_modify.code_evolver import _rule_based_proposal

        p = _rule_based_proposal({"deployed_frac": 0.1, "paper_pnl": 0.0, "hit_rate": 0.5})
        self.assertIn("rationale", p)
        self.assertIn("hf_deltas", p)

    def test_render_and_validate(self):
        from self_modify.code_evolver import _render_overlay, _validate_overlay_source

        prop = {
            "rationale": "test",
            "hf_deltas": {"HF_W_MOMENTUM": 0.01},
            "rank_rules": ["pass"],
            "policy_lines": ["pass"],
        }
        metrics = {"benchmark": "SPY", "alpha": -0.01, "losing_to_market": True}
        src = _render_overlay(prop, 1, metrics)
        ok, reason = _validate_overlay_source(src)
        self.assertTrue(ok, reason)


if __name__ == "__main__":
    unittest.main()
