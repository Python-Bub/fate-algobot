import json
import os
import tempfile
import unittest
from unittest import mock

from risk_manager import RiskManager, base_symbol, monthly_drawdown_ok


class TestRiskPhase14(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.mkdtemp()
        os.environ["MONTHLY_EQUITY_STATE_FILE"] = os.path.join(self.td, "monthly_equity.json")
        os.environ["SECTOR_CACHE_FILE"] = os.path.join(self.td, "sector_cache.json")
        os.environ["USE_MONTHLY_DRAWDOWN_HALT"] = "false"
        os.environ["USE_SECTOR_RISK"] = "false"
        os.environ["MAX_TOTAL_EXPOSURE_FRAC"] = "0.70"
        os.environ["MAX_SINGLE_ASSET_FRAC"] = "0.05"

    def test_base_symbol_strips_short_suffix(self):
        self.assertEqual(base_symbol("AAPL:S"), "AAPL")

    def test_total_exposure_cap(self):
        os.environ["MAX_TOTAL_EXPOSURE_FRAC"] = "0.50"
        os.environ["MAX_SINGLE_ASSET_FRAC"] = "0.50"
        os.environ["USE_BUYING_POWER"] = "false"
        os.environ["FORTRESS_EXPOSURE_USE_BP"] = "false"
        rm = RiskManager(equity=100_000.0)
        rm.register_open("AAA", 30_000.0, 100.0, 95.0)
        ok, why = rm.can_open_explain("BBB", 30_000.0, 100.0, 95.0)
        self.assertFalse(ok)
        self.assertEqual(why, "total_exposure_cap")

    def test_single_asset_cap(self):
        rm = RiskManager(equity=100_000.0)
        rm.register_open("ZZZ", 4_800.0, 50.0, 45.0)
        ok, why = rm.can_open_explain("ZZZ", 600.0, 50.0, 45.0)
        self.assertFalse(ok)
        self.assertEqual(why, "single_asset_cap")

    def test_sector_cap(self):
        os.environ["USE_SECTOR_RISK"] = "true"
        os.environ["SECTOR_MAX_EXPOSURE_FRAC"] = "0.25"
        os.environ["MAX_SINGLE_ASSET_FRAC"] = "0.50"  # isolate sector rule (else 22k > 5% single cap)
        rm = RiskManager(equity=100_000.0)
        with mock.patch("risk_manager.get_sector", return_value="Technology"):
            ok1, _ = rm.can_open_explain("AAA", 4_000.0, 100.0, 95.0)
            self.assertTrue(ok1)
            rm.register_open("AAA", 4_000.0, 100.0, 95.0)
            ok2, why = rm.can_open_explain("BBB", 22_000.0, 100.0, 95.0)
            self.assertFalse(ok2)
            self.assertEqual(why, "sector_cap")

    def test_monthly_drawdown_halt(self):
        os.environ["USE_MONTHLY_DRAWDOWN_HALT"] = "true"
        os.environ["MONTHLY_DRAWDOWN_HALT_PCT"] = "0.10"
        p = os.environ["MONTHLY_EQUITY_STATE_FILE"]
        if os.path.isfile(p):
            os.remove(p)
        from datetime import datetime, timezone

        mk = f"{datetime.now(timezone.utc).year:04d}-{datetime.now(timezone.utc).month:02d}"
        st = {"month_key": mk, "start_equity": 100_000.0, "peak_equity": 100_000.0}
        with open(p, "w", encoding="utf-8") as f:
            json.dump(st, f)
        ok2, r2 = monthly_drawdown_ok(88_000.0)
        self.assertFalse(ok2)
        self.assertIn("monthly_dd", r2)


class TestFredMacro(unittest.TestCase):
    def test_no_key_neutral(self):
        from signals import fred_macro

        with mock.patch.dict(os.environ, {"FRED_API_KEY": ""}, clear=False):
            fred_macro._MEM["t"] = 0.0
            fred_macro._MEM["bundle"] = None
            b = fred_macro.get_macro_bundle(force_refresh=True)
            self.assertFalse(b["ok"])
            self.assertEqual(b["macro_score"], 0.0)

    def test_with_key_parses_spread(self):
        from signals import fred_macro

        def fake_get(url, params=None, timeout=None):
            class R:
                status_code = 200

                def raise_for_status(self):
                    return None

                def json(self):
                    return {"observations": [{"value": "4.5"}, {"value": "4.4"}]}

            return R()

        fred_macro._MEM["t"] = 0.0
        fred_macro._MEM["bundle"] = None
        with mock.patch.dict(os.environ, {"FRED_API_KEY": "fake"}, clear=False):
            with mock.patch("signals.fred_macro.requests.get", side_effect=fake_get):
                b = fred_macro.get_macro_bundle(force_refresh=True)
                self.assertTrue(b["ok"])
                self.assertIsNotNone(b["spread_10y2y"])


class TestHeadlineParallel(unittest.TestCase):
    def test_parallel_disabled_calls_sync(self):
        os.environ["USE_PARALLEL_NEWS_FETCH"] = "false"
        from intel.headline_fetch_parallel import fetch_headline_groups_parallel

        with mock.patch("intel.headline_fetch_parallel.fetch_finnhub_headlines", return_value=["a"]), \
             mock.patch("intel.headline_fetch_parallel.fetch_newsapi_headlines", return_value=["b"]), \
             mock.patch("intel.headline_fetch_parallel.fetch_cramer_mentions", return_value=["c"]), \
             mock.patch("intel.api_budget.cache_get", return_value=None), \
             mock.patch("intel.api_budget.should_skip_newsapi", return_value=False), \
             mock.patch("intel.api_budget.should_skip_cramer_newsapi", return_value=False):
            a, b, c = fetch_headline_groups_parallel("X")
            self.assertEqual(a, ["a"])
            self.assertEqual(b, ["b"])
            self.assertEqual(c, ["c"])


if __name__ == "__main__":
    unittest.main()
