"""Unit tests for intel.algo_risk_filter contextual gates."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pandas as pd


class TestAlgoRiskFilter(unittest.TestCase):
    def setUp(self):
        self._env = os.environ.copy()
        os.environ["ALGO_RISK_ALPACA_MA"] = "false"
        os.environ.pop("EMERGENCY_BYPASS_ALGO_RISK", None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)
        from intel import algo_risk_filter as arf

        arf._load_config.cache_clear()

    def test_tmhc_blocked_by_pending_acquisition(self):
        from intel.algo_risk_filter import check_ma_status

        blocked, reason = check_ma_status("TMHC")
        self.assertTrue(blocked)
        self.assertIn("Berkshire", reason)

    def test_earnings_buffer_blocks_within_window(self):
        from intel.algo_risk_filter import check_earnings_conflict

        today = date(2026, 6, 7)
        earn = today + timedelta(days=3)

        with patch("intel.algo_risk_filter._next_earnings_date", return_value=(earn, 3)):
            blocked, reason, meta = check_earnings_conflict("ORCL", buffer_days=5, as_of=today)
        self.assertTrue(blocked)
        self.assertIn("3 day", reason)
        self.assertEqual(meta["days_to_earnings"], 3)

    def test_earnings_clear_outside_buffer(self):
        from intel.algo_risk_filter import check_earnings_conflict

        today = date(2026, 5, 30)
        earn = date(2026, 6, 10)

        with patch("intel.algo_risk_filter._next_earnings_date", return_value=(earn, 11)):
            blocked, reason, _ = check_earnings_conflict("ORCL", buffer_days=5, as_of=today)
        self.assertFalse(blocked)
        self.assertIn("11d", reason)

    def test_sector_sympathy_blocks_pltr_when_orcl_earnings_imminent(self):
        from intel.algo_risk_filter import check_sector_sympathy

        today = date(2026, 6, 8)

        def fake_earnings(sym, *, as_of=None, buffer_days=None):
            if sym == "ORCL":
                return True, "Earnings in 2 day(s)", {"days_to_earnings": 2}
            return False, "clear", {"days_to_earnings": 30}

        with patch("intel.algo_risk_filter.check_earnings_conflict", side_effect=fake_earnings):
            blocked, reason, meta = check_sector_sympathy("PLTR", sympathy_days=2, as_of=today)
        self.assertTrue(blocked)
        self.assertIn("ORCL", reason)
        self.assertEqual(meta["cluster"], "AI_INFRA")

    def test_stabilization_blocks_after_large_drop_without_tight_range(self):
        from intel.algo_risk_filter import check_stabilization

        idx = pd.date_range("2026-05-20", periods=10, freq="B")
        closes = [100, 99, 98, 97, 96, 95, 94, 80, 79, 78]
        hist = pd.DataFrame(
            {
                "Open": closes,
                "High": [c * 1.04 for c in closes],
                "Low": [c * 0.96 for c in closes],
                "Close": closes,
            },
            index=idx,
        )

        with patch("intel.algo_risk_filter._daily_history", return_value=hist):
            blocked, reason, meta = check_stabilization(
                "AVGO", weekly_drop_pct=0.15, range_pct=0.02, sessions=3
            )
        self.assertTrue(blocked)
        self.assertIn("weekly drop", reason.lower())
        self.assertFalse(meta["stabilized"])

    def test_stabilization_passes_after_tight_sessions(self):
        from intel.algo_risk_filter import check_stabilization

        idx = pd.date_range("2026-05-20", periods=11, freq="B")
        base = [100, 99, 98, 97, 96, 95, 94, 80]
        tight = [80.1, 80.0, 79.95]
        closes = base + tight
        hist = pd.DataFrame(
            {
                "Open": closes,
                "High": [c * 1.005 for c in closes],
                "Low": [c * 0.995 for c in closes],
                "Close": closes,
            },
            index=idx[: len(closes)],
        )

        with patch("intel.algo_risk_filter._daily_history", return_value=hist):
            blocked, reason, meta = check_stabilization(
                "AVGO", weekly_drop_pct=0.15, range_pct=0.02, sessions=3
            )
        self.assertFalse(blocked)
        self.assertTrue(meta["stabilized"])

    def test_screen_ticker_orcl_rejects_on_earnings(self):
        from intel.algo_risk_filter import AlgoRiskFilter

        today = date(2026, 6, 7)
        earn = today + timedelta(days=2)
        with patch("intel.algo_risk_filter._next_earnings_date", return_value=(earn, 2)):
            res = AlgoRiskFilter(buffer_days=5, as_of=today).screen_ticker("ORCL")
        self.assertFalse(res["approved"])
        self.assertEqual(res["rule"], "earnings_buffer")

    def test_screen_ticker_tmhc_rejects_on_ma(self):
        from intel.algo_risk_filter import AlgoRiskFilter

        res = AlgoRiskFilter(as_of=date(2026, 5, 30)).screen_ticker("TMHC")
        self.assertFalse(res["approved"])
        self.assertEqual(res["rule"], "ma_lock")

    def test_apply_risk_gate_to_row_sets_no_trade(self):
        from intel.algo_risk_filter import apply_risk_gate_to_row

        row = {"ticker": "TMHC", "gate_detail": "all_ok", "asym_action": "LONG"}
        out = apply_risk_gate_to_row(row)
        self.assertEqual(out["asym_action"], "NO_TRADE")
        self.assertIn("risk:ma_lock", out["gate_detail"])

    def test_custom_config_path(self):
        from intel import algo_risk_filter as arf

        arf._load_config.cache_clear()
        with tempfile.TemporaryDirectory() as td:
            cfg = {
                "pending_acquisitions": {
                    "TESTX": {"status": "definitive", "acquirer": "BuyerCo", "offer_price": 10.0}
                },
                "sector_clusters": {"TEST_CLUSTER": ["TESTX", "TESTY"]},
                "cluster_leaders": {"TEST_CLUSTER": ["TESTX"]},
            }
            p = Path(td) / "risk.json"
            p.write_text(json.dumps(cfg), encoding="utf-8")
            os.environ["ALGO_RISK_CONFIG_PATH"] = str(p)
            arf._load_config.cache_clear()
            blocked, reason = arf.check_ma_status("TESTX")
            self.assertTrue(blocked)
            self.assertIn("BuyerCo", reason)


if __name__ == "__main__":
    unittest.main()
