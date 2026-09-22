"""Scan order must not walk the alphabet A→B→C."""
import os
import unittest


class TestUniverseScanOrder(unittest.TestCase):
    def test_hash_shuffle_not_abc_walk(self):
        from fortress_universe import hash_shuffle

        syms = [f"{c}{i}" for c in "ABCDEFGHIJ" for i in range(5)]
        out = hash_shuffle(syms, "testseed")
        # A0,B0,C0 walk would put A before B before C in first three slots.
        self.assertNotEqual([s[0] for s in out[:3]], ["A", "B", "C"])

    def test_apply_scan_order_spreads_letters(self):
        os.environ["SCAN_ORDER_MODE"] = "hash"
        os.environ["SCAN_ORDER_SEED"] = "unittest"
        from fortress_universe import apply_scan_order, symbols_paper_active_universe

        active = symbols_paper_active_universe()
        head = active[: min(30, len(active))]
        a_head = sum(1 for s in head if s.startswith("A"))
        b_head = sum(1 for s in head if s.startswith("B"))
        self.assertLess(a_head, 15, msg=f"A-heavy: {head}")
        self.assertLess(b_head, 15, msg=f"B-heavy: {head}")

    def test_fortress_scan_not_abc_walk(self):
        os.environ["SCAN_ORDER_MODE"] = "hash"
        os.environ["SCAN_ORDER_SEED"] = "fortress-test"
        from fortress_universe import load_fortress_scan_list

        syms = load_fortress_scan_list(40, shuffle_rest=False)
        letters = [s[0] for s in syms[:10]]
        self.assertNotEqual(letters[:3], ["A", "B", "C"])

    def test_resolve_universe_capped(self):
        os.environ.pop("PAPER_SIM_USE_LIVE_LIST", None)
        os.environ["PAPER_SIM_CONFIG_TICKERS_ONLY"] = "false"
        os.environ["PAPER_SIM_USE_MODEL_UNIVERSE"] = "false"
        os.environ["PAPER_SIM_ACTIVE_ONLY"] = "true"
        os.environ["PAPER_SIM_ACTIVE_MODE"] = "top100_rotate"
        os.environ["PAPER_SIM_ACTIVE_MAX"] = "480"
        os.environ["SCAN_ORDER_MODE"] = "hash"
        from unittest.mock import patch

        from fortress_universe import load_top100_symbols

        stub = list(dict.fromkeys(list(load_top100_symbols()) + [f"Z{i:03d}" for i in range(400)] + ["AAPL"]))
        with patch("fortress_universe.symbols_with_trained_intraday", return_value=stub), patch(
            "fortress_universe.symbols_with_daily_models", return_value=stub
        ):
            from paper_sim_today import _resolve_universe

            syms = _resolve_universe(None)
        self.assertGreater(len(syms), 80)
        self.assertLess(len(syms), 600)

    def test_prioritize_training_not_alphabet_cap(self):
        os.environ["TRAIN_PRIORITIZE"] = "top100"
        os.environ["SCAN_ORDER_SEED"] = "train-test"
        from fortress_universe import load_top100_symbols, prioritize_training_universe

        top = load_top100_symbols()[:20]
        alphabet = sorted(f"{c}{i}" for c in "ABCDEFGHIJKLMNOP" for i in range(3))
        ordered = prioritize_training_universe(top + alphabet, cap=25)
        head = ordered[:10]
        self.assertIn("NVDA", head)
        self.assertIn("MSFT", head)
        self.assertNotEqual(head[:3], sorted(alphabet)[:3])

    def test_letter_rr_equal_no_mega_first(self):
        os.environ["TRAIN_PRIORITIZE"] = "letter_rr"
        os.environ["SCAN_ORDER_SEED"] = "letter-fair-test"
        from fortress_universe import prioritize_training_universe

        alphabet = [f"{c}{i}" for c in "ABCDEFGHIJKLMNOP" for i in range(3)]
        # Mix in mega names that would dominate under top100 mode
        ordered = prioritize_training_universe(["NVDA", "MSFT", "AAPL"] + alphabet)
        head_letters = [s[0] for s in ordered[:16]]
        self.assertEqual(len(set(head_letters)), len(head_letters), msg=f"not RR: {ordered[:16]}")
        self.assertNotEqual(ordered[:3], sorted(alphabet)[:3])

    def test_quality_half_cap(self):
        os.environ["TRAIN_PRIORITIZE"] = "top100"
        os.environ["TRAIN_QUALITY_HALF"] = "true"
        syms = [f"S{i}" for i in range(100)]
        from fortress_universe import prioritize_training_universe

        out = prioritize_training_universe(syms, quality_half=True)
        self.assertEqual(len(out), 50)


if __name__ == "__main__":
    unittest.main()
