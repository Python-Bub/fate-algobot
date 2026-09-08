"""Day-trade qty must not turn a 25bps stop into a 60% book bomb."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from analytics.day_trade_risk import size_position


class TestDayTradeNotionalCap(unittest.TestCase):
    def test_wmt_style_stop_cannot_buy_389_shares(self):
        env = {
            "HARD_MAX_ORDER_NOTIONAL": "2500",
            "DAY_TRADE_MAX_NOTIONAL": "2500",
            "DAY_TRADE_MAX_SHARES": "400",
            "DAY_TRADE_RISK_PER_TRADE_PCT": "0.0025",
            "DAY_TRADE_DEFAULT_STOP_PCT": "0.004",
            "MAX_SINGLE_ASSET_FRAC": "0.10",
        }
        with patch.dict(os.environ, env, clear=False):
            d = size_position(equity=72_126.0, entry_px=115.90, stop_px=115.44)
        self.assertTrue(d.ok, d.reason)
        self.assertLessEqual(d.qty * 115.90, 2500 * 1.02)
        self.assertLess(d.qty, 50)

    def test_rejects_name_above_hard_max(self):
        env = {
            "HARD_MAX_ORDER_NOTIONAL": "2500",
            "DAY_TRADE_MAX_NOTIONAL": "2500",
        }
        with patch.dict(os.environ, env, clear=False):
            d = size_position(equity=72_126.0, entry_px=3500.0, stop_px=3480.0)
        self.assertFalse(d.ok)
        self.assertEqual(d.reason, "name-too-expensive-for-cap")


if __name__ == "__main__":
    unittest.main()
