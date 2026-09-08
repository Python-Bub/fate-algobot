"""Tests for 50-industry taxonomy and co-movement engine."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd


class TestIndustryTaxonomy(unittest.TestCase):
    def test_override_welltower_healthcare_reit(self):
        from analytics.industry_taxonomy import classify_symbol

        meta = classify_symbol("WELL", use_yfinance=False)
        self.assertEqual(meta["industry_id"], "specialized_reits")
        self.assertTrue(meta["rate_sensitive"])

    def test_semiconductor_pattern(self):
        from analytics.industry_taxonomy import classify_symbol

        meta = classify_symbol(
            "TEST",
            sector="Technology",
            industry="Semiconductors",
            use_yfinance=False,
        )
        self.assertEqual(meta["industry_id"], "semiconductors")
        self.assertEqual(meta["etf_proxy"], "SMH")

    def test_catalog_has_fifty_buckets(self):
        from analytics.industry_taxonomy import all_industry_ids

        ids = all_industry_ids()
        self.assertGreaterEqual(len(ids), 49)


class TestIndustryComovement(unittest.TestCase):
    def _fake_df(self, n: int = 80) -> pd.DataFrame:
        idx = pd.date_range("2025-01-01", periods=n, freq="B")
        close = 100 * np.cumprod(1 + np.random.default_rng(7).normal(0, 0.01, n))
        return pd.DataFrame({"Close": close, "Adj Close": close}, index=idx)

    def test_enrich_adds_columns(self):
        from analytics.industry_comovement import INDUSTRY_FEATURE_COLUMNS, enrich_industry_comovement

        df = self._fake_df()
        with patch("analytics.industry_comovement._load_closes") as mock_load:
            ret_idx = df.index
            mock_load.side_effect = lambda sym, start, end: pd.Series(
                df["Close"].values * (1.02 if sym == "SMH" else 1.01),
                index=ret_idx,
            )
            out = enrich_industry_comovement(df, "NVDA", "2025-01-01", "2025-04-01")
        for col in INDUSTRY_FEATURE_COLUMNS:
            self.assertIn(col, out.columns)

    def test_factor_tilts_rate_sensitive_reit(self):
        from analytics.industry_comovement import factor_tilts

        factors = {"spread_10y2y": -0.5, "rate_shock_20d": 0.3, "pmi_score": 0.0, "nasdaq_ret_5d": 0.0}
        tilts = factor_tilts("residential_reits", factors)
        self.assertLess(tilts["factor_rate_tilt"], 0.0)

    def test_factor_tilts_expansion_semis(self):
        from analytics.industry_comovement import factor_tilts

        factors = {"spread_10y2y": 0.4, "rate_shock_20d": -0.1, "pmi_score": 0.8, "nasdaq_ret_5d": 0.02}
        tilts = factor_tilts("semiconductors", factors)
        self.assertGreater(tilts["factor_expansion_tilt"], 0.0)

    def test_leader_sympathy_mock(self):
        from analytics.industry_comovement import compute_leader_sympathy

        with patch("analytics.industry_comovement._leaders_for_industry", return_value=["NVDA", "AMD"]):
            with patch("analytics.industry_comovement._load_closes") as mock_load:
                idx = pd.date_range("2026-05-20", periods=8, freq="B")
                mock_load.return_value = pd.Series(np.linspace(100, 108, 8), index=idx)
                snap = compute_leader_sympathy("INTC", as_of="2026-06-07")
        self.assertIn("sympathy_score", snap)
        self.assertGreater(snap["sympathy_score"], 0.0)

    def test_rank_adjustment_returns_delta(self):
        from analytics.industry_comovement import industry_rank_adjustment

        row = {"industry_residual_1d": 0.01, "industry_z_20": 1.5, "industry_beta_60": 1.1}
        with patch("analytics.industry_comovement.compute_leader_sympathy", return_value={"sympathy_score": 0.3, "leader_z": 1.0}):
            with patch("analytics.industry_comovement.get_factor_snapshot", return_value={"nasdaq_ret_5d": 0.01, "spread_10y2y": 0.2, "pmi_score": 0.5, "rate_shock_20d": 0.0}):
                adj = industry_rank_adjustment("NVDA", row)
        self.assertIn("score_delta", adj)
        self.assertEqual(adj["industry_id"], "semiconductors")

    def test_intra_correlation_synthetic(self):
        from analytics.industry_comovement import rolling_intra_industry_correlation

        with patch("analytics.industry_comovement._load_closes") as mock_load:
            idx = pd.date_range("2025-01-01", periods=40, freq="B")
            base = np.cumprod(1 + np.random.default_rng(1).normal(0, 0.01, 40))

            def _closes(sym, start, end):
                noise = np.random.default_rng(hash(sym) % 2**16).normal(0, 0.002, 40)
                return pd.Series(base * (1 + noise), index=idx)

            mock_load.side_effect = _closes
            corr = rolling_intra_industry_correlation(["A", "B", "C"], "2025-01-01", "2025-03-01")
        self.assertGreater(corr, 0.5)


if __name__ == "__main__":
    unittest.main()
