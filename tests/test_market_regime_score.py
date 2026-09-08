import unittest

from analytics.market_regime_score import analyze_bull_bear_market, apply_bull_bear_to_p_up
from regime_detector import Regime, RegimeState


class TestMarketRegimeScore(unittest.TestCase):
    def test_bull_label(self):
        st = RegimeState(Regime.BULL_TREND, 16.0, 1.0, 1.0)
        bb = analyze_bull_bear_market(st, {"macro_score": 0.3}, hmm_market_score=0.2)
        self.assertEqual(bb["bull_bear_label"], "BULL")
        p1, d = apply_bull_bear_to_p_up(0.55, bb)
        self.assertGreater(p1, 0.55)

    def test_bear_label(self):
        st = RegimeState(Regime.BEAR_TREND, 32.0, 0.5, 1.5)
        bb = analyze_bull_bear_market(st, {"macro_score": -0.4}, hmm_market_score=-0.2)
        self.assertEqual(bb["bull_bear_label"], "BEAR")
        p1, d = apply_bull_bear_to_p_up(0.55, bb)
        self.assertLess(p1, 0.55)


if __name__ == "__main__":
    unittest.main()
