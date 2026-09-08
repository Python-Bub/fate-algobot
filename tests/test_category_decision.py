"""Tests for 50-category spec decision engine."""

from __future__ import annotations

import unittest


class CategorySpecRegistryTests(unittest.TestCase):
    def test_all_fifty_specs_present(self):
        from analytics.industries.categories._registry import USER_CATEGORIES
        from analytics.industries.categories.specs import CATEGORY_SPECS, get_spec, get_spec_by_industry_id

        self.assertEqual(len(CATEGORY_SPECS), 50)
        for num, slug, display, iid in USER_CATEGORIES:
            spec = get_spec(slug)
            self.assertIsNotNone(spec, slug)
            self.assertEqual(spec.number, num)
            self.assertEqual(spec.slug, slug)
            self.assertTrue(spec.definition)
            self.assertTrue(spec.algo_key_metric)
            self.assertTrue(spec.prediction_feature)
            self.assertTrue(spec.correlation)
            self.assertTrue(spec.whole_group_movement)
            by_iid = get_spec_by_industry_id(iid)
            self.assertEqual(by_iid.slug, slug)

    def test_marine_transportation_spec(self):
        from analytics.industries.categories.specs import get_spec

        spec = get_spec("marine_transportation")
        self.assertEqual(spec.number, 47)
        self.assertEqual(spec.industry_id, "marine_shipping")
        self.assertEqual(spec.metric_type, "spot_charter")
        self.assertIn("Baltic", spec.prediction_feature)


class CategoryDecisionTests(unittest.TestCase):
    def test_biotech_blocks_on_trial_failure(self):
        from analytics.industries.category_decision import evaluate_category_decision

        cd = evaluate_category_decision(
            "MRNA",
            {"industry_id": "biotech"},
            {"vix": 25.0},
            ["Biotech trial failure on primary endpoint"],
        )
        self.assertTrue(cd.block_buy)
        self.assertIn("binary", " ".join(cd.notes).lower())

    def test_residential_reit_rate_shock_warns(self):
        from analytics.industries.category_decision import evaluate_category_decision

        cd = evaluate_category_decision(
            "EQR",
            {"industry_id": "residential_reits"},
            {"rate_shock_20d": 0.25, "spread_10y2y": -0.3},
            None,
        )
        self.assertTrue(cd.block_buy or cd.warn_buy)

    def test_defensive_pharma_boosts_on_high_vix(self):
        from analytics.industries.category_decision import evaluate_category_decision

        cd = evaluate_category_decision(
            "PFE",
            {"industry_id": "big_pharma"},
            {"vix": 30.0, "macro_score": -0.2},
            None,
        )
        self.assertGreater(cd.score_delta, 0.0)

    def test_category_module_evaluate_buy_decision(self):
        from analytics.industries.categories.biotechnology import CATEGORY

        cd = CATEGORY.evaluate_buy_decision("MRNA", {"cash_runway_months": 30})
        self.assertEqual(cd.notes[-1], "category=biotechnology")
        self.assertGreaterEqual(cd.buy_quality, 0.0)

    def test_wire_score_applies_category_delta(self):
        from analytics.industries.project_wiring import wire_score

        s0, p0 = 0.5, 0.55
        s1, p1, meta = wire_score(
            "PFE",
            s0,
            p0,
            {"industry_id": "big_pharma", "industry": {"primary": "big_pharma"}},
            macro_bundle={"vix": 28.0},
        )
        self.assertIn("category_decision", meta)
        self.assertNotEqual(s0, s1)


if __name__ == "__main__":
    unittest.main()
