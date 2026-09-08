"""Master test runner — high-level validation for all 50 industry enhancements."""

from __future__ import annotations

import unittest

from analytics.industries.enhancements import ALL_ENHANCEMENTS
from analytics.industries.enhancements._base import ENHANCEMENT_FEATURES


class TestAllFiftyEnhancements(unittest.TestCase):
    def test_registry_count(self):
        ids = [k for k in ALL_ENHANCEMENTS if k != "unclassified"]
        self.assertGreaterEqual(len(ids), 49)

    def test_every_industry_high_level(self):
        failures: list[str] = []
        for iid, enh in ALL_ENHANCEMENTS.items():
            if iid == "unclassified":
                continue
            report = enh.high_level_test()
            if not report.get("net_positive"):
                failures.append(f"{iid}: not net positive — {report}")
            if report.get("features_implemented", 0) < len(ENHANCEMENT_FEATURES):
                failures.append(f"{iid}: missing features — {report.get('features_missing')}")
        self.assertFalse(failures, "\n".join(failures[:10]))

    def test_enhancement_beats_baseline_pipeline(self):
        from analytics.industries.pipeline import run_industry_pipeline

        sym = "NVDA"
        base_macro = {
            "macro_score": 0.45,
            "pmi_score": 0.65,
            "nasdaq_ret_5d": 0.03,
            "rate_shock_20d": -0.04,
            "vix": 18.0,
            "spread_10y2y": 0.15,
        }
        pipe = run_industry_pipeline(sym, macro_bundle=base_macro)
        self.assertTrue(pipe.get("enabled"))
        self.assertGreater(float(pipe.get("score_delta") or 0), 0.05)


if __name__ == "__main__":
    unittest.main()
