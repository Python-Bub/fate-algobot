"""Trade rotation cooldown."""
import os
import tempfile
import unittest
from pathlib import Path


class TestTradeRotation(unittest.TestCase):
    def setUp(self):
        os.environ["USE_TRADE_ROTATION"] = "true"
        os.environ["TRADE_COOLDOWN_HOURS"] = "48"
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["RECENT_TRADES_FILE"] = str(Path(self._tmp.name) / "recent.json")
        os.environ["LAST_PICKS_FILE"] = str(Path(self._tmp.name) / "picks.json")

    def tearDown(self):
        self._tmp.cleanup()

    def test_cooldown_blocks_repeat(self):
        from analytics.trade_rotation import in_cooldown, recent_symbols, record_trade

        record_trade("NVDA", source="fortress")
        self.assertIn("NVDA", recent_symbols())
        self.assertTrue(in_cooldown("NVDA"))
        record_trade("AMD", source="hft")
        self.assertFalse(in_cooldown("AMD", for_engine="fortress"))

    def test_penalty_reduces_score(self):
        from analytics.trade_rotation import apply_score_penalty, record_trade

        record_trade("MSFT", source="fortress")
        self.assertLess(apply_score_penalty("MSFT", 1.0), 0.5)
        self.assertEqual(apply_score_penalty("GOOG", 1.0), 1.0)

    def test_letter_diversify_caps_a_cluster(self):
        os.environ["TRADE_LETTER_DIVERSIFY"] = "true"
        os.environ["TRADE_MAX_BUYS_PER_LETTER"] = "1"
        from analytics.trade_rotation import select_diversified_buys

        cands = [
            {"ticker": "AAPL", "score": 0.95},
            {"ticker": "AMZN", "score": 0.94},
            {"ticker": "MSFT", "score": 0.93},
            {"ticker": "NVDA", "score": 0.92},
        ]
        picks = select_diversified_buys(cands, 3)
        letters = [p["ticker"][0] for p in picks]
        self.assertEqual(letters.count("A"), 1)
        self.assertIn("MSFT", [p["ticker"] for p in picks])


if __name__ == "__main__":
    unittest.main()
