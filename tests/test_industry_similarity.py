"""Tests for soft similarity + RL industry blending."""

from __future__ import annotations

import unittest


class IndustrySimilarityTests(unittest.TestCase):
    def test_amazon_gets_multi_industry_blend(self):
        from analytics.industries.integration import get_industry_profile

        prof = get_industry_profile(
            "AMZN",
            news_headlines=["Amazon AWS cloud revenue growth", "e-commerce retail marketplace"],
        )
        blend = prof.get("blend_weights") or {}
        self.assertGreaterEqual(len(blend), 2, blend)
        ids = set(blend.keys())
        self.assertTrue(
            ids & {"hypermarkets_discount", "interactive_media", "application_software", "industrial_logistics_reits"},
            f"unexpected blend {blend}",
        )

    def test_similarity_neighbors_ranked(self):
        from analytics.industries.similarity_engine import nearest_categories

        hits = nearest_categories(
            "TSLA",
            {"industry_id": "auto_manufacturers", "yahoo_industry": "auto manufacturers", "confidence": 0.7},
            top_k=5,
        )
        self.assertGreaterEqual(len(hits), 3)
        top_ids = [h[0] for h in hits[:3]]
        self.assertIn("auto_manufacturers", top_ids)

    def test_rl_updates_affinity(self):
        from analytics.industries.industry_rl import affinity_offsets, update_from_trade

        rep = update_from_trade(
            "TEST",
            0.04,
            "LONG",
            blend_weights={"semiconductors": 0.6, "tech_hardware": 0.4},
            reward=0.5,
        )
        self.assertTrue(rep.get("applied"))
        aff = affinity_offsets("TEST")
        self.assertIn("semiconductors", aff)
        self.assertGreater(aff["semiconductors"], 0.0)

    def test_blended_category_decision(self):
        from analytics.industries.category_decision import evaluate_category_decision

        cd = evaluate_category_decision(
            "AMZN",
            {
                "blend_weights": {"hypermarkets_discount": 0.55, "application_software": 0.45},
                "industry_id": "hypermarkets_discount",
            },
            {"vix": 22.0, "nasdaq_ret_5d": 0.03},
            None,
        )
        self.assertTrue(any("blended_categories" in n for n in cd.notes))


if __name__ == "__main__":
    unittest.main()
