"""Tests for AGI objective + guarded code editor."""

from __future__ import annotations

import unittest


class TestAgiObjective(unittest.TestCase):
    def test_primary_objective_default(self):
        from self_modify.objective_engine import DEFAULT_OBJECTIVE, primary_objective

        self.assertIn("portfolio", primary_objective().lower() or DEFAULT_OBJECTIVE.lower())

    def test_objective_reward_bounded(self):
        from self_modify.objective_engine import objective_reward

        r = objective_reward({"equity": 100000, "equity_delta": 500, "equity_growth_pct": 0.005})
        self.assertGreaterEqual(r, -1.0)
        self.assertLessEqual(r, 1.0)

    def test_hooks_validation_accepts_seed(self):
        from self_modify.code_editor import _validate_hooks_source
        from self_modify.custom_hooks import __file__ as hooks_path
        from pathlib import Path

        src = Path(hooks_path).read_text(encoding="utf-8")
        ok, reason = _validate_hooks_source(src)
        self.assertTrue(ok, reason)

    def test_custom_hooks_callable(self):
        from self_modify.custom_hooks import equity_rank_boost, fortress_size_mult, policy_priority_hints

        red = {"equity_delta": -10, "p_up": 0.62, "deployed_frac": 0.4}
        b = equity_rank_boost("AAPL", 0.6, red)
        self.assertEqual(b, 0.0)
        m = fortress_size_mult({"equity_delta": -10, "deployed_frac": 0.3})
        self.assertLess(m, 1.0)
        self.assertGreaterEqual(m, 0.85)
        hints = policy_priority_hints({"equity_delta": -10, "cur_buy": 0.58, "cur_notional": 8000})
        self.assertGreaterEqual(hints["BUY_THRESHOLD"], 0.58)
        self.assertLessEqual(hints["ORDER_NOTIONAL"], 8000)
        hints = policy_priority_hints({"deployed_frac": 0.4, "cur_buy": 0.58, "cur_notional": 8000})
        self.assertIsInstance(hints, dict)


if __name__ == "__main__":
    unittest.main()
