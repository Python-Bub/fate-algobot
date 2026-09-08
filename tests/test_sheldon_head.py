"""Sheldon EV head — whole-book hunt, no alphabet walk."""
import os
import unittest


class TestSheldonHead(unittest.TestCase):
    def test_ev_positive_on_edge_and_mos(self):
        from analytics.sheldon_head import _ev

        weak = _ev(0.51, 0.0, 0.0, 0.0)
        strong = _ev(0.62, 0.16, 0.10, 0.05)
        self.assertGreater(strong, weak)
        self.assertGreater(strong, 0.0)

    def test_international_primaries_cover_adrs(self):
        from analytics.sheldon_head import international_primaries

        intl = set(international_primaries())
        for s in ("TSM", "BABA", "ASML", "NVO", "SHEL"):
            self.assertIn(s, intl)

    def test_hunt_rewrites_board(self):
        os.environ["SHELDON_TOP_N"] = "12"
        os.environ["SHELDON_HOT_N"] = "6"
        from analytics.sheldon_head import hunt, sheldon_rank_boost, sheldon_priority_tickers

        payload = hunt(symbols=["AAPL", "MSFT", "TSM", "BABA", "ZZZZ"], top_n=8)
        self.assertGreaterEqual(int(payload.get("scanned") or 0), 3)
        self.assertTrue(payload.get("hot"))
        pri = sheldon_priority_tickers(limit=20)
        self.assertTrue(pri)
        boost, meta = sheldon_rank_boost(payload["hot"][0])
        self.assertGreaterEqual(boost, 0.0)
        self.assertEqual(meta.get("head"), "sheldon")


if __name__ == "__main__":
    unittest.main()
