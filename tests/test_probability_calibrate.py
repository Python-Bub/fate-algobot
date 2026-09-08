import os
import unittest

from analytics.probability_calibrate import (
    calibrate_horizon_probs,
    calibrate_probability,
    display_chance_pct,
)


class TestProbabilityCalibrate(unittest.TestCase):
    def test_raw_display_preserves_spread(self):
        os.environ["CHANCE_DISPLAY_MODE"] = "raw"
        self.assertEqual(display_chance_pct(0.82), 82)
        self.assertEqual(display_chance_pct(0.35), 35)
        self.assertNotEqual(display_chance_pct(0.82), display_chance_pct(0.55))

    def test_calibrated_display_mode(self):
        os.environ["CHANCE_DISPLAY_MODE"] = "calibrated"
        os.environ["USE_PROB_CALIBRATION"] = "true"
        os.environ["CHANCE_PCT_MIN"] = "8"
        os.environ["CHANCE_PCT_MAX"] = "92"
        hi = calibrate_probability(1.0)
        lo = calibrate_probability(0.0)
        mid = calibrate_probability(0.5)
        self.assertEqual(hi["chance_pct"], 92)
        self.assertEqual(lo["chance_pct"], 8)
        self.assertEqual(mid["chance_pct"], 50)

    def test_horizon_bundle_uses_per_head_raw(self):
        os.environ["CHANCE_DISPLAY_MODE"] = "raw"
        h = calibrate_horizon_probs(p_daily=0.72, p_short=0.41, p_long=0.68, p_xlong=0.91)
        self.assertEqual(h["p_daily_chance_pct"], 72)
        self.assertEqual(h["p_short_chance_pct"], 41)
        self.assertEqual(h["p_long_chance_pct"], 68)
        self.assertEqual(h["p_xlong_chance_pct"], 91)


if __name__ == "__main__":
    unittest.main()
