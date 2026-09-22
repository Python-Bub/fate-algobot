"""Family forecast must not surface junk A-tickers from stale full scans."""
import json
import os
import unittest
from pathlib import Path


class TestFamilyForecastQuality(unittest.TestCase):
    def test_eligible_rows_exclude_obscure_a_names(self):
        os.environ["PAPER_SIM_ACTIVE_MODE"] = "top100_rotate"
        os.environ["PAPER_SIM_ACTIVE_MAX"] = "480"
        from fortress_universe import trade_quality_universe
        from tools.family_forecast import _best_from_report, _eligible_rows

        rep = Path("reports/paper_sim_20260605.json")
        if not rep.is_file():
            self.skipTest("no paper sim report")
        rows = json.loads(rep.read_text())["rows"]
        eligible = _eligible_rows(rows)
        tickers = {str(r.get("ticker", "")).upper() for r in eligible}
        quality = trade_quality_universe()
        self.assertIn("AAPL", quality)
        self.assertIn("MSFT", quality)
        aapl_in_report = [r for r in rows if str(r.get("ticker", "")).upper() == "AAPL"]
        if aapl_in_report:
            self.assertIn("AAPL", tickers)
        self.assertNotIn("AN", tickers)
        self.assertNotIn("AGCC", tickers)
        picks = _best_from_report(rows, bullish=0.55, bearish=0.45)
        self.assertGreaterEqual(len(picks), 1)
        for p in picks:
            self.assertNotIn(p.ticker, {"AN", "AGCC", "AAAA", "HACK"})
            self.assertIn(p.signal, ("UP", "HOLD", "DOWN"))
            if p.signal == "DOWN":
                self.assertGreaterEqual(max(0, 100 - p.chance_pct), 55)
            else:
                self.assertGreaterEqual(p.chance_pct, 55)


    def test_family_forecast_skips_live_yahoo_by_default(self):
        from unittest.mock import patch

        from tools import family_forecast as ff

        with patch("intel.algo_risk_filter.blocks_buy") as mock_blocks:
            self.assertFalse(ff._live_headwinds_enabled())
            self.assertFalse(ff._live_risk_check_enabled())
            rows = [
                {
                    "ticker": "AAPL",
                    "skipped": False,
                    "top100": True,
                    "p_daily_model_raw": 0.62,
                    "p_short_model_raw": 0.6,
                    "p_long_model_raw": 0.58,
                    "p_xlong_model_raw": 0.65,
                    "asym_action": "LONG",
                    "score": 0.2,
                }
            ]
            ff._best_from_report(rows, bullish=0.55, bearish=0.45)
            mock_blocks.assert_not_called()

    def test_hack_excluded_from_family(self):
        from tools.family_forecast import _family_symbol_ok

        ok, reason = _family_symbol_ok("HACK", {"asym_action": "LONG"}, days=1)
        self.assertFalse(ok)
        self.assertIn("block", reason.lower())

    def test_independent_horizons_keep_disagreeing_1d(self):
        old = {
            k: os.environ.get(k)
            for k in (
                "HORIZON_INDEPENDENT",
                "FAMILY_UNIFIED_INTEL",
                "FAMILY_LIVE_HEADWINDS",
                "FAMILY_LIVE_RISK_CHECK",
                "FAMILY_TOP100_ONLY",
                "FAMILY_MOMENTUM_GATE",
                "FAMILY_REQUIRE_ASYM_LONG",
                "FAMILY_MIN_SCORE",
            )
        }
        os.environ["HORIZON_INDEPENDENT"] = "true"
        os.environ["FAMILY_UNIFIED_INTEL"] = "false"
        os.environ["FAMILY_LIVE_HEADWINDS"] = "false"
        os.environ["FAMILY_LIVE_RISK_CHECK"] = "false"
        os.environ["FAMILY_TOP100_ONLY"] = "false"
        os.environ["FAMILY_MOMENTUM_GATE"] = "false"
        os.environ["FAMILY_REQUIRE_ASYM_LONG"] = "false"
        os.environ["FAMILY_MIN_SCORE"] = "0"
        try:
            from unittest.mock import patch

            from tools.family_forecast import _best_from_report

            row = {
                "ticker": "NVDA",
                "skipped": False,
                "top100": True,
                "p_daily_model_raw": 0.81,
                "p_short_model_raw": 0.40,
                "p_long_model_raw": 0.38,
                "p_xlong_model_raw": 0.22,
                "asym_action": "LONG",
                "score": 0.2,
            }
            with patch("intel.unified_intel.blocks_long", return_value=(False, [])), patch(
                "tools.family_forecast._family_intel_blocks", return_value=(False, [])
            ), patch("tools.family_forecast._prefetch_macro_bundle", return_value={}):
                picks = _best_from_report([row], bullish=0.55, bearish=0.45)
            by = {}
            for p in picks:
                by.setdefault(p.label, []).append(p)
            self.assertTrue(any(p.ticker == "NVDA" and p.signal == "UP" for p in by.get("one_day", [])))
            self.assertTrue(any(p.ticker == "NVDA" and p.signal == "DOWN" for p in by.get("six_months", [])))
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_bounce_name_skips_short_horizons(self):
        old = os.environ.get("HORIZON_INDEPENDENT")
        os.environ["HORIZON_INDEPENDENT"] = "false"
        try:
            from tools.family_forecast import _best_from_report

            row = {
                "ticker": "ISRG",
                "skipped": False,
                "top100": True,
                "p_daily_model_raw": 0.54,
                "p_short_model_raw": 0.53,
                "p_long_model_raw": 0.47,
                "p_xlong_model_raw": 0.86,
                "ur_detected": True,
                "ur_rationale": "undercut_and_rally",
                "dip_signal": 0.28,
                "asym_action": "NO_TRADE",
                "score": -0.03,
                "fund_score": 0.6,
                "ur_score": 0.2,
            }
            picks = _best_from_report([row], bullish=0.55, bearish=0.45)
            labels = {p.label: p.ticker for p in picks}
            self.assertNotIn("one_day", labels)
            self.assertNotIn("one_week", labels)
            self.assertEqual(labels.get("one_month"), "ISRG")
            self.assertEqual(labels.get("six_months"), "ISRG")
        finally:
            if old is None:
                os.environ.pop("HORIZON_INDEPENDENT", None)
            else:
                os.environ["HORIZON_INDEPENDENT"] = old


if __name__ == "__main__":
    unittest.main()
