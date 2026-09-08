"""Tests for industry specialized pipeline modules."""

from __future__ import annotations

import unittest

from analytics.industries.base import IndustryContext
from analytics.industries.handlers import ALL_HANDLERS
from analytics.industries.pipeline import run_industry_pipeline
from analytics.industries.specialized import ALL_SPECIALIZED, get_specialized


class TestSpecializedRegistry(unittest.TestCase):
    def test_fifty_specialized_modules(self):
        ids = [k for k in ALL_SPECIALIZED if k != "unclassified"]
        self.assertGreaterEqual(len(ids), 49)

    def test_each_specialized_runs(self):
        ctx = IndustryContext(
            symbol="TEST",
            macro={"rate_shock_20d": 0.0, "spread_10y2y": 0.1, "pmi_score": 0.2, "vix": 20.0, "nasdaq_ret_5d": 0.01},
        )
        for iid, logic in list(ALL_SPECIALIZED.items())[:10]:
            handler = ALL_HANDLERS.get(iid) or ALL_HANDLERS["unclassified"]
            res = logic.run(ctx, handler)
            self.assertIsNotNone(res)


class TestPipelineGates(unittest.TestCase):
    def test_reit_blocks_on_rate_shock(self):
        pipe = run_industry_pipeline(
            "EQR",
            macro_bundle={"rate_shock_20d": 0.3, "spread_10y2y": 0.0, "vix": 20.0, "pmi_score": 0.0, "nasdaq_ret_5d": 0.0},
        )
        self.assertTrue(pipe.get("block_long"))

    def test_biotech_blocks_clinical_hold(self):
        pipe = run_industry_pipeline(
            "MRNA",
            news_headlines=["FDA places clinical hold on lead trial after safety concern"],
        )
        self.assertTrue(pipe.get("block_long"))

    def test_semis_pipeline_score(self):
        pipe = run_industry_pipeline(
            "NVDA",
            macro_bundle={"pmi_score": 0.7, "nasdaq_ret_5d": 0.03, "rate_shock_20d": 0.0, "vix": 18.0, "spread_10y2y": 0.1},
        )
        self.assertEqual(pipe.get("industry_id"), "semiconductors")
        self.assertIsInstance(pipe.get("score_delta"), float)

    def test_feature_weights_present(self):
        pipe = run_industry_pipeline("AAPL")
        weights = pipe.get("feature_weights") or {}
        self.assertTrue(weights)


class TestIntegrationRank(unittest.TestCase):
    def test_blended_rank_includes_pipeline(self):
        from analytics.industries.integration import blended_rank_adjustment

        adj = blended_rank_adjustment(
            "NVDA",
            {"industry_z_20": 0.0, "industry_residual_1d": 0.0},
            macro_bundle={"pmi_score": 0.5, "nasdaq_ret_5d": 0.02, "rate_shock_20d": 0.0, "vix": 18.0, "spread_10y2y": 0.1},
        )
        self.assertIn("pipeline", adj)
        self.assertIn("score_delta", adj)


class TestAlgoRiskIndustryGate(unittest.TestCase):
    def test_blocks_reit_rate_shock(self):
        from intel.algo_risk_filter import check_industry_pipeline

        blocked, reason, _ = check_industry_pipeline(
            "EQR",
            macro_bundle={"rate_shock_20d": 0.35, "spread_10y2y": 0.0, "vix": 20.0, "pmi_score": 0.0, "nasdaq_ret_5d": 0.0},
        )
        self.assertTrue(blocked)
        self.assertIn("rate", reason.lower())


if __name__ == "__main__":
    unittest.main()
