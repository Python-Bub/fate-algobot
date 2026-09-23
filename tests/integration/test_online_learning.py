import os
import unittest
from unittest import mock

import numpy as np

from analytics.asymmetric_loss import asymmetric_reward
from analytics.asymmetric_meta_filter import asymmetric_decision


class TestAsymmetricLoss(unittest.TestCase):
    def test_long_correct_positive(self):
        rw = asymmetric_reward("LONG", 0.02, bars_held=1)
        self.assertGreater(rw.reward, 0.0)
        self.assertTrue(rw.correct)

    def test_long_wrong_penalized(self):
        rw = asymmetric_reward("LONG", -0.02, bars_held=1)
        self.assertLess(rw.reward, 0.0)
        self.assertFalse(rw.correct)
        # 5x penalty multiplier on losing longs
        self.assertLess(rw.reward, -0.02 * 4.0)

    def test_short_wrong_more_penalized_than_long(self):
        # Default convention is position P&L: a losing short is a negative number.
        rl = asymmetric_reward("LONG", -0.02, bars_held=1).reward
        rs = asymmetric_reward("SHORT", -0.02, bars_held=1).reward
        self.assertLess(rl, 0.0)
        self.assertLess(rs, rl)

    def test_price_return_convention_flips_short(self):
        # position_pnl=False: input is the underlying price return, so a SHORT
        # into a +2% move is a loss and a SHORT into a -2% move is a win.
        lose = asymmetric_reward("SHORT", 0.02, bars_held=1, position_pnl=False)
        win = asymmetric_reward("SHORT", -0.02, bars_held=1, position_pnl=False)
        self.assertFalse(lose.correct)
        self.assertLess(lose.reward, 0.0)
        self.assertTrue(win.correct)
        self.assertGreater(win.reward, 0.0)
        # Explicit position_pnl=True must ignore the env fallback.
        with mock.patch.dict(os.environ, {"ASYM_POSITION_PNL": "false"}):
            pos = asymmetric_reward("SHORT", 0.02, bars_held=1, position_pnl=True)
            self.assertTrue(pos.correct)


class TestAsymmetricFilter(unittest.TestCase):
    def setUp(self):
        os.environ["USE_ASYM_META_FILTER"] = "true"
        os.environ["LONG_DECISION_THRESHOLD"] = "0.90"
        os.environ["SHORT_DECISION_THRESHOLD"] = "0.80"
        os.environ["ASYM_REQUIRE_EXEC_CONF"] = "false"

    def test_long_zone(self):
        d = asymmetric_decision(0.95, 0.99, 0.95)
        self.assertEqual(d.action, "LONG")

    def test_short_zone(self):
        d = asymmetric_decision(0.10, 0.99, 0.95)
        self.assertEqual(d.action, "SHORT")

    def test_no_trade_zone(self):
        d = asymmetric_decision(0.55, 0.99, 0.95)
        self.assertEqual(d.action, "NO_TRADE")
        self.assertEqual(d.rationale, "in_no_trade_zone")

    def test_exec_floor_blocks(self):
        os.environ["ASYM_REQUIRE_EXEC_CONF"] = "true"
        d = asymmetric_decision(0.95, 0.50, 0.95)
        self.assertEqual(d.action, "NO_TRADE")
        self.assertEqual(d.rationale, "exec_conf_below_floor")


class TestOnlineUpdater(unittest.TestCase):
    def test_disabled_by_default(self):
        os.environ.pop("USE_ONLINE_UPDATER", None)
        from online_learning.weight_updater import online_update_meta_for_trade

        rep = online_update_meta_for_trade(
            "FAKETICKER",
            {"p_short": 0.6, "p_long": 0.6, "vol_regime_ratio": 1.0},
            "LONG",
            -0.05,
        )
        self.assertFalse(rep.applied)
        self.assertEqual(rep.reason, "updater_disabled")

    def test_micro_step_changes_weights(self):
        os.environ["USE_ONLINE_UPDATER"] = "true"
        os.environ["ONLINE_LR"] = "0.5"  # exaggerate so the test sees a delta

        from sklearn.linear_model import LogisticRegression
        from analytics.meta_stack import MetaStackResult

        # Fit a tiny meta model so coef_/intercept_ exist with the expected dim.
        X = np.random.RandomState(0).normal(size=(80, 7))
        y = (X[:, 0] + X[:, 1] > 0).astype(int)
        m = LogisticRegression(max_iter=400).fit(X, y)
        res = MetaStackResult(auc=0.5, rows=80, features=["p_short", "p_long", "p_gap", "vol_regime_ratio", "sentiment_impulse", "regime_transition_flag", "alpha_proxy_20"])

        with mock.patch("analytics.meta_stack.load_meta_stack", return_value=m), \
             mock.patch("analytics.meta_stack.save_meta_stack", return_value="/tmp/fake.pkl"):
            from online_learning.weight_updater import online_update_meta_for_trade

            rep = online_update_meta_for_trade(
                "FAKE",
                {"p_short": 0.4, "p_long": 0.6, "vol_regime_ratio": 1.0, "alpha_proxy_20": 0.1},
                "LONG",
                -0.10,
            )
            self.assertTrue(rep.applied)
            self.assertGreater(rep.delta_l2, 0.0)


if __name__ == "__main__":
    unittest.main()
