#!/usr/bin/env python3
"""100-phase algorithm pipeline daemon.

  ./venv/bin/python tools/algo_pipeline.py --once
  ./run_all.sh algo-pipeline

Each cycle: 9 waves × (scan → cover → harvest → distill → pipeline → quality →
fuse → deploy → batch → advance → finalize) + complete (phase 100).
Never deletes ticker models. Live rank only flips when freeze-train OOS beats
teacher AND live auc_oos (never in-sample auc). Cover is a teacher-pickle
backlog — the live algorithm already scores every ticker from features.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
    _scale = ROOT / "data" / "deploy_scale.env"
    if _scale.is_file():
        load_dotenv(_scale, override=True)
except Exception:
    pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()
    pause = float(os.getenv("ALGO_PIPELINE_LOOP_SEC", "180"))

    from analytics.algo_generation import PHASES, pipeline_lock_path, run_generation

    lock_f = None
    try:
        lock_path = pipeline_lock_path()
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_f = lock_path.open("a+", encoding="utf-8")
        try:
            import fcntl

            fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            print(json.dumps({"ok": False, "note": "skipped_locked"}), flush=True)
            return 0
        while True:
            payload = run_generation()
            print(
                json.dumps(
                    {
                        "phases": list(PHASES),
                        "n_phases": payload.get("n_phases") or len(PHASES),
                        "phase_index": payload.get("phase_index"),
                        "generation": payload.get("generation"),
                        "auc": payload.get("auc"),
                        "n_rows": payload.get("n_rows"),
                        "batch": payload.get("batch"),
                        "kick": payload.get("kick"),
                        "skipped_unchanged": payload.get("skipped_unchanged"),
                    },
                    indent=2,
                ),
                flush=True,
            )
            if args.once:
                return 0
            time.sleep(max(45.0, pause))
    finally:
        if lock_f is not None:
            try:
                import fcntl

                fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
            try:
                lock_f.close()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
