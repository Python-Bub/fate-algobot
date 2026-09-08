import os
import tempfile
import unittest

import numpy as np


class TestNeuralEnsemble(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["USE_NEURAL_ENSEMBLE"] = "true"
        os.environ["NEURAL_REPLAY_FILE"] = os.path.join(self.tmp.name, "replay.jsonl")
        os.environ["NEURAL_MODEL_DIR"] = os.path.join(self.tmp.name, "models")
        os.environ["NEURAL_MIN_SAMPLES"] = "40"
        os.environ["NEURAL_MAX_SAMPLES"] = "500"
        os.environ["NEURAL_EPOCHS"] = "1"
        os.environ["NEURAL_BATCH"] = "64"
        os.environ["NEURAL_SEQ_LEN"] = "12"

    def tearDown(self):
        self.tmp.cleanup()

    def test_train_and_predict(self):
        from online_learning import neural_ensemble as ne

        if not ne.use_neural_ensemble():
            self.skipTest("torch missing or disabled")

        rs = np.random.RandomState(42)
        ticker = "TEST"
        for _ in range(160):
            p = float(rs.uniform(0.2, 0.8))
            rr = float((p - 0.5) * 0.06 + rs.normal(0, 0.005))
            side = "LONG" if p >= 0.5 else "SHORT"
            reward = rr if side == "LONG" else -rr
            state = {
                "p_up_base": p,
                "p_short_model": 1.0 - p,
                "p_long_model": p,
                "execution_confidence": min(1.0, max(0.0, p)),
                "sentiment": float(rs.normal(0, 0.4)),
                "news_factor": float(rs.normal(0, 0.2)),
                "transcript_factor": float(rs.normal(0, 0.2)),
                "volume_ratio": float(rs.uniform(0.8, 2.0)),
                "momentum_5d": float(rs.normal(0, 0.03)),
                "rs_spy": float(rs.uniform(0.9, 1.1)),
                "dip_signal": float(rs.uniform(0, 1)),
                "atr_14": float(rs.uniform(0.5, 4.0)),
                "alpha_proxy_20": float(rs.normal(0, 0.03)),
            }
            ne.record_neural_experience(ticker, state, side, rr, reward)

        rep = ne.train_neural_ensemble_for_ticker(ticker)
        self.assertTrue(rep.applied, rep.reason)
        self.assertGreater(rep.n_samples, 40)

        q_state = {
            "p_up_base": 0.62,
            "p_short_model": 0.38,
            "p_long_model": 0.62,
            "execution_confidence": 0.61,
            "sentiment": 0.15,
            "news_factor": 0.08,
            "transcript_factor": 0.02,
            "volume_ratio": 1.3,
            "momentum_5d": 0.01,
            "rs_spy": 1.03,
            "dip_signal": 0.2,
            "atr_14": 1.2,
            "alpha_proxy_20": 0.015,
        }
        p = ne.neural_ensemble_p_up(ticker, q_state)
        self.assertIsNotNone(p)
        self.assertGreaterEqual(float(p), 0.0)
        self.assertLessEqual(float(p), 1.0)

        details = ne.neural_ensemble_details(ticker, q_state)
        self.assertIsNotNone(details)
        self.assertIn("ensemble_p_up", details)
        self.assertIn("models", details)
        self.assertGreaterEqual(details["n_models_loaded"], 1)
        self.assertAlmostEqual(float(details["ensemble_p_up"]), float(p), places=4)

        wr = ne.model_win_rates_for_ticker(ticker)
        self.assertTrue(wr)
        for k in ("lstm", "cnn", "ga_lstm", "cnn_bilstm", "dqn"):
            if k in wr:
                self.assertGreater(wr[k]["n"], 0)
                self.assertGreaterEqual(wr[k]["win_rate"], 0.0)
                self.assertLessEqual(wr[k]["win_rate"], 1.0)

        dash = ne.build_neural_dashboard(
            [{"ticker": ticker, "action": "BUY", "p_up": 0.6, "neural_p_up": p, "neural_breakdown": details}]
        )
        self.assertIn("model_leaderboard", dash)
        self.assertGreaterEqual(dash["symbols_with_neural"], 1)

    def test_fill_state_aliases_are_not_zeros(self):
        from online_learning.neural_ensemble import _feat

        st = {"p_long": 0.71, "p_short": 0.29, "exec_c": 0.66, "sentiment_impulse": 0.2}
        self.assertAlmostEqual(_feat(st, "p_up_base"), 0.71, places=4)
        self.assertAlmostEqual(_feat(st, "p_short_model"), 0.29, places=4)
        self.assertAlmostEqual(_feat(st, "execution_confidence"), 0.66, places=4)
        self.assertAlmostEqual(_feat(st, "sentiment"), 0.2, places=4)

    def test_blend_preds_downweights_outlier(self):
        from online_learning.neural_ensemble import _blend_preds
        import numpy as np

        p, std = _blend_preds(np.asarray([0.60, 0.61, 0.59, 0.95]))
        self.assertGreater(p, 0.55)
        self.assertLess(p, 0.80)
        self.assertGreater(std, 0.0)


if __name__ == "__main__":
    unittest.main()

