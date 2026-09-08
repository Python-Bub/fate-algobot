"""High-level tests for Luxury Goods enhancement module."""

from __future__ import annotations

import unittest

from analytics.industries.enhancements.luxury_goods import ENHANCEMENT
from analytics.industries.enhancements._base import ENHANCEMENT_FEATURES
from analytics.industries.base import IndustryContext
from analytics.industries.pipeline_models import IndustryPipelineResult
from analytics.industries.registry import get_handler


class TestLuxuryGoodsEnhancement(unittest.TestCase):
    INDUSTRY_ID = 'luxury_goods'

    def test_all_features_callable(self):
        for feat in ENHANCEMENT_FEATURES:
            self.assertTrue(callable(getattr(ENHANCEMENT, feat)), feat)

    def test_high_level_self_test(self):
        report = ENHANCEMENT.high_level_test()
        self.assertEqual(report['industry_id'], self.INDUSTRY_ID)
        self.assertEqual(report['features_implemented'], len(ENHANCEMENT_FEATURES))
        self.assertTrue(report['net_positive'], report)
        self.assertGreater(report['score_delta'], 0, report)
        self.assertGreaterEqual(report['feature_weight_count'], 3, report)

    def test_bullish_macro_enhances(self):
        handler = get_handler(self.INDUSTRY_ID)
        ctx = IndustryContext(
            symbol='LVMUY',
            market_cap=80e9,
            macro={'macro_score': 0.5, 'pmi_score': 0.7, 'nasdaq_ret_5d': 0.04, 'rate_shock_20d': -0.06, 'vix': 18, 'spread_10y2y': 0.2},
            row_features={'industry_z_20': 1.0, 'industry_ret_5d': 0.03, 'industry_beta_60': 1.05},
        )
        res = IndustryPipelineResult()
        ENHANCEMENT.enhance(res, ctx, handler)
        self.assertGreater(res.score_delta, 0.05)

    def test_bull_news_enhances(self):
        handler = get_handler(self.INDUSTRY_ID)
        ctx = IndustryContext(
            symbol='LVMUY',
            news_headlines=['china reopen', 'beats estimates raises guidance'],
            macro={'macro_score': 0.3, 'pmi_score': 0.5, 'vix': 18, 'nasdaq_ret_5d': 0.01, 'rate_shock_20d': 0},
        )
        res = IndustryPipelineResult()
        ENHANCEMENT.enhance(res, ctx, handler)
        self.assertGreater(res.score_delta, 0.03)
        self.assertGreater(res.p_up_delta, 0)

    def test_leader_premium(self):
        handler = get_handler(self.INDUSTRY_ID)
        ctx = IndustryContext(symbol='LVMUY', market_cap=200e9, macro={'macro_score': 0.2})
        res = IndustryPipelineResult()
        ENHANCEMENT.leader_ticker_premium(res, ctx, handler)
        self.assertGreater(res.score_delta, 0)

    def test_never_reduces_on_enhance_guard(self):
        handler = get_handler(self.INDUSTRY_ID)
        ctx = IndustryContext(symbol='ZZZZ', macro={'macro_score': -0.5, 'vix': 35})
        base = IndustryPipelineResult(score_delta=0.10)
        out = ENHANCEMENT.enhance(base, ctx, handler)
        self.assertGreaterEqual(out.score_delta, 0.10)


if __name__ == '__main__':
    unittest.main()
