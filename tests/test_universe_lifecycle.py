"""Universe lifecycle: rankings, corporate actions, tiered training."""
import os
import unittest


class TestUniverseLifecycle(unittest.TestCase):
    def test_canonical_symbol_chain(self):
        from symbol_aliases import canonical_symbol, price_feed_symbol

        self.assertEqual(price_feed_symbol("sq"), "XYZ")
        self.assertEqual(canonical_symbol("FB"), "META")

    def test_diff_universe(self):
        from universe_lifecycle.snapshot import diff_universe

        d = diff_universe(["AAPL", "MSFT"], ["AAPL", "NVDA"])
        self.assertEqual(d["added"], ["NVDA"])
        self.assertEqual(d["removed"], ["MSFT"])

    def test_corporate_registry_load(self):
        from universe_lifecycle.corporate_actions import alias_map, load_registry

        reg = load_registry()
        self.assertIn("aliases", reg)
        m = alias_map(reg)
        self.assertEqual(m.get("SQ"), "XYZ")

    def test_register_rename(self):
        import tempfile
        from pathlib import Path
        from universe_lifecycle import corporate_actions as ca

        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "corp.json"
            ca.CORPORATE_ACTIONS_PATH = p
            ev = ca.register_event(kind="rename", old="OLDX", new="NEWX", source="test")
            self.assertEqual(ev["kind"], "rename")
            reg = ca.load_registry()
            self.assertEqual(reg["aliases"]["OLDX"], "NEWX")

    def test_tier_diff_helpers(self):
        from universe_lifecycle.rankings import _tier_diff

        d = _tier_diff(["A", "B"], ["B", "C"])
        self.assertEqual(d["entered"], ["C"])
        self.assertEqual(d["exited"], ["A"])

    def test_load_top50pct_fallback(self):
        import json
        from fortress_universe import TOP50_CACHE, load_top50pct_symbols

        if not TOP50_CACHE.is_file():
            TOP50_CACHE.parent.mkdir(parents=True, exist_ok=True)
            TOP50_CACHE.write_text(
                json.dumps({"symbols": ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL"]}),
                encoding="utf-8",
            )
        syms = load_top50pct_symbols()
        self.assertGreater(len(syms), 3)

    def test_maintenance_plan_dry_run(self):
        os.environ["UNIVERSE_REFRESH_ON_MAINT"] = "false"
        from tools.universe_monthly_maintenance import build_maintenance_plan

        plan = build_maintenance_plan(dry_run=True)
        self.assertIn("universe_diff", plan)
        self.assertIn("train", plan)


if __name__ == "__main__":
    unittest.main()
