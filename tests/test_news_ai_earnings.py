"""Tests for earnings calendar + news AI agent good/bad separation."""
from __future__ import annotations

import unittest
from datetime import date, timedelta
from unittest.mock import patch

from intel.news_sentiment_lexicon import classify_headline


class TestEarningsCalendar(unittest.TestCase):
    def setUp(self):
        from intel import earnings_calendar as ec

        ec._EARN_CACHE.clear()
        ec._EMPTY_CACHE.clear()
        ec._SNAP_CACHE.clear()
        ec._BATCH_INDEX = None
        ec._BATCH_REFRESHING = False

    def test_snapshot_days_to_next(self):
        from intel import earnings_calendar as ec

        today = date(2026, 6, 1)
        nxt = today + timedelta(days=9)
        with patch.object(ec, "load_all_earnings_dates", return_value=[today - timedelta(days=80), nxt]):
            snap = ec.earnings_snapshot("ORCL", as_of=today, force_refresh=True)
        self.assertEqual(snap["days_to_earnings"], 9)
        self.assertEqual(snap["next_earnings_date"], nxt.isoformat())

    def test_load_merges_sources(self):
        from intel import earnings_calendar as ec
        from unittest.mock import patch

        d1 = date(2026, 3, 1)
        d2 = date(2026, 6, 10)
        with patch.object(ec, "_disk_dates", return_value=[d1]), patch.object(
            ec, "_finnhub_batch_dates", return_value=[d2]
        ), patch.object(ec, "_yfinance_earnings_dates") as yf_mock:
            out = ec.load_all_earnings_dates("ORCL", force_refresh=True)
        yf_mock.assert_not_called()
        self.assertEqual(out, [d1, d2])

    def test_yfinance_used_when_finnhub_empty(self):
        from intel import earnings_calendar as ec

        d1 = date(2026, 7, 1)
        with patch.object(ec, "_disk_dates", return_value=[]), patch.object(
            ec, "_finnhub_batch_dates", return_value=[]
        ), patch.object(ec, "_finnhub_budget_ok", return_value=(False, "finnhub_earnings")), patch.object(
            ec, "_yfinance_earnings_dates", return_value=[d1]
        ) as yf_mock:
            out = ec.load_all_earnings_dates("ORCL", force_refresh=True)
        yf_mock.assert_called_once()
        self.assertEqual(out, [d1])

    def test_batch_index_used_without_per_symbol(self):
        from intel import earnings_calendar as ec

        nxt = date(2026, 8, 12)
        with patch.object(ec, "_disk_dates", return_value=[]), patch.object(
            ec, "_finnhub_batch_dates", return_value=[nxt]
        ), patch.object(ec, "_finnhub_earnings_dates") as per_sym, patch.object(
            ec, "_yfinance_earnings_dates", return_value=[]
        ):
            out = ec.load_all_earnings_dates("AIXC", force_refresh=True)
        per_sym.assert_not_called()
        self.assertEqual(out, [nxt])

    def test_empty_not_cached_when_budget_blocked(self):
        from intel import earnings_calendar as ec

        with patch.object(ec, "_disk_dates", return_value=[]), patch.object(
            ec, "_finnhub_batch_dates", return_value=[]
        ), patch.object(ec, "_finnhub_budget_ok", return_value=(False, "finnhub_earnings")), patch.object(
            ec, "_yfinance_earnings_dates", return_value=[]
        ):
            first = ec.load_all_earnings_dates("ZZZZ", force_refresh=True)
            self.assertEqual(first, [])
            self.assertNotIn("ZZZZ", ec._EMPTY_CACHE)

    def test_empty_results_not_cached_long(self):
        from intel import earnings_calendar as ec

        with patch.object(ec, "_disk_dates", return_value=[]), patch.object(
            ec, "_finnhub_batch_dates", return_value=[]
        ), patch.object(ec, "_yfinance_earnings_dates", return_value=[]), patch.object(
            ec, "_finnhub_earnings_dates", return_value=[]
        ), patch.object(ec, "_finnhub_stock_earnings_dates", return_value=[]):
            first = ec.load_all_earnings_dates("ZZZZ", force_refresh=True)
            self.assertEqual(first, [])
            with patch.object(ec, "_yfinance_earnings_dates", return_value=[date(2026, 7, 1)]):
                second = ec.load_all_earnings_dates("ZZZZ", force_refresh=True)
            self.assertEqual(second, [date(2026, 7, 1)])

    def test_projects_next_from_history(self):
        from intel import earnings_calendar as ec

        today = date(2026, 6, 1)
        past = [today - timedelta(days=95), today - timedelta(days=186), today - timedelta(days=277)]
        with patch.object(ec, "load_all_earnings_dates", return_value=past):
            snap = ec.earnings_snapshot("LOW", as_of=today, force_refresh=True)
        self.assertTrue(snap.get("estimated_next"))
        self.assertIsNotNone(snap.get("days_to_earnings"))
        self.assertGreater(snap["days_to_earnings"], 0)


class TestNewsAIAgent(unittest.TestCase):
    def setUp(self):
        from intel import news_ai_agent as na

        na._INTEL_CACHE.clear()

    def test_lexicon_separates_good_bad_phrases(self):
        bull = classify_headline("Company beats estimates and raises full-year guidance")
        bear = classify_headline("Stock plunges after earnings miss and guidance cut")
        self.assertEqual(bull.label, "bullish")
        self.assertEqual(bear.label, "bearish")
        self.assertGreater(bull.score, bear.score)

    def test_analyze_blocks_bad_narrative(self):
        from intel import news_ai_agent as na
        from intel.news_digest import NewsDigest

        digest = NewsDigest(
            symbol="MSFT",
            composite_score=-0.4,
            verdict="bearish",
            bullish_count=0,
            bearish_count=3,
            neutral_count=1,
            finnhub_count=2,
            newsapi_count=2,
            cramer_count=0,
            finnhub_buzz_score=None,
            finnhub_bull_pct=None,
            finnhub_bear_pct=None,
            top_bullish=[],
            top_bearish=["Guidance cut", "Downgrade to sell"],
            llm_thesis="",
            block_long=True,
            generated_at_utc="2026-06-01T00:00:00+00:00",
        )
        with patch("intel.news_digest.build_news_digest", return_value=digest):
            with patch.object(na, "_enabled", return_value=False):
                with patch(
                    "intel.earnings_calendar.earnings_snapshot",
                    return_value={"days_to_earnings": 12, "in_earnings_window": False},
                ):
                    with patch(
                        "intel.earnings_calendar.earnings_context_text",
                        return_value="Next earnings in 12 days",
                    ):
                        out = na.analyze_symbol_news("MSFT", force_refresh=True)
        self.assertTrue(out["block_long"] or out["bad_news_score"] > out["good_news_score"])

    def test_score_adjustments_good_vs_bad(self):
        from intel.news_ai_agent import score_adjustments

        os.environ["USE_NEWS_AI_AGENT"] = "true"
        good_p, good_s = score_adjustments(
            {"boost_long": True, "good_news_score": 0.7, "bad_news_score": 0.1, "narrative": "good_news"}
        )
        bad_p, bad_s = score_adjustments(
            {"block_long": True, "good_news_score": 0.1, "bad_news_score": 0.8, "narrative": "bad_news"}
        )
        self.assertGreater(good_s, bad_s)
        self.assertGreater(good_p, bad_p)


if __name__ == "__main__":
    unittest.main()
