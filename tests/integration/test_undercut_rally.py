import os
import unittest

import numpy as np
import pandas as pd

from signals.undercut_rally import detect_undercut_rally
from dashboard.chart_data import (
    to_lightweight_candles,
    to_lightweight_line,
    to_lightweight_volume,
    ur_overlay_markers,
)


def _make_df(closes, lows=None, highs=None, opens=None, volumes=None):
    n = len(closes)
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    closes = np.array(closes, dtype=float)
    lows = np.array(lows if lows is not None else closes - 0.5, dtype=float)
    highs = np.array(highs if highs is not None else closes + 0.5, dtype=float)
    opens = np.array(opens if opens is not None else closes, dtype=float)
    volumes = np.array(
        volumes if volumes is not None else np.full(n, 1_000_000, dtype=float),
        dtype=float,
    )
    return pd.DataFrame(
        {"Open": opens, "High": highs, "Low": lows, "Close": closes, "Volume": volumes},
        index=idx,
    )


class TestUndercutRally(unittest.TestCase):
    def setUp(self):
        os.environ["UR_LOOKBACK"] = "20"
        os.environ["UR_MIN_PIVOT_AGE"] = "3"
        os.environ["UR_PIVOT_WINDOW"] = "5"
        os.environ["UR_VOL_EXPANSION"] = "1.3"
        os.environ["UR_REQUIRE_TREND"] = "false"

    def test_textbook_undercut_rally(self):
        # Ramp up to bar 30 (uptrend), pivot low around bar 25, then bar 35 undercuts and rallies.
        closes = list(np.linspace(100, 130, 25)) + [120, 122, 121, 119, 118] + [121, 124, 126, 125, 122] + [127]
        lows = [c - 1.0 for c in closes]
        highs = [c + 1.0 for c in closes]
        # Mark bar 28 as the swing low.
        lows[28] = 115.0
        # Today (last bar): undercut 115 and reclaim above it.
        lows[-1] = 113.0
        closes[-1] = 117.0
        highs[-1] = 118.5
        df = _make_df(closes, lows=lows, highs=highs, volumes=[1_000_000] * (len(closes) - 1) + [2_000_000])

        ur = detect_undercut_rally(df)
        self.assertTrue(ur.detected, msg=f"rationale={ur.rationale}")
        self.assertGreater(ur.score, 0.5)
        self.assertGreater(ur.undercut_depth_pct, 0.0)
        self.assertGreater(ur.reclaim_pct, 0.0)
        self.assertGreater(ur.volume_expansion, 1.0)

    def test_no_undercut_monotonic_uptrend(self):
        closes = list(np.linspace(100, 130, 40))
        df = _make_df(closes)
        ur = detect_undercut_rally(df)
        self.assertFalse(ur.detected)
        # A strict uptrend has no local swing-low pivot at all -> "no_pivot_window".
        # If we ever loosen the pivot definition, this should become "no_undercut".
        self.assertIn(ur.rationale, ("no_pivot_window", "no_undercut", "no_pivot_in_age_window"))

    def test_undercut_no_reclaim(self):
        closes = list(np.linspace(100, 130, 25)) + [120, 122, 121, 119, 118] + [121, 124, 126, 125, 122] + [110]
        lows = [c - 1.0 for c in closes]
        highs = [c + 1.0 for c in closes]
        lows[28] = 115.0
        lows[-1] = 109.0  # undercut
        closes[-1] = 110.0  # but did NOT reclaim 115
        df = _make_df(closes, lows=lows, highs=highs)
        ur = detect_undercut_rally(df)
        self.assertFalse(ur.detected)
        self.assertEqual(ur.rationale, "no_reclaim")

    def test_trend_required_invalidates(self):
        # Long downtrend so EMA50 is far above last close (>7% away).
        closes = list(np.linspace(200, 100, 60))
        lows = [c - 1.0 for c in closes]
        highs = [c + 1.0 for c in closes]
        lows[40] = 130.0
        # Undercut + reclaim on the last bar
        lows[-1] = 95.0
        closes[-1] = 132.0  # reclaim above pivot 130
        highs[-1] = 133.0
        df = _make_df(closes, lows=lows, highs=highs)
        os.environ["UR_REQUIRE_TREND"] = "true"
        ur = detect_undercut_rally(df)
        # When trend is broken and required, score should be 0
        self.assertEqual(ur.score, 0.0)
        self.assertFalse(ur.trend_ok)

    def test_chart_payload_smoke(self):
        df = _make_df(list(np.linspace(100, 110, 20)))
        cs = to_lightweight_candles(df)
        vols = to_lightweight_volume(df)
        line = to_lightweight_line(df["Close"])
        self.assertEqual(len(cs), 20)
        self.assertEqual(len(vols), 20)
        self.assertEqual(len(line), 20)
        self.assertSetEqual(set(cs[0].keys()), {"time", "open", "high", "low", "close"})

    def test_marker_only_when_detected(self):
        df = _make_df(list(np.linspace(100, 110, 5)))
        empty = ur_overlay_markers(df, {"ur_detected": False, "ur_score": 0.0})
        self.assertEqual(empty, [])
        m = ur_overlay_markers(df, {"ur_detected": True, "ur_score": 0.7})
        self.assertEqual(len(m), 1)
        self.assertEqual(m[0]["shape"], "arrowUp")


if __name__ == "__main__":
    unittest.main()
