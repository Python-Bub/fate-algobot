"""Paper sim report usability gates — reject partial scans."""

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from analytics.paper_report import (
    is_usable_report,
    latest_valid_report,
    prune_unusable_paper_reports,
    report_quality_metrics,
)


class TestPaperReportQuality(unittest.TestCase):
    def test_good_report_passes(self):
        rep = Path("reports/paper_sim_20260605.json")
        if not rep.is_file():
            self.skipTest("no full paper sim report")
        doc = json.loads(rep.read_text(encoding="utf-8"))
        m = report_quality_metrics(doc)
        ok, reason = is_usable_report(doc)
        self.assertTrue(ok, reason)
        self.assertGreaterEqual(int(m["top100"]), 50)
        self.assertGreaterEqual(int(m["tradeable"]), 100)

    def test_thin_report_fails(self):
        doc = {
            "universe_size": 480,
            "symbols_scored": 50,
            "rows": [
                {"ticker": "HD", "skipped": False, "score": 0.1, "top100": True},
            ]
            * 50,
        }
        ok, reason = is_usable_report(doc)
        self.assertFalse(ok)
        self.assertTrue("top100" in reason or "tradeable" in reason)

    def test_prune_drops_unusable_files(self):
        reports = Path("reports")
        reports.mkdir(exist_ok=True)
        bad = reports / "paper_sim_20990101.json"
        bad.write_text(
            json.dumps(
                {
                    "universe_size": 480,
                    "symbols_scored": 12,
                    "rows": [{"ticker": "ZZZ", "skipped": False, "score": 0.1}] * 12,
                }
            ),
            encoding="utf-8",
        )
        try:
            _, removed = prune_unusable_paper_reports(dry_run=False)
            self.assertTrue(any("20990101" in x for x in removed))
            self.assertFalse(bad.is_file())
        finally:
            if bad.is_file():
                bad.unlink(missing_ok=True)

    def test_latest_skips_unusable(self):
        with patch.dict(
            "os.environ",
            {
                "PAPER_REPORT_REQUIRE_USABLE": "true",
                "PAPER_REPORT_PRUNE_UNUSABLE": "false",
            },
            clear=False,
        ):
            path, doc = latest_valid_report(min_rows=50)
        if path is None:
            self.skipTest("no usable report on disk")
        ok, _ = is_usable_report(doc or {})
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
