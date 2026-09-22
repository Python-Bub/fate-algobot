"""Paper-sim active universe: intraday-trained tickers only."""
import os
import unittest
from unittest.mock import patch


def _stub_trained(n: int = 450) -> list[str]:
    from fortress_universe import load_top100_symbols

    extra = [f"Z{i:03d}" for i in range(n)]
    return list(dict.fromkeys(list(load_top100_symbols()) + extra + ["AAPL", "MSFT", "NVDA"]))


class TestPaperActiveUniverse(unittest.TestCase):
    def test_active_universe_size(self):
        os.environ["PAPER_SIM_ACTIVE_MODE"] = "top100_rotate"
        os.environ["PAPER_SIM_ACTIVE_MAX"] = "480"
        stub = _stub_trained()
        with patch("fortress_universe.symbols_with_trained_intraday", return_value=stub), patch(
            "fortress_universe.symbols_with_daily_models", return_value=stub
        ):
            from fortress_universe import (
                symbols_paper_active_universe,
                symbols_with_trained_intraday,
            )

            intra = symbols_with_trained_intraday()
            active = symbols_paper_active_universe()
        self.assertGreaterEqual(len(intra), 400)
        self.assertGreaterEqual(len(active), 80)
        self.assertLessEqual(len(active), 550)
        self.assertIn("AAPL", active)
        self.assertNotIn("AAAA", active)

    def test_resolve_universe_uses_active_by_default(self):
        os.environ.pop("PAPER_SIM_USE_LIVE_LIST", None)
        os.environ["PAPER_SIM_CONFIG_TICKERS_ONLY"] = "false"
        os.environ["PAPER_SIM_USE_MODEL_UNIVERSE"] = "false"
        os.environ["PAPER_SIM_ACTIVE_ONLY"] = "true"
        os.environ["PAPER_SIM_ACTIVE_MODE"] = "top100_rotate"
        os.environ["PAPER_SIM_ACTIVE_MAX"] = "480"
        stub = _stub_trained()
        with patch("fortress_universe.symbols_with_trained_intraday", return_value=stub), patch(
            "fortress_universe.symbols_with_daily_models", return_value=stub
        ):
            from paper_sim_today import _resolve_universe

            syms = _resolve_universe(None)
        self.assertGreater(len(syms), 80)
        self.assertLess(len(syms), 600)


if __name__ == "__main__":
    unittest.main()
