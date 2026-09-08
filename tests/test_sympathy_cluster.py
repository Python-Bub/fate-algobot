"""Sympathy peer warnings + panic limit entry rules."""
from __future__ import annotations

import unittest
from datetime import date, timedelta
from unittest.mock import patch

import pandas as pd


class TestSympathyClusterRules(unittest.TestCase):
    def setUp(self):
        from intel import algo_risk_filter as arf

        arf._load_config.cache_clear()

    def test_pltr_warns_when_orcl_in_buffer(self):
        from intel.algo_risk_filter import check_sympathy_peer_warnings

        today = date(2026, 6, 6)
        orcl_date = today + timedelta(days=4)

        def fake_earnings(sym, *, buffer_days=None, as_of=None):
            if sym == "ORCL":
                return True, "in buffer", {"days_to_earnings": 4, "next_earnings": orcl_date.isoformat()}
            return False, "clear", {"days_to_earnings": 30}

        with patch("intel.algo_risk_filter.check_earnings_conflict", side_effect=fake_earnings):
            warn, reason, meta = check_sympathy_peer_warnings("PLTR", warn_days=5, as_of=today)
        self.assertTrue(warn)
        self.assertIn("ORCL", reason)
        self.assertEqual(meta["sympathy_peer"], "ORCL")
        self.assertEqual(meta["max_hold_days"], 3)
        self.assertAlmostEqual(float(meta["take_profit_pct"]), 0.03, places=2)

    def test_avgo_panic_limit_band(self):
        from intel.algo_risk_filter import check_panic_drop_limit_entry

        idx = pd.date_range("2026-05-20", periods=10, freq="B")
        closes = [450, 440, 430, 420, 410, 400, 395, 412, 385.73, 384.0]
        hist = pd.DataFrame(
            {
                "Open": closes,
                "High": [c * 1.01 for c in closes],
                "Low": [c * 0.99 for c in closes],
                "Close": closes,
            },
            index=idx[: len(closes)],
        )
        with patch("intel.algo_risk_filter._daily_history", return_value=hist):
            active, reason, meta = check_panic_drop_limit_entry("AVGO")
        self.assertTrue(active)
        self.assertEqual(meta["limit_low"], 370.0)
        self.assertEqual(meta["limit_high"], 375.0)
        self.assertEqual(meta["entry_order_type"], "limit")

    def test_screen_pltr_approved_with_warning(self):
        from intel.algo_risk_filter import AlgoRiskFilter

        today = date(2026, 6, 6)

        def pass_check(*_a, **_k):
            return False, "ok", {}

        def orcl_earnings(sym, *, buffer_days=None, as_of=None):
            if sym == "ORCL":
                return True, "soon", {"days_to_earnings": 4, "next_earnings": (today + timedelta(days=4)).isoformat()}
            return False, "clear", {"days_to_earnings": 58}

        with patch("intel.algo_risk_filter.check_ma_status", return_value=(False, "")), patch(
            "intel.algo_risk_filter.check_earnings_conflict", side_effect=orcl_earnings
        ), patch("intel.algo_risk_filter.check_sector_sympathy", return_value=(False, "", {})), patch(
            "intel.algo_risk_filter.check_stabilization", return_value=(False, "", {})
        ), patch("intel.algo_risk_filter.check_panic_drop_limit_entry", return_value=(False, "", {})):
            res = AlgoRiskFilter(as_of=today).screen_ticker("PLTR", hold_days=5)
        self.assertTrue(res["approved"])
        self.assertTrue(res.get("warnings"))
        self.assertEqual(res["hold_days"], 3)
        self.assertEqual(res["trade_constraints"]["sympathy_peer"], "ORCL")


if __name__ == "__main__":
    unittest.main()
