"""Historical smoke tests for 50 industry anchors on real price data."""

from __future__ import annotations

import os
import unittest


@unittest.skipUnless(
    os.getenv("RUN_INDUSTRY_HISTORICAL_SMOKE", "").lower() in ("1", "true", "yes"),
    "Set RUN_INDUSTRY_HISTORICAL_SMOKE=1 to hit live price APIs",
)
class TestIndustryHistoricalSmokeLive(unittest.TestCase):
    def test_all_fifty_anchors(self):
        from analytics.industries.project_wiring import run_all_historical_smoke

        summary = run_all_historical_smoke()
        self.assertGreater(summary["total"], 45)
        self.assertTrue(summary["all_ok"], f"failed={summary['total'] - summary['passed']}")


class TestIndustryHistoricalSmokeFast(unittest.TestCase):
    """Fast checks without network — registry + self-tests."""

    def test_anchor_registry(self):
        from analytics.industries.anchors import ALL_ANCHORS

        ids = [k for k in ALL_ANCHORS if k != "unclassified"]
        self.assertGreaterEqual(len(ids), 49)
        for iid, anchor in list(ALL_ANCHORS.items())[:10]:
            if iid == "unclassified":
                continue
            self.assertTrue(anchor.ANCHOR_TICKER, msg=iid)

    def test_project_wiring_imports(self):
        from analytics.industries.project_wiring import (
            run_all_historical_smoke,
            wire_monday_pick,
            wire_paper_sim_row,
            wire_score,
            wire_training_frame,
        )

        self.assertTrue(callable(wire_paper_sim_row))
        self.assertTrue(callable(wire_score))
        self.assertTrue(callable(wire_monday_pick))
        self.assertTrue(callable(wire_training_frame))
        self.assertTrue(callable(run_all_historical_smoke))

    def test_enhancement_self_tests_sample(self):
        from analytics.industries.enhancements import ALL_ENHANCEMENTS

        for iid in ("semiconductors", "biotech", "residential_reits", "diversified_banks"):
            rep = ALL_ENHANCEMENTS[iid].high_level_test()
            self.assertTrue(rep.get("net_positive"), rep)


if __name__ == "__main__":
    unittest.main()
