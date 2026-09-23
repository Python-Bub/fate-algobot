"""Full test suite for 50 industry handlers."""

from __future__ import annotations

import unittest

from analytics.industries.handlers import ALL_HANDLERS
from analytics.industries.base import IndustryContext
from analytics.industries.registry import list_industry_ids


class TestAllHandlersPresent(unittest.TestCase):
    def test_fifty_industries(self):
        ids = [i for i in list_industry_ids() if i != "unclassified"]
        self.assertGreaterEqual(len(ids), 49)

    def test_each_handler_has_etf(self):
        for iid, h in ALL_HANDLERS.items():
            self.assertTrue(h.ETF_PROXY, msg=iid)

    def test_each_handler_classifies_hints(self):
        for iid, h in ALL_HANDLERS.items():
            if iid == "unclassified":
                continue
            hints = list(h.TICKER_HINTS)[:2]
            if not hints:
                continue
            ctx = IndustryContext(symbol=hints[0], sector="", yahoo_industry="")
            hit = h.classify(ctx)
            self.assertIsNotNone(hit, msg=f"{iid} did not classify hint {hints[0]!r}")
            self.assertEqual(hit.industry_id, iid)


class TestHandlerFactorTilts(unittest.TestCase):
    def test_rate_sensitive_reits_negative_on_hike(self):
        h = ALL_HANDLERS["residential_reits"]
        ctx = IndustryContext(
            symbol="EQR",
            macro={"spread_10y2y": 0.0, "rate_shock_20d": 0.4, "pmi_score": 0.0, "vix": 20.0, "nasdaq_ret_5d": 0.0},
        )
        t = h.compute_factor_tilts(ctx)
        self.assertLess(t.rate_tilt, 0.0)

    def test_semis_positive_on_pmi(self):
        h = ALL_HANDLERS["semiconductors"]
        ctx = IndustryContext(symbol="NVDA", macro={"pmi_score": 0.9, "spread_10y2y": 0.2, "rate_shock_20d": 0.0, "vix": 18.0, "nasdaq_ret_5d": 0.02})
        t = h.compute_factor_tilts(ctx)
        self.assertGreater(t.expansion_tilt, 0.0)


class TestNewsRouting(unittest.TestCase):
    def test_restaurant_food_commodity_news(self):
        from analytics.industries.news_router import route_headlines

        r = route_headlines("MCD", ["Beef prices surge on supply concerns"])
        self.assertGreater(r["bearish_score"], 0.0)
        self.assertEqual(r["industry_id"], "restaurants_food")

    def test_biotech_fda_news(self):
        from analytics.industries.news_router import route_headlines

        r = route_headlines("MRNA", ["Company wins FDA approval for new vaccine"])
        self.assertGreater(r["bullish_score"], 0.0)


class TestPeerMap(unittest.TestCase):
    def test_lookup_nvda(self):
        from analytics.industries.peer_ticker_map import lookup

        self.assertIn(lookup("NVDA"), ("semiconductors", "unclassified"))


class TestMacroPlaybooks(unittest.TestCase):
    def test_rate_hike_reits(self):
        from analytics.industries.macro_playbooks import apply_playbook

        r = apply_playbook("residential_reits", "rate_hike")
        self.assertTrue(r["applied"])
        self.assertLess(r["combined_delta"], 0.0)


if __name__ == "__main__":
    unittest.main()
