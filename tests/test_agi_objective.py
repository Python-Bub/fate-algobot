"""Tests for AGI objective + guarded code editor."""

from __future__ import annotations

import unittest


class TestAgiObjective(unittest.TestCase):
    def test_primary_objective_default(self):
        from self_modify.objective_engine import DEFAULT_OBJECTIVE, primary_objective

        self.assertIn("portfolio", primary_objective().lower() or DEFAULT_OBJECTIVE.lower())

    def test_stale_cash_credit_is_not_a_win(self):
        import json
        import tempfile
        from pathlib import Path

        from self_modify import objective_engine as oe

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "objective_state.json"
            hist = root / "equity_history.jsonl"
            state.write_text(
                json.dumps(
                    {
                        "last_equity": 71871.86,
                        "baseline_equity": 73823.02,
                        "growth_streak": 1,
                        "growth_vs_baseline": -0.02643023815606571,
                    }
                ),
                encoding="utf-8",
            )
            orig_state, orig_hist = oe.STATE_PATH, oe.HISTORY_PATH
            orig_fetch = oe.fetch_account_equity
            oe.STATE_PATH = state
            oe.HISTORY_PATH = hist
            oe.fetch_account_equity = lambda: {
                "ok": True,
                "equity": 89605.08,
                "cash": 45443.55,
                "buying_power": 1.0,
                "deployed_mv": 44161.53,
                "n_positions": 27,
                "deployed_frac": 0.49,
            }
            try:
                row = oe.record_equity_snapshot(source="test")
            finally:
                oe.STATE_PATH = orig_state
                oe.HISTORY_PATH = orig_hist
                oe.fetch_account_equity = orig_fetch
        self.assertEqual(row["delta"], 0.0)
        self.assertGreater(row["external_cash"], 15_000)
        self.assertAlmostEqual(row["growth_vs_baseline"], -0.02643023815606571, places=4)

    def test_flat_book_cash_increase_is_external(self):
        from self_modify.objective_engine import split_skill_delta

        skill, external = split_skill_delta(
            prev_cash=21_336.0,
            prev_mv=48_076.0,
            cash=42_139.0,
            mv=48_076.0,
            equity_delta=20_803.0,
            prev_equity=69_412.0,
        )
        self.assertEqual(skill, 0.0)
        self.assertAlmostEqual(external, 20_803.0, places=2)
        skill, external = split_skill_delta(
            prev_cash=20_000.0,
            prev_mv=50_000.0,
            cash=25_000.0,
            mv=45_200.0,
            equity_delta=200.0,
            prev_equity=70_000.0,
        )
        self.assertAlmostEqual(skill, 200.0, places=2)
        self.assertEqual(external, 0.0)

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
