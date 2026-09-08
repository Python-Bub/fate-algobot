import unittest
import numpy as np
import pandas as pd

from analytics.feature_families import enrich_advanced_features, advanced_feature_columns
from analytics.meta_stack import train_meta_stack, apply_meta_stack


class TestAnalyticsStack(unittest.TestCase):
    def setUp(self):
        np.random.seed(7)
        idx = pd.date_range("2022-01-01", periods=500, freq="D")
        close = 100 + np.cumsum(np.random.normal(0, 1.2, size=len(idx)))
        self.df = pd.DataFrame(
            {
                "Open": close + np.random.normal(0, 0.3, size=len(idx)),
                "High": close + np.abs(np.random.normal(1, 0.4, size=len(idx))),
                "Low": close - np.abs(np.random.normal(1, 0.4, size=len(idx))),
                "Close": close,
                "Volume": np.random.randint(5000, 120000, size=len(idx)),
            },
            index=idx,
        )
        self.df["Adj Close"] = self.df["Close"]
        self.df["returns"] = self.df["Adj Close"].pct_change().fillna(0)
        self.df["sentiment"] = np.random.normal(0, 0.2, size=len(idx))
        self.df["days_to_earnings"] = np.random.randint(-30, 30, size=len(idx))
        self.df["target"] = (self.df["returns"].shift(-1) > 0).astype(int)

    def test_advanced_features_exist(self):
        out = enrich_advanced_features(self.df)
        for c in advanced_feature_columns():
            self.assertIn(c, out.columns)

    def test_meta_stack_train_and_infer(self):
        out = enrich_advanced_features(self.df)
        out["p_short"] = np.clip(0.5 + out["returns"] * 3, 0.01, 0.99)
        out["p_long"] = np.clip(0.5 + out["mom_20"] * 2, 0.01, 0.99)
        model, res = train_meta_stack(out, target_col="target")
        self.assertGreater(res.rows, 100)
        p = apply_meta_stack(model, out.iloc[-1])
        self.assertGreaterEqual(p, 0.0)
        self.assertLessEqual(p, 1.0)


if __name__ == "__main__":
    unittest.main()

