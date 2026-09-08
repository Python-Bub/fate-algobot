import os
import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ET = ZoneInfo("America/New_York")


class TestDuplicateBuyIsFailure(unittest.TestCase):
    def test_notional_buy_duplicate_returns_false(self):
        from alpaca_broker import place_notional_alpaca

        with patch("alpaca_broker.pending_buy_order", return_value={"id": "x"}):
            self.assertFalse(place_notional_alpaca("AAPL", 500.0, "BUY"))


class TestCryptoSession(unittest.TestCase):
    def test_weekend_crypto_buy_allowed(self):
        from analytics import market_session as ms

        dt = datetime(2026, 8, 16, 12, 0, tzinfo=ET)  # Sunday
        os.environ["TRADE_CRYPTO_24_7"] = "true"
        os.environ["TRADE_CRYPTO"] = "true"
        with patch.object(ms, "now_et", lambda: dt):
            ok, why = ms.orders_allowed("buy", symbol="BTC/USD")
        self.assertTrue(ok)
        self.assertIn("crypto", why)

    def test_weekend_equity_still_closed(self):
        from analytics import market_session as ms

        dt = datetime(2026, 8, 16, 12, 0, tzinfo=ET)
        os.environ["ALPACA_CLOCK_GATE"] = "true"
        with patch.object(ms, "now_et", lambda: dt):
            with patch.object(ms, "exchange_is_open", return_value=(False, "weekend")):
                ok, why = ms.orders_allowed("buy", symbol="AAPL")
        self.assertFalse(ok)


class TestHiddenPatternTrainZero(unittest.TestCase):
    def test_train_does_not_broadcast_live_scan(self):
        from analytics.hidden_pattern_learn import attach_hidden_pattern_features

        os.environ["HIDDEN_PATTERN_BROADCAST_HISTORY"] = "false"
        idx = pd.date_range("2024-01-01", periods=5, freq="B")
        df = pd.DataFrame({"Close": np.linspace(10, 11, 5)}, index=idx)
        with patch("analytics.hidden_pattern_anomaly.load_hits", return_value={"ts": 9e12, "by_symbol": {"AAA": {"score": 0.9, "direction": 1}}}):
            out = attach_hidden_pattern_features(df, "AAA")
        self.assertTrue((out["hidden_anomaly_score"] == 0.0).all())


class TestPrecisionAtTopQ(unittest.TestCase):
    def test_small_holdout_is_nan_not_perfect(self):
        from model_trainer import _acc_at_top_q

        os.environ["ACC_TOP_MIN_K"] = "20"
        y = np.ones(10)
        p = np.linspace(0.1, 0.9, 10)
        v = _acc_at_top_q(y, p, 0.2)
        self.assertTrue(v != v)  # NaN

    def test_large_holdout_precision(self):
        from model_trainer import _acc_at_top_q

        os.environ["ACC_TOP_MIN_K"] = "20"
        y = np.array([1] * 20 + [0] * 80)
        p = np.linspace(1.0, 0.0, 100)
        v = _acc_at_top_q(y, p, 0.2)
        self.assertAlmostEqual(v, 1.0)


class TestPolicyAlias(unittest.TestCase):
    def test_buy_threshold_feeds_min_model_confidence(self, tmp_path=None):
        from self_modify import policy_agent as pa

        path = pa.OVERRIDE_PATH
        old = path.read_text() if path.is_file() else None
        env_old = {k: os.environ.get(k) for k in ("POLICY_ENV_WINS", "MIN_MODEL_CONFIDENCE", "BUY_THRESHOLD")}
        try:
            os.environ["POLICY_ENV_WINS"] = "false"
            os.environ.pop("MIN_MODEL_CONFIDENCE", None)
            os.environ.pop("BUY_THRESHOLD", None)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('{"BUY_THRESHOLD": 0.66}\n', encoding="utf-8")
            v = pa.get_runtime_param("MIN_MODEL_CONFIDENCE", 0.55)
            self.assertEqual(float(v), 0.66)
        finally:
            for k, val in env_old.items():
                if val is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = val
            if old is None:
                try:
                    path.unlink()
                except OSError:
                    pass
            else:
                path.write_text(old, encoding="utf-8")

    def test_env_wins_over_stale_policy_json(self):
        from self_modify import policy_agent as pa

        os.environ["POLICY_ENV_WINS"] = "true"
        os.environ["MIN_MODEL_CONFIDENCE"] = "0.62"
        self.assertEqual(float(pa.get_runtime_param("MIN_MODEL_CONFIDENCE", 0.55)), 0.62)


class TestAlpacaCapacity(unittest.TestCase):
    def test_maps_equity_and_does_not_treat_bp_as_nav(self):
        from analytics.alpaca_capacity import capacity_from_account, size_budget_usd

        cap = capacity_from_account(
            {
                "equity": "74519.79",
                "portfolio_value": "74519.79",
                "cash": "12000",
                "buying_power": "200000",
                "crypto_buying_power": "12000",
            }
        )
        self.assertAlmostEqual(cap["equity"], 74519.79)
        self.assertAlmostEqual(cap["buying_power"], 200000.0)
        budget = size_budget_usd(cap, max_frac=0.10)
        self.assertLess(budget, 200000.0)
        self.assertAlmostEqual(budget, 7451.979)


class TestCramerTableCap(unittest.TestCase):
    def test_apply_sleeve_caps_cramer_to_table(self):
        from analytics.sleeve_weights import apply_sleeve_env

        os.environ["RANK_W_CRAMER"] = "0.70"
        os.environ["FORTRESS_CRAMER_BLEND"] = "0.85"
        apply_sleeve_env("fortress", force=True)
        self.assertLessEqual(float(os.environ["RANK_W_CRAMER"]), 0.06)
        self.assertLessEqual(float(os.environ["FORTRESS_CRAMER_BLEND"]), 0.06)


class TestInvalidateCacheExists(unittest.TestCase):
    def test_symbol(self):
        from alpaca_broker import invalidate_rest_cache

        invalidate_rest_cache()


if __name__ == "__main__":
    unittest.main()
