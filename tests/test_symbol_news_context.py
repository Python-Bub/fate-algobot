import unittest

from intel.news_sentiment_lexicon import classify_headline
from intel.symbol_news_context import (
    headline_relevant,
    is_ambiguous_ticker,
    newsapi_search_query,
)


class TestSymbolNewsContext(unittest.TestCase):
    def test_meta_is_ambiguous(self):
        self.assertTrue(is_ambiguous_ticker("META"))

    def test_nvda_not_ambiguous(self):
        self.assertFalse(is_ambiguous_ticker("NVDA"))

    def test_crash_headline(self):
        c = classify_headline("Shares crash on weak guidance")
        self.assertEqual(c.label, "bearish")

    def test_newsapi_query_uses_company_not_hardcoded_meta(self):
        q = newsapi_search_query("META")
        self.assertNotEqual(q.strip(), "META")
        self.assertIn("stock", q.lower())

    def test_headline_relevant_requires_company_or_ticker(self):
        self.assertFalse(headline_relevant("META", "The metadata field was updated"))
        self.assertTrue(headline_relevant("META", "Meta Platforms stock drops 5%"))


if __name__ == "__main__":
    unittest.main()
