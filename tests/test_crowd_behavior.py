import os
import unittest

from analytics.crowd_behavior import (
    analyze_crowd_behavior,
    apply_investor_context,
    block_long_on_crowd_euphoria,
    counterparty_adjustment,
    crowd_rank_boost,
)


class TestCrowdBehavior(unittest.TestCase):
    def test_euphoric_crowd_detected(self):
        c = analyze_crowd_behavior(
            "GME",
            news_sentiment=0.6,
            news_factor=0.5,
            social_score=0.7,
            social_bull_share=0.85,
            volume_ratio=2.5,
            vix=14.0,
        )
        self.assertGreater(c["crowd_pressure"], 0.35)
        self.assertIn(c["expected_crowd_action"], ("BUY", "LEAN_BUY"))

    def test_fearful_crowd_detected(self):
        c = analyze_crowd_behavior(
            "SPY",
            news_sentiment=-0.5,
            news_factor=-0.4,
            social_score=-0.6,
            social_bull_share=0.2,
            volume_ratio=1.8,
            vix=35.0,
        )
        self.assertLess(c["crowd_pressure"], -0.2)
        self.assertIn(c["expected_crowd_action"], ("SELL", "LEAN_SELL"))

    def test_contrarian_fades_euphoria(self):
        os.environ["USE_CROWD_BEHAVIOR"] = "true"
        os.environ["CROWD_ADJUST_MODE"] = "contrarian_long"
        out = apply_investor_context(
            0.62,
            0.70,
            symbol="NVDA",
            news_sentiment=0.55,
            news_factor=0.4,
            social_score=0.6,
            social_bull_share=0.8,
            volume_ratio=2.0,
            vix=13.0,
            fetch_after_hours=False,
            ah_snapshot={"ok": True, "ah_tilt": 0.35, "ah_return_pct": 0.02, "session": "post_market"},
        )
        self.assertLess(out["p_up"], out["p_up_before"])
        self.assertGreaterEqual(out["min_exec_effective"], out["min_exec_base"])

    def test_contrarian_boosts_fearful_dip_when_model_bullish(self):
        os.environ["CROWD_ADJUST_MODE"] = "contrarian_long"
        out = apply_investor_context(
            0.58,
            0.66,
            symbol="AAPL",
            news_sentiment=-0.4,
            social_score=-0.5,
            social_bull_share=0.25,
            volume_ratio=1.5,
            vix=32.0,
        )
        self.assertGreaterEqual(out["p_up"], out["p_up_before"])

    def test_momentum_follows_crowd(self):
        os.environ["CROWD_ADJUST_MODE"] = "momentum"
        out = apply_investor_context(
            0.55,
            0.65,
            symbol="TSLA",
            news_sentiment=0.5,
            social_score=0.5,
            social_bull_share=0.75,
            volume_ratio=2.0,
            vix=15.0,
        )
        self.assertGreater(out["p_up"], out["p_up_before"])

    def test_fomo_block_threshold(self):
        c = analyze_crowd_behavior(
            "MEME",
            news_sentiment=0.8,
            news_factor=0.7,
            social_score=0.9,
            social_bull_share=0.9,
            volume_ratio=3.0,
            vix=12.0,
        )
        os.environ["CROWD_BLOCK_FOMO"] = "true"
        os.environ["CROWD_EUPHORIA_BLOCK"] = "0.5"
        self.assertTrue(block_long_on_crowd_euphoria(c))

    def test_rank_boost_contrarian_negative_on_euphoria(self):
        os.environ["CROWD_ADJUST_MODE"] = "contrarian_long"
        c = analyze_crowd_behavior("X", news_sentiment=0.7, social_score=0.6, social_bull_share=0.8, vix=13.0)
        self.assertLess(crowd_rank_boost(c), 0.0)


    def test_counterparty_motivated_seller_on_fear(self):
        p2, _, diag = counterparty_adjustment(
            intended_side="buy",
            p_up=0.58,
            exec_conf=0.66,
            crowd_pressure=-0.5,
            ah_tilt=-0.3,
        )
        self.assertGreater(p2, 0.58)
        self.assertIn("motivated seller", diag["counterparty_read"])

    def test_ah_blends_into_crowd(self):
        c = analyze_crowd_behavior("X", ah_tilt=0.4, vix=14.0)
        self.assertGreater(c["crowd_pressure"], 0.1)


if __name__ == "__main__":
    unittest.main()
