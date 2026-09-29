"""Paper-sim active universe: intraday-trained tickers only."""
import os
import unittest
from unittest import mock

_ACTIVE_ENV = {
    "PAPER_SIM_ACTIVE_MODE": "top100_rotate",
    "PAPER_SIM_ACTIVE_MAX": "480",
}


class TestPaperActiveUniverse(unittest.TestCase):
    def test_active_universe_size(self):
        from fortress_universe import (
            symbols_paper_active_universe,
            symbols_with_trained_intraday,
        )

        with mock.patch.dict(os.environ, _ACTIVE_ENV):
            intra = symbols_with_trained_intraday()
            active = symbols_paper_active_universe()
        self.assertGreaterEqual(len(intra), 400)
        self.assertGreaterEqual(len(active), 80)
        self.assertLessEqual(len(active), 550)
        self.assertIn("AAPL", active)
        self.assertNotIn("AAAA", active)

    def test_resolve_universe_uses_active_by_default(self):
        # Import first: paper_sim_today loads data/deploy_scale.env with override=True
        # at import time (deploy knobs deliberately win), so env must be set after.
        from paper_sim_today import _resolve_universe

        env = dict(_ACTIVE_ENV)
        env.update(
            {
                "PAPER_SIM_CONFIG_TICKERS_ONLY": "false",
                "PAPER_SIM_USE_MODEL_UNIVERSE": "false",
                "PAPER_SIM_ACTIVE_ONLY": "true",
            }
        )
        with mock.patch.dict(os.environ, env):
            os.environ.pop("PAPER_SIM_USE_LIVE_LIST", None)
            syms = _resolve_universe(None)
        self.assertGreater(len(syms), 80)
        self.assertLess(len(syms), 600)


if __name__ == "__main__":
    unittest.main()
