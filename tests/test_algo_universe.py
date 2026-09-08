"""One algorithm for all stocks: unseen-ticker holdout, online adapter, rank boost."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import numpy as np


def _rows(n_tickers: int = 80, dates: int = 6) -> list[dict]:
    out = []
    for d in range(dates):
        date = f"2026-07-{10 + d:02d}"
        for i in range(n_tickers):
            p = 0.35 + (i % 10) * 0.04 + 0.01 * (d % 3)
            fwd = 0.012 if p >= 0.52 else -0.009
            y = 1 if fwd > 0 else 0
            if i % 11 == 0:
                y = 1 - y
                fwd = -fwd
            out.append(
                {
                    "ticker": f"U{i:03d}",
                    "p_up": p,
                    "p_up_raw": p,
                    "p_short_model": p,
                    "p_long_model": p,
                    "execution_confidence": 0.6,
                    "score": (p - 0.5) * 2,
                    "momentum_5d": 0.02 if y else -0.02,
                    "rs_spy": 1.0,
                    "volume_ratio": 1.0,
                    "sentiment": 0.2 if y else -0.2,
                    "dip_signal": 0.0,
                    "news_factor": 0.0,
                    "lstm_p_up": p,
                    "neural_p_up": p,
                    "y": y,
                    "fwd": fwd,
                    "signal_date": date,
                }
            )
    return out


class TestAlgoUniverse(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        os.environ["ALGO_MODEL_DIR"] = str(root / "algorithm")
        os.environ["ALGO_ONLINE_STATE"] = str(root / "online.json")
        os.environ["ALGO_ONLINE_REPLAY"] = str(root / "replay.jsonl")
        os.environ["ALGO_SMOKE_STATE"] = str(root / "smoke.json")
        os.environ["ALGO_HARVEST_ROWS"] = str(root / "harvest.json")
        os.environ["ALGO_DISTILL_STATE"] = str(root / "distill.json")
        os.environ["ALGO_DEPLOY_STATE"] = str(root / "deploy.json")
        os.environ["ALGO_PIPELINE_STATE"] = str(root / "state.json")
        os.environ["ALGO_COMPLETE_STATE"] = str(root / "complete.json")
        os.environ["ALGO_HARVEST_STATE"] = str(root / "harvest_state.json")
        os.environ["USE_ALGO_PIPELINE"] = "true"
        os.environ["USE_ALGO_ONLINE"] = "true"
        os.environ["RANK_W_ALGO"] = "0.12"
        os.environ["ALGO_ONLINE_TAU"] = "40"
        (root / "algorithm").mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_coverage_grows_exponentially_with_tickers(self):
        from analytics.algo_universe import coverage_weight

        a = coverage_weight(10, tau=40)
        b = coverage_weight(80, tau=40)
        c = coverage_weight(400, tau=40)
        self.assertGreater(b, a)
        self.assertGreater(c, b)
        self.assertLess(c, 1.0)
        self.assertGreater(c, 0.99)

    def test_scores_unseen_ticker_not_on_board(self):
        from analytics.algo_generation import current_ptr, distill
        from analytics.algo_universe import features_from_signals, live_rank_boost

        rows = _rows(40, 4)
        meta = distill(rows, generation=1)
        self.assertTrue(meta.get("ok"), meta)
        current_ptr().write_text(
            __import__("json").dumps({"generation": 1, "path": meta["path"]}),
            encoding="utf-8",
        )
        feats = features_from_signals(ticker="ZZNEW", p_up=0.72, exec_conf=0.7, mom_5d=0.02)
        boost, info = live_rank_boost("ZZNEW", feats)
        self.assertTrue(info.get("universe"))
        self.assertNotEqual(info.get("src"), "board")
        self.assertGreater(boost, 0.0)
        self.assertGreater(float(info.get("p_up") or 0), 0.5)

    def test_historical_smoke_unseen_tickers_beat_chance(self):
        from analytics.algo_universe import historical_smoke

        out = historical_smoke(_rows(60, 6))
        self.assertTrue(out.get("ok"), out)
        unseen = out.get("unseen_tickers") or {}
        self.assertGreaterEqual(float(unseen.get("auc") or 0), 0.55)
        self.assertGreaterEqual(int(unseen.get("n_test_tickers") or 0), 8)

    def test_online_adapter_learns_from_stream(self):
        from analytics.algo_universe import learn_from_outcome

        rows = _rows(30, 3)
        applied = 0
        for r in rows:
            rep = learn_from_outcome(str(r["ticker"]), float(r["fwd"]), features=r, side="LONG")
            if rep.get("applied"):
                applied += 1
        self.assertGreaterEqual(applied, 20)
        last = learn_from_outcome("U000", 0.02, features=rows[0], side="LONG")
        self.assertGreaterEqual(int(last.get("n_tickers") or 0), 10)
        self.assertGreater(float(last.get("coverage") or 0), 0.0)


if __name__ == "__main__":
    unittest.main()
