import unittest

from intel.news_sentiment_lexicon import classify_headline


class TestNewsSentimentLexicon(unittest.TestCase):
    def test_crash_headline_bearish(self):
        c = classify_headline("Meta stock crashing on AI spending fears as shares plunge 8%")
        self.assertEqual(c.label, "bearish")
        self.assertLess(c.score, -0.3)

    def test_beat_headline_bullish(self):
        c = classify_headline("Meta beats estimates, raises guidance on strong ad revenue")
        self.assertEqual(c.label, "bullish")
        self.assertGreater(c.score, 0.3)

    def test_neutral_headline(self):
        c = classify_headline("Meta to report earnings next week")
        self.assertEqual(c.label, "neutral")


if __name__ == "__main__":
    unittest.main()
