import os
import unittest
from unittest.mock import patch

from analytics.after_hours_intel import ah_rank_boost, fetch_after_hours_snapshot


class TestAfterHoursIntel(unittest.TestCase):
    def test_neutral_when_disabled(self):
        os.environ["USE_AFTER_HOURS"] = "false"
        snap = fetch_after_hours_snapshot("AAPL", force=False)
        self.assertFalse(snap["ok"])

    @patch("yfinance.Ticker")
    def test_post_market_bullish(self, mock_ticker):
        os.environ["USE_AFTER_HOURS"] = "true"
        mock_ticker.return_value.info = {
            "regularMarketPreviousClose": 100.0,
            "postMarketPrice": 102.0,
            "postMarketChangePercent": 2.0,
        }
        snap = fetch_after_hours_snapshot("TEST", force=True)
        self.assertTrue(snap["ok"])
        self.assertGreater(snap["ah_tilt"], 0.0)
        self.assertGreater(ah_rank_boost(snap), 0.0)


if __name__ == "__main__":
    unittest.main()
