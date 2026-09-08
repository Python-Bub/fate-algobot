"""Tests for built-in change cleaner."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class TestChangeCleaner(unittest.TestCase):
    def test_cleanup_orphan_respects_protected(self):
        import tools.change_cleaner as cc

        with patch.object(cc, "_protected_symbols", return_value={"DEAD"}):
            with tempfile.TemporaryDirectory() as td:
                model_dir = Path(td) / "models"
                model_dir.mkdir()
                orphan = model_dir / "ORPH_model.pkl"
                orphan.write_bytes(b"x" * 100)
                protected = model_dir / "DEAD_model.pkl"
                protected.write_bytes(b"x" * 100)

                with patch.object(cc, "_artifact_paths", lambda s: [model_dir / f"{s}_model.pkl"]):
                    out = cc.cleanup_orphan_symbols(["ORPH", "DEAD"], dry=True)
                self.assertIn("ORPH", out["symbols"])
                self.assertNotIn("DEAD", out["symbols"])

    def test_run_builtin_cleaner_dry(self):
        from tools.change_cleaner import run_builtin_cleaner

        plan = {
            "universe_diff": {"removed": ["ZZZZ"]},
            "tiers": {"top100_diff": {"exited": ["ZZZZ"]}, "top50_diff": {"exited": []}},
            "corporate": {"delistings": [], "migrations_applied": []},
        }
        with patch("tools.change_cleaner.run_prune_disk", return_value=0):
            report = run_builtin_cleaner(reason="test", plan=plan, dry_run=True, skip_disk=False)
        self.assertEqual(report["reason"], "test")
        self.assertIn("steps", report)


if __name__ == "__main__":
    unittest.main()
