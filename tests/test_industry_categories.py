"""Tests for 50 user-facing category modules (marine_transportation.py, etc.)."""

from __future__ import annotations

import importlib
import unittest

from analytics.industries.categories import ALL_CATEGORIES, USER_CATEGORIES, get_category, list_category_slugs
from analytics.industries.categories._registry import INDUSTRY_TO_SLUG, SLUG_TO_INDUSTRY


class TestCategoryRegistry(unittest.TestCase):
    def test_fifty_slugs(self):
        slugs = list_category_slugs()
        self.assertEqual(len(slugs), 50)

    def test_marine_transportation_maps_to_marine_shipping(self):
        self.assertEqual(SLUG_TO_INDUSTRY["marine_transportation"], "marine_shipping")
        self.assertEqual(INDUSTRY_TO_SLUG["marine_shipping"], "marine_transportation")

    def test_every_slug_has_module_file(self):
        for _, slug, _, iid in USER_CATEGORIES:
            mod = importlib.import_module(f"analytics.industries.categories.{slug}")
            self.assertTrue(hasattr(mod, "CATEGORY"), slug)
            self.assertEqual(mod.INDUSTRY_ID, iid, slug)

    def test_get_category_by_slug_and_id(self):
        c1 = get_category("marine_transportation")
        c2 = get_category("marine_shipping")
        self.assertEqual(c1.CATEGORY_SLUG, "marine_transportation")
        self.assertEqual(c2.CATEGORY_SLUG, "marine_transportation")

    def test_all_categories_dict(self):
        self.assertGreaterEqual(len(ALL_CATEGORIES), 50)


class TestCategoryHighLevel(unittest.TestCase):
    def test_sample_categories_self_test(self):
        for slug in ("biotechnology", "semiconductors", "marine_transportation", "residential_reits"):
            cat = get_category(slug)
            rep = cat.high_level_test()
            self.assertEqual(rep.get("category_slug"), slug)
            self.assertTrue(rep.get("net_positive"), rep)

    def test_marine_transportation_number(self):
        cat = get_category("marine_transportation")
        self.assertEqual(cat.CATEGORY_NUMBER, 47)
        self.assertEqual(cat.DISPLAY_NAME, "Marine Transportation")
        self.assertGreaterEqual(len(cat.LEADER_TICKERS), 1)


if __name__ == "__main__":
    unittest.main()
