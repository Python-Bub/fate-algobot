import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ET = ZoneInfo("America/New_York")

_SEEN: dict = {}


class _RecorderHead:
    def predict_proba(self, x):
        _SEEN["cols"] = list(x.columns)
        _SEEN["nan"] = bool(x.isna().any().any())
        return np.array([[0.3, 0.7]])


class TestCompletedDailyBar(unittest.TestCase):
    def _today_df(self):
        return pd.DataFrame(
            {"Close": [10.0, 11.0, 12.0], "Volume": [1e6, 1e6, 1e6]},
            index=pd.DatetimeIndex(
                [
                    datetime(2026, 8, 14, tzinfo=ET),
                    datetime(2026, 8, 17, tzinfo=ET),
                    datetime(2026, 8, 18, tzinfo=ET),
                ]
            ),
        )

    def test_rth_uses_prior_session(self):
        from analytics.completed_bar import completed_daily_signal_row

        now = datetime(2026, 8, 18, 11, 0, tzinfo=ET)
        row, px = completed_daily_signal_row(self._today_df(), now=now)
        self.assertEqual(float(row["Close"]), 11.0)
        self.assertEqual(px, 12.0)

    def test_after_close_uses_last_bar(self):
        from analytics.completed_bar import completed_daily_signal_row

        now = datetime(2026, 8, 18, 16, 10, tzinfo=ET)
        row, px = completed_daily_signal_row(self._today_df(), now=now)
        self.assertEqual(float(row["Close"]), 12.0)
        self.assertEqual(px, 12.0)

    def test_opt_in_incomplete(self):
        from analytics.completed_bar import completed_daily_signal_row

        os.environ["FORTRESS_PREDICT_INCOMPLETE_BAR"] = "true"
        try:
            now = datetime(2026, 8, 18, 11, 0, tzinfo=ET)
            row, px = completed_daily_signal_row(self._today_df(), now=now)
            self.assertEqual(float(row["Close"]), 12.0)
            self.assertEqual(px, 12.0)
        finally:
            os.environ.pop("FORTRESS_PREDICT_INCOMPLETE_BAR", None)


class TestIntradayLiveBlend(unittest.TestCase):
    def test_blend_none_is_passthrough(self):
        from intraday.live_infer import blend_intraday_p

        p, w = blend_intraday_p(0.7, None)
        self.assertEqual(p, 0.7)
        self.assertEqual(w, 0.0)

    def test_blend_small_weight(self):
        from intraday.live_infer import blend_intraday_p

        os.environ["INTRADAY_LIVE_BLEND_W"] = "0.12"
        os.environ.pop("INTRADAY_DISAGREE_DAMPEN", None)
        os.environ.pop("INTRADAY_OPPOSE_MULT", None)
        p, w = blend_intraday_p(0.60, 0.80)
        self.assertAlmostEqual(w, 0.12)
        self.assertAlmostEqual(p, 0.60 * 0.88 + 0.80 * 0.12)

    def test_placeholder_skipped(self):
        import joblib
        from intraday import intraday_trainer as m
        from intraday.intraday_trainer import predict_intraday

        tmp = Path(tempfile.mkdtemp())
        joblib.dump({"placeholder": True}, tmp / "AAA_intraday.pkl")
        old = m.MODEL_DIR
        m.MODEL_DIR = tmp
        try:
            out = predict_intraday("AAA", pd.Series({"rsi_14": 50.0}))
        finally:
            m.MODEL_DIR = old
        self.assertTrue(out.get("placeholder"))
        self.assertTrue(out.get("missing"))
        self.assertEqual(out["p_up"], 0.5)

    def test_missing_feature_cols_fill_zero(self):
        import joblib
        from intraday import intraday_trainer as m
        from intraday.intraday_trainer import predict_intraday

        tmp = Path(tempfile.mkdtemp())
        joblib.dump(
            {"placeholder": False, "features": ["ret_1", "ret_3", "rsi_14"], "model_minutely": _RecorderHead()},
            tmp / "AAA_intraday.pkl",
        )
        old = m.MODEL_DIR
        m.MODEL_DIR = tmp
        _SEEN.clear()
        try:
            out = predict_intraday("AAA", pd.Series({"ret_1": 0.01}))
        finally:
            m.MODEL_DIR = old
        self.assertFalse(out.get("missing"))
        self.assertAlmostEqual(out["p_up"], 0.7)
        self.assertEqual(_SEEN.get("cols"), ["ret_1", "ret_3", "rsi_14"])
        self.assertFalse(_SEEN.get("nan"))


class TestTop100QualityEnv(unittest.TestCase):
    def test_perfection_does_not_hardcode_fast_train(self):
        src = Path("tools/train_top100_perfect.py").read_text(encoding="utf-8")
        self.assertNotIn('"FAST_UNIVERSE_TRAIN": "true"', src)
        self.assertIn("TOP100_FAST_UNIVERSE_TRAIN", src)


class TestVwapNoFutureFill(unittest.TestCase):
    def test_early_vwap_uses_own_close(self):
        from analytics.classic_quant_features import add_vwap_proxy

        df = pd.DataFrame({"Close": [10.0, 11.0, 12.0, 13.0, 14.0], "Volume": [1.0] * 5})
        out = add_vwap_proxy(df, window=20)
        self.assertEqual(float(out["vwap_20"].iloc[0]), 10.0)


if __name__ == "__main__":
    unittest.main()
