"""Tests for top-50% universe tier and AI industry registry."""

from __future__ import annotations

import unittest
from unittest.mock import patch


class TestTop50UniverseTier(unittest.TestCase):
    def test_trainable_pool_is_thousands_not_hundreds(self):
        from universe_lifecycle.rankings import _trainable_model_pool

        pool = _trainable_model_pool()
        self.assertGreater(len(pool), 3000, msg=f"pool={len(pool)}")

    def test_top50_target_is_half_of_pool(self):
        from universe_lifecycle.rankings import _trainable_model_pool

        pool = _trainable_model_pool()
        half = max(1, len(pool) // 2)
        self.assertGreater(half, 1500)
        self.assertLess(abs(half - len(pool) * 0.5), 2)

    @patch("universe_lifecycle.rankings._refresh_caps_progressive")
    def test_refresh_writes_correct_top50_size(self, mock_refresh):
        from universe_lifecycle.rankings import refresh_market_cap_tiers

        mock_refresh.side_effect = lambda pool, cached: cached
        with patch("universe_lifecycle.rankings._trainable_model_pool") as mock_pool:
            mock_pool.return_value = [f"T{i}" for i in range(4000)]
            out = refresh_market_cap_tiers(merge_cache=True)
            self.assertEqual(out["universe_size"], 4000)
            self.assertEqual(out["top50_target"], 2000)
            self.assertGreaterEqual(len(out["top50pct"]), 2000)


class TestAIRegistry(unittest.TestCase):
    def test_multi_industry_normalize(self):
        from analytics.industries.ai_registry import normalize_industries, upsert_ai_classification

        norm = normalize_industries(
            [
                {"industry_id": "semiconductors", "weight": 0.6, "role": "primary"},
                {"industry_id": "auto_manufacturers", "weight": 0.4, "role": "secondary"},
            ]
        )
        self.assertEqual(len(norm), 2)
        self.assertAlmostEqual(sum(x["weight"] for x in norm), 1.0, places=2)

        row = upsert_ai_classification(
            "TSLA",
            industries=norm,
            source="test",
            confidence=0.88,
            persist=False,
        )
        self.assertEqual(row["primary_industry_id"], "semiconductors")

    def test_merge_ai_into_row(self):
        from analytics.industries.ai_registry import merge_ai_into_industry_row, upsert_ai_classification

        upsert_ai_classification(
            "AMZN",
            industries=[
                {"industry_id": "interactive_media", "weight": 0.45},
                {"industry_id": "application_software", "weight": 0.35},
                {"industry_id": "air_freight_logistics", "weight": 0.2},
            ],
            confidence=0.91,
            persist=False,
        )
        base = {"symbol": "AMZN", "industry_id": "unclassified", "confidence": 0.1}
        merged = merge_ai_into_industry_row("AMZN", base)
        self.assertEqual(merged["industry_id"], "interactive_media")
        self.assertEqual(len(merged.get("industries") or []), 3)


class TestIntegration(unittest.TestCase):
    def test_get_industry_profile(self):
        from analytics.industries.integration import get_industry_profile

        prof = get_industry_profile("NVDA", use_ai=False)
        self.assertIn(prof.get("primary_industry_id"), ("semiconductors", "unclassified"))


if __name__ == "__main__":
    unittest.main()
