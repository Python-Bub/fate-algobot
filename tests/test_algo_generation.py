"""100-phase algorithm factory: distill student from teacher rows, chain batches."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def _rows(n: int = 80) -> list[dict]:
    out = []
    for i in range(n):
        p = 0.35 + (i % 10) * 0.04
        fwd = 0.01 if p >= 0.52 else -0.008
        y = 1 if fwd > 0 else 0
        if i % 11 == 0:
            y = 1 - y
            fwd = -fwd
        out.append(
            {
                "ticker": f"T{i:03d}",
                "p_up": p,
                "p_up_raw": p,
                "p_short_model": p,
                "p_long_model": p,
                "execution_confidence": 0.6,
                "score": p,
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
            }
        )
    return out


class TestAlgoGeneration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        os.environ["ALGO_PIPELINE_STATE"] = str(root / "state.json")
        os.environ["ALGO_BOARD_PATH"] = str(root / "board.json")
        os.environ["ALGO_CANDIDATE_BOARD"] = str(root / "board_candidate.json")
        os.environ["ALGO_PIPELINE_PHASE"] = str(root / "pipeline.json")
        os.environ["ALGO_OVERLAY_PATH"] = str(root / "overlay.json")
        os.environ["ALGO_OVERLAY_CANDIDATE"] = str(root / "overlay_candidate.json")
        os.environ["ALGO_FUSE_STATE"] = str(root / "fuse.json")
        os.environ["ALGO_DEPLOY_STATE"] = str(root / "deploy.json")
        os.environ["ALGO_BATCH_FILE"] = str(root / "batch.txt")
        os.environ["ALGO_BATCH_STATE"] = str(root / "batch.json")
        os.environ["ALGO_ADVANCE_STATE"] = str(root / "advance.json")
        os.environ["ALGO_COMPLETE_STATE"] = str(root / "complete.json")
        os.environ["ALGO_LEDGER"] = str(root / "ledger.json")
        os.environ["ALGO_HARVEST_ROWS"] = str(root / "harvest_rows.json")
        os.environ["ALGO_SCAN_STATE"] = str(root / "scan.json")
        os.environ["ALGO_COVER_STATE"] = str(root / "cover.json")
        os.environ["ALGO_ENSURE_LOOP"] = "false"
        os.environ["ALGO_TRAIN_CHECKPOINT"] = str(root / "train_checkpoint.json")
        (root / "train_checkpoint.json").write_text("{}", encoding="utf-8")
        os.environ["ALGO_MODEL_DIR"] = str(root / "algorithm")
        os.environ["ALGO_HARVEST_STATE"] = str(root / "harvest.json")
        os.environ["ALGO_DISTILL_STATE"] = str(root / "distill.json")
        os.environ["ALGO_QUALITY_STATE"] = str(root / "quality.json")
        os.environ["ALGO_QUALITY_FILE"] = str(root / "quality_weak.txt")
        os.environ["ALGO_QUALITY_SCAN"] = "false"
        os.environ["ALGO_KICK_TRAIN"] = "false"
        os.environ["ALGO_KICK_DAILY_BATCH"] = "false"
        os.environ["ALGO_SKIP_UNCHANGED"] = "true"
        os.environ["ALGO_BATCH_SIZE"] = "40"
        os.environ["ALGO_DISTILL_RECIPE"] = "teacher_blend_v1"
        os.environ["ALGO_HARVEST_PKL_JOIN"] = "false"
        os.environ["ALGO_UNIVERSE_GAPS"] = "false"
        os.environ["ALGO_SCAN_TTL_SEC"] = "0"
        os.environ["USE_ALGO_PIPELINE"] = "true"
        os.environ["RANK_W_ALGO"] = "0.12"
        self._prev_harvest = os.environ.get("ALGO_HARVEST_REPORTS")
        self._prev_stats = os.environ.get("TRAIN_STATS_PATH")

    def tearDown(self):
        if self._prev_harvest is None:
            os.environ.pop("ALGO_HARVEST_REPORTS", None)
        else:
            os.environ["ALGO_HARVEST_REPORTS"] = self._prev_harvest
        if self._prev_stats is None:
            os.environ.pop("TRAIN_STATS_PATH", None)
        else:
            os.environ["TRAIN_STATS_PATH"] = self._prev_stats
        self.tmp.cleanup()

    def test_harvest_joins_train_stats(self):
        from analytics.algo_generation import harvest_teachers

        reports = Path(self.tmp.name) / "reports"
        reports.mkdir()
        (reports / "paper_sim_latest.json").write_text(
            __import__("json").dumps(
                {
                    "generated_at_utc": "2026-08-11T00:00:00+00:00",
                    "symbols_scored": 2,
                    "skipped_no_model_or_history": 3,
                    "rows": [
                        {
                            "ticker": "AAA",
                            "skipped": False,
                            "signal_date": "2026-08-06",
                            "p_up": 0.62,
                            "fwd_1d_return": 0.02,
                        },
                        {
                            "ticker": "BBB",
                            "skipped": False,
                            "signal_date": "2026-08-06",
                            "p_up": 0.41,
                            "fwd_1d_return": -0.01,
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        stats = Path(self.tmp.name) / "train_run_stats.jsonl"
        stats.write_text(
            '{"ticker":"AAA","daily_top20":0.71,"meta_auc":0.66,"lstm_test_acc":0.58}\n',
            encoding="utf-8",
        )
        os.environ["ALGO_HARVEST_REPORTS"] = str(reports)
        os.environ["TRAIN_STATS_PATH"] = str(stats)
        os.environ["ALGO_HARVEST_STATE"] = str(Path(self.tmp.name) / "harvest.json")
        rows = harvest_teachers()
        self.assertEqual(len(rows), 2)
        aaa = next(r for r in rows if r["ticker"] == "AAA")
        self.assertEqual(aaa["y"], 1)
        self.assertAlmostEqual(aaa["daily_top20"], 0.71)
        self.assertTrue(aaa["joined_daily"])
        import json

        doc = json.loads((Path(self.tmp.name) / "harvest.json").read_text(encoding="utf-8"))
        self.assertEqual(doc["n_rows"], 2)
        self.assertEqual(doc["skipped_no_model_or_history"], 3)

    def test_cover_queues_without_spawn(self):
        from analytics.algo_generation import cover_gaps

        with patch("analytics.algo_generation._pid_running", return_value=False):
            out = cover_gaps(
                {
                    "missing_intraday": 12,
                    "missing_lstm": 0,
                    "cover_intraday_file": str(Path(self.tmp.name) / "cover.txt"),
                }
            )
        self.assertEqual(out["note"], "queued_file")
        self.assertEqual(out["missing_intraday"], 12)
        self.assertTrue(out.get("algorithm_independent"))
        self.assertEqual(out.get("status"), "teacher_backlog")

    def test_quality_queues_without_spawn(self):
        from analytics.algo_generation import quality_retrain

        with patch("analytics.algo_generation._pid_running", return_value=False):
            with patch("analytics.algo_generation._backup_pickles", return_value=[]):
                out = quality_retrain({"weak_sample": ["AAPL", "JNJ"]})
        self.assertEqual(out["note"], "queued_file")
        self.assertEqual(out["symbols"], ["AAPL", "JNJ"])
        self.assertTrue((Path(self.tmp.name) / "quality_weak.txt").is_file())

    def test_fuse_stays_staged_when_not_deploy_ready(self):
        from analytics.algo_generation import fuse, overlay_path, overlay_candidate_path

        meta = fuse(
            3,
            {"deploy_ready": False, "auc_oos": 0.49, "auc_teacher_oos": 0.52, "kind": "hgb"},
            {"hot": ["AAA"], "teacher_hot": ["BBB"], "cold": ["CCC"], "deploy_ready": False},
            {"symbols": ["AAPL"]},
        )
        self.assertFalse(meta.get("live"))
        self.assertTrue(overlay_candidate_path().is_file())
        self.assertFalse(overlay_path().is_file())

    def test_deploy_refuses_when_oos_below_teacher(self):
        from analytics.algo_generation import current_ptr, deploy

        (Path(self.tmp.name) / "algorithm").mkdir(parents=True, exist_ok=True)
        fake = Path(self.tmp.name) / "algorithm" / "gen_00003_algo.pkl"
        fake.write_bytes(b"not-a-real-pickle-but-exists")
        out = deploy(
            3,
            {
                "path": str(fake),
                "deploy_ready": False,
                "auc_oos": 0.49,
                "auc_teacher_oos": 0.52,
            },
        )
        self.assertFalse(out.get("deployed"))
        self.assertEqual(out.get("note"), "refused_oos_below_teacher")
        self.assertFalse(current_ptr().is_file())

    def test_batch_prioritizes_weak_not_hot(self):
        from analytics.algo_generation import make_batch

        (Path(self.tmp.name) / "train_checkpoint.json").write_text(
            '{"failed": {"ZZGAP": "skipped_no_model"}}',
            encoding="utf-8",
        )
        out = make_batch(
            {"weak_sample": ["AAPL"], "missing_intraday_sample": ["UPBD"]},
            {"hot": ["GNRC", "WBTN"]},
            {"symbols": ["AAPL", "JNJ"]},
        )
        self.assertEqual(out["symbols"][0], "AAPL")
        self.assertIn("JNJ", out["symbols"])
        self.assertNotIn("GNRC", out["symbols"])
        self.assertNotIn("UPBD", out["symbols"])

    def test_batch_size_zero_is_unbounded(self):
        from analytics.algo_generation import make_batch

        os.environ["ALGO_BATCH_SIZE"] = "0"
        failed = {f"G{i:03d}": "skipped_no_model" for i in range(80)}
        (Path(self.tmp.name) / "train_checkpoint.json").write_text(
            __import__("json").dumps({"failed": failed}),
            encoding="utf-8",
        )
        out = make_batch({}, {}, {"symbols": []})
        self.assertEqual(out["n"], 80)

    def test_advance_queues_when_trainers_busy(self):
        from analytics.algo_generation import _write_batch, advance

        _write_batch(["AAPL", "AAL"])
        with patch("analytics.algo_generation.trainers_busy", return_value=["train-intraday"]):
            with patch("analytics.algo_generation._pid_running", return_value=False):
                out = advance(["AAPL", "AAL"], generation=3, ensure_loop=False)
        self.assertTrue(str(out.get("kick") or "").startswith("queued"))
        self.assertEqual(out["loop"], "skipped")

    def test_hundred_named_phases(self):
        from analytics.algo_generation import CORE_PHASES, N_WAVES, PHASES

        self.assertEqual(len(CORE_PHASES), 11)
        self.assertEqual(N_WAVES, 9)
        self.assertEqual(len(PHASES), 100)
        self.assertEqual(PHASES[0], "scan")
        self.assertEqual(PHASES[10], "finalize")
        self.assertEqual(PHASES[11], "w2_scan")
        self.assertEqual(PHASES[-1], "complete")

    def test_distill_and_rank_boost(self):
        from analytics.algo_generation import algo_rank_boost, distill, pipeline_score

        rows = _rows(80)
        meta = distill(rows, generation=1)
        self.assertTrue(meta.get("ok"), meta)
        self.assertGreaterEqual(float(meta.get("auc") or 0), 0.55)
        self.assertIn("auc_oos", meta)
        self.assertTrue((Path(self.tmp.name) / "distill.json").is_file())
        pipeline_score(rows)
        self.assertTrue((Path(self.tmp.name) / "board_candidate.json").is_file())
        hot = rows[9]["ticker"]  # p=0.35+9*0.04=0.71
        import json as _json
        cand = _json.loads((Path(self.tmp.name) / "board_candidate.json").read_text(encoding="utf-8"))
        self.assertIn(hot, cand.get("board") or {})
        boost, info = algo_rank_boost(hot)
        self.assertEqual(boost, 0.0)
        self.assertTrue(info.get("staged") or info.get("miss") or cand.get("live") is False)

    def test_blend_picks_teacher_when_student_has_no_edge(self):
        from analytics.algo_generation import distill

        rows = _rows(80)
        meta = distill(rows, generation=1)
        kinds = [c.get("kind") for c in (meta.get("candidates") or [])]
        self.assertIn("teacher", kinds)
        self.assertTrue(any(str(k).startswith("blend_") for k in kinds) or "calibrated" in kinds)

    def test_generation_runs_all_phases(self):
        from analytics.algo_generation import PHASES, run_generation

        rows = _rows(80)
        catalog = {
            "daily_models": 10,
            "intraday_models": 8,
            "lstm_models": 7,
            "neural_models": 1,
            "missing_intraday": 2,
            "missing_lstm": 3,
            "weak_heads": 1,
            "overlay_generation": 1,
            "enhancement_phase": "done",
            "trainers_busy": [],
            "missing_intraday_sample": ["ZZ1"],
            "missing_lstm_sample": ["ZZ2"],
            "weak_sample": ["ZZ3"],
        }
        with patch("analytics.algo_generation.scan_upgrades", return_value=catalog):
            with patch("analytics.algo_generation.harvest_teachers", return_value=rows):
                payload = run_generation()
                names = [p["phase"] for p in payload["phases"]]
                self.assertEqual(names, list(PHASES))
                self.assertEqual(payload["n_phases"], 100)
                self.assertEqual(payload["phase_index"], 100)
                self.assertEqual(names[-1], "complete")
                self.assertEqual(payload["generation"], 1)
                self.assertTrue(payload.get("auc"))
                self.assertFalse((payload.get("complete") or {}).get("deployed"))
                payload2 = run_generation()
                self.assertEqual(payload2["generation"], 1)
                self.assertTrue(payload2.get("skipped_unchanged"))

    def test_overlay_boost_noop_when_staged(self):
        from analytics.algo_generation import algo_overlay_boost, overlay_path

        overlay_path().write_text('{"generation": 3, "live": false, "tilts": {"AAA": 0.1}}', encoding="utf-8")
        boost, info = algo_overlay_boost("AAA")
        self.assertEqual(boost, 0.0)
        self.assertTrue(info.get("staged"))

    def test_finalize_does_not_flip_live(self):
        from analytics.algo_generation import current_ptr, finalize

        out = finalize(generation=4, distill_meta={"auc_oos": 0.49, "auc_teacher_oos": 0.52, "deploy_ready": False})
        self.assertTrue(out.get("ok"))
        self.assertFalse(out.get("deployed"))
        self.assertFalse(current_ptr().is_file())

    def test_deploy_refuses_teacher_passthrough(self):
        from analytics.algo_generation import current_ptr, deploy

        (Path(self.tmp.name) / "algorithm").mkdir(parents=True, exist_ok=True)
        fake = Path(self.tmp.name) / "algorithm" / "gen_00007_algo.pkl"
        fake.write_bytes(b"passthrough")
        out = deploy(
            7,
            {
                "path": str(fake),
                "kind": "teacher",
                "deploy_ready": True,
                "auc_oos": 0.51556,
                "auc_teacher_oos": 0.51556,
            },
        )
        self.assertFalse(out.get("deployed"))
        self.assertEqual(out.get("note"), "refused_teacher_passthrough")
        self.assertFalse(current_ptr().is_file())

    def test_compact_keeps_running_totals_not_stale_dates(self):
        from analytics.algo_generation import compact_labeled_rows, harvest_moments

        rows = []
        for d in range(12):
            date = f"2026-07-{10 + d:02d}"
            rows.append({"ticker": "AAA", "signal_date": date, "y": 1, "fwd": 0.01, "p_up": 0.6})
            rows.append({"ticker": "BBB", "signal_date": date, "y": 0, "fwd": -0.01, "p_up": 0.4})
        compact = compact_labeled_rows(rows, keep_dates=8)
        dates = {r["signal_date"] for r in compact}
        self.assertEqual(len(dates), 8)
        self.assertLess(len(compact), len(rows))
        moments = harvest_moments(rows)
        self.assertEqual(moments["n"], 24)
        self.assertEqual(moments["n_tickers"], 2)

    def test_deploy_ignores_in_sample_auc(self):
        from analytics.algo_generation import current_ptr, deploy
        import json

        (Path(self.tmp.name) / "algorithm").mkdir(parents=True, exist_ok=True)
        current_ptr().write_text(
            json.dumps({"generation": 2, "path": "x", "auc": 0.905}),
            encoding="utf-8",
        )
        fake = Path(self.tmp.name) / "algorithm" / "gen_00008_algo.pkl"
        fake.write_bytes(b"ok")
        out = deploy(
            8,
            {
                "path": str(fake),
                "kind": "blend_hgb",
                "auc_oos": 0.55,
                "auc_teacher_oos": 0.51,
            },
        )
        self.assertTrue(out.get("deployed"), out)
        ptr = json.loads(current_ptr().read_text(encoding="utf-8"))
        self.assertEqual(ptr.get("generation"), 8)
        self.assertEqual(ptr.get("auc_oos"), 0.55)

    def test_deploy_refuses_when_oos_below_live(self):
        from analytics.algo_generation import current_ptr, deploy
        import json

        (Path(self.tmp.name) / "algorithm").mkdir(parents=True, exist_ok=True)
        live = Path(self.tmp.name) / "algorithm" / "gen_00002_algo.pkl"
        live.write_bytes(b"live")
        current_ptr().write_text(
            json.dumps({"generation": 2, "path": str(live), "auc": 0.905, "auc_oos": 0.60}),
            encoding="utf-8",
        )
        fake = Path(self.tmp.name) / "algorithm" / "gen_00009_algo.pkl"
        fake.write_bytes(b"worse")
        out = deploy(
            9,
            {
                "path": str(fake),
                "kind": "blend_hgb",
                "auc_oos": 0.55,
                "auc_teacher_oos": 0.51,
            },
        )
        self.assertFalse(out.get("deployed"), out)
        self.assertEqual(out.get("note"), "refused_oos_below_live")
        ptr = json.loads(current_ptr().read_text(encoding="utf-8"))
        self.assertEqual(ptr.get("generation"), 2)

    def test_complete_does_not_flip_live(self):
        from analytics.algo_generation import complete, current_ptr

        out = complete(
            generation=4,
            distill_meta={"auc_oos": 0.49, "auc_teacher_oos": 0.52, "deploy_ready": False},
            catalog={"missing_intraday": 3, "daily_models": 10},
            pipeline_meta={"hot": ["AAA"]},
            kick="queued_busy:train-intraday",
            n_phases=100,
        )
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("phase_index"), 100)
        self.assertFalse(out.get("deployed"))
        self.assertFalse(current_ptr().is_file())
        self.assertTrue(out.get("cover_is_teachers_not_algorithm"))
        self.assertTrue(out.get("algorithm_live_for_all_stocks"))


if __name__ == "__main__":
    unittest.main()
