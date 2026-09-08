"""Hedge fund multi-strategy stack."""
from __future__ import annotations

import os
import unittest

import numpy as np
import pandas as pd


class TestHedgeFundStack(unittest.TestCase):
    def setUp(self):
        os.environ["USE_HEDGE_FUND_STACK"] = "true"

    def test_factor_momentum_positive_on_uptrend(self):
        from analytics.hedge_fund_stack import factor_scores_from_row

        row = {"momentum_5d": 0.05, "rs_spy": 1.08}
        f = factor_scores_from_row(row)
        self.assertGreater(f["momentum"], 0.2)

    def test_stat_arb_cheap_vs_pair(self):
        from analytics.hedge_fund_stack import stat_arb_pair_signal

        idx = pd.date_range("2024-01-01", periods=120, freq="D")
        b = pd.Series(np.linspace(100, 120, 120), index=idx)
        a = b.copy()
        a.iloc[-20:] *= 0.90
        sig, z, peer = stat_arb_pair_signal(
            "KO",
            a,
            pair_closes_loader=lambda _: b,
        )
        self.assertIsNotNone(z)
        self.assertLess(z, 0.0)
        self.assertGreater(sig, 0.0)

    def test_etf_dislocation_nonzero(self):
        from analytics.hedge_fund_stack import etf_dislocation_score

        idx = pd.date_range("2024-01-01", periods=90, freq="D")
        bench = pd.Series(np.linspace(100, 120, 90), index=idx)
        etf = bench.copy()
        etf.iloc[-8:] *= 0.94
        score = etf_dislocation_score("QQQ", etf, bench)
        self.assertNotEqual(score, 0.0)

    def test_composite_boost_nonzero(self):
        from analytics.hedge_fund_stack import hedge_fund_rank_boost

        idx = pd.date_range("2024-01-01", periods=90, freq="D")
        closes = pd.Series(np.linspace(50, 55, 90), index=idx)
        row = {"rsi": 48, "rs_spy": 1.05, "volume_ratio": 1.8, "volatility": 0.02}
        hf = hedge_fund_rank_boost("SPY", row=row, closes=closes, bench_closes=closes)
        self.assertNotEqual(hf.boost, 0.0)

    def test_portfolio_risk_scales_down(self):
        from analytics.hedge_fund_stack import portfolio_risk_overlay

        pos = [{"symbol": "AAPL", "market_value": 50_000}]
        ro = portfolio_risk_overlay(pos, 100_000.0)
        self.assertLessEqual(ro["scale"], 1.0)
        self.assertTrue(ro["ok"])


if __name__ == "__main__":
    unittest.main()
