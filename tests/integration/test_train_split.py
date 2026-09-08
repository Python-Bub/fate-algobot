import os
import unittest

import numpy as np
import pandas as pd

from model_trainer import _chrono_split_xy, _train_val_matrix_split


class TestChronologicalTrainSplit(unittest.TestCase):
    def setUp(self):
        os.environ["TRAIN_TIME_ORDER_SPLIT"] = "true"
        os.environ["TRAIN_TEST_FRACTION"] = "0.2"
        os.environ.pop("TRAIN_EMBARGO_BARS", None)
        os.environ["TRAIN_EMBARGO_DEFAULT"] = "0"
        os.environ["TRAIN_EMBARGO_LONG"] = "20"
        os.environ["TRAIN_EMBARGO_XLONG"] = "60"

    def test_holdout_is_last_segment(self):
        idx = pd.date_range("2020-01-01", periods=100, freq="B")
        X = pd.DataFrame({"a": np.linspace(0, 1, len(idx))}, index=idx)
        y = pd.Series((X["a"] > 0.5).astype(int), index=idx)
        yl = y.copy()
        Xt, Xv, yt, yv, yltr, ylte = _train_val_matrix_split(X, y, yl, "ZZZ")
        self.assertLess(len(Xt), len(X))
        self.assertGreater(Xv.index[0], Xt.index[-1])
        pd.testing.assert_index_equal(yltr.index, Xt.index)
        pd.testing.assert_index_equal(ylte.index, Xv.index)

    def test_horizon_head_split_matches_main_semantics(self):
        """Untagged split stays ~80/20 (no embargo)."""
        idx = pd.date_range("2020-01-01", periods=100, freq="B")
        X = pd.DataFrame({"a": np.linspace(0, 1, len(idx))}, index=idx)
        y = pd.Series((X["a"] > 0.5).astype(int), index=idx)
        Xt, Xv, _, _ = _chrono_split_xy(X, y)
        self.assertGreaterEqual(len(Xt), 70)
        self.assertLessEqual(len(Xv), 30)

    def test_horizon_embargo_drops_label_overlap(self):
        idx = pd.date_range("2020-01-01", periods=200, freq="B")
        X = pd.DataFrame({"a": np.linspace(0, 1, len(idx))}, index=idx)
        y = pd.Series((X["a"] > 0.5).astype(int), index=idx)
        Xt, Xv, _, _ = _chrono_split_xy(X, y, ticker="ZZZ", tag="H60d")
        self.assertLess(len(Xt) + len(Xv), 200)
        self.assertGreater(Xv.index[0], Xt.index[-1])
        # ~60-bar embargo on business-day index → at least a month of calendar gap.
        self.assertGreaterEqual((Xv.index[0] - Xt.index[-1]).days, 40)

    def test_head_quality_gate(self):
        from model_trainer import _head_passes_quality, _stats_need_retrain

        os.environ["MIN_HEAD_TOP20"] = "0.45"
        os.environ["MIN_HEAD_ACC"] = "0.45"
        self.assertFalse(_head_passes_quality(0.32, 0.50))
        self.assertTrue(_head_passes_quality(0.52, 0.48))

        os.environ["RETRAIN_MIN_TOP20"] = "0.6"
        os.environ["AUTO_RETRAIN_LOW_TOP20"] = "true"
        os.environ.pop("_RETRAIN_LOW_TOP20", None)
        self.assertTrue(_stats_need_retrain({"short_top20": 0.55, "long_top20": 0.58}))
        self.assertFalse(_stats_need_retrain({"short_top20": 0.62, "long_top20": 0.65}))
        os.environ["_RETRAIN_LOW_TOP20"] = "1"
        self.assertFalse(_stats_need_retrain({"short_top20": 0.3}))


class TestTrainFeatureEnrich(unittest.TestCase):
    def test_enrich_adds_columns_without_network(self):
        os.environ["USE_TRAIN_SIGNAL_FEATURES"] = "true"
        os.environ["TRAIN_COMPUTE_UR"] = "false"
        os.environ["USE_TRAIN_NEWS_HISTORY"] = "false"
        os.environ.pop("FRED_API_KEY", None)
        from signals.train_feature_enrich import enrich_train_signals

        idx = pd.date_range("2024-01-01", periods=30, freq="B")
        df = pd.DataFrame(
            {
                "Open": np.linspace(100, 110, 30),
                "High": np.linspace(101, 111, 30),
                "Low": np.linspace(99, 109, 30),
                "Close": np.linspace(100.5, 110.5, 30),
                "Volume": np.full(30, 1e6),
            },
            index=idx,
        )
        out = enrich_train_signals(df, "2024-01-01", "2024-03-01", ticker="ZZZ")
        self.assertIn("ur_score", out.columns)
        self.assertIn("fred_spread_10y2y", out.columns)
        self.assertIn("news_sent_roll_5d", out.columns)
        self.assertTrue((out["ur_score"] == 0.0).all())


if __name__ == "__main__":
    unittest.main()
