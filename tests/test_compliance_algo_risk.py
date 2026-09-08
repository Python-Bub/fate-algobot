"""Compliance guard includes automatic algo risk filter on BUY."""
import os
import unittest
from unittest.mock import patch


class TestComplianceAlgoRisk(unittest.TestCase):
    def test_pretrade_blocks_tmhc_ma(self):
        from compliance_guard import pretrade_check

        with patch.dict(os.environ, {"PAPER_RELAX_ALGO_RISK": "false"}, clear=False):
            with patch("intel.algo_risk_filter.blocks_buy", return_value=(True, "M&A dead money")):
                d = pretrade_check("TMHC", "BUY", qty=10, notional=500.0)
        self.assertFalse(d.ok)
        self.assertEqual(d.reason, "algo_risk_block")

    def test_pretrade_allows_sell_despite_risk(self):
        from compliance_guard import pretrade_check

        with patch("intel.algo_risk_filter.blocks_buy", return_value=(True, "M&A dead money")):
            d = pretrade_check("TMHC", "SELL", qty=10, notional=500.0)
        self.assertTrue(d.ok)

    def test_crypto_clip_uses_wider_single_cap(self):
        from compliance_guard import pretrade_check

        with patch("alpaca_broker.get_account", return_value={"equity": 71_000.0}):
            with patch("intel.algo_risk_filter.blocks_buy", return_value=(False, "")):
                d = pretrade_check(
                    "BTC-USD",
                    "BUY",
                    qty=0.12,
                    notional=10_000.0,
                    equity=71_000.0,
                )
        self.assertTrue(d.ok, d.reason)


if __name__ == "__main__":
    unittest.main()
