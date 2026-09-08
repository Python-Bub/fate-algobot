import unittest
import numpy as np
import pandas as pd

from data_platform.data_quality import audit_ohlcv


class TestDataQuality(unittest.TestCase):
    def setUp(self):
        idx = pd.date_range("2024-01-01", periods=120, freq="D")
        close = 100 + np.cumsum(np.random.normal(0, 1, size=len(idx)))
        high = close + np.abs(np.random.normal(1, 0.3, size=len(idx)))
        low = close - np.abs(np.random.normal(1, 0.3, size=len(idx)))
        self.df = pd.DataFrame(
            {
                "Open": close + np.random.normal(0, 0.2, size=len(idx)),
                "High": high,
                "Low": low,
                "Close": close,
                "Volume": np.random.randint(1000, 100000, size=len(idx)),
            },
            index=idx,
        )

    def test_quality_ok(self):
        rep = audit_ohlcv(self.df)
        self.assertIn("ok", rep)
        self.assertIn("issues", rep)
        self.assertEqual(rep["rows"], len(self.df))

    def test_detect_bad_geometry(self):
        bad = self.df.copy()
        bad.loc[bad.index[5], "High"] = bad.loc[bad.index[5], "Low"] - 1.0
        rep = audit_ohlcv(bad)
        self.assertTrue(any(i["code"] == "high_below_low" for i in rep["issues"]))


if __name__ == "__main__":
    unittest.main()

