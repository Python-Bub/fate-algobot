#!/usr/bin/env python3
"""Fill blank / weak / placeholder heads without blacklisting symbols.

Pipeline:
  features → models (this refill) → rank_pipeline → risk → execution

Scopes: top100 | top50pct | active | promoted | all
Never deletes models; overwrites weak/blank checkpoints with real training.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / "venv" / "bin" / "python"


def _scope_symbols(scope: str) -> list[str]:
    sys.path.insert(0, str(ROOT))
    from fortress_universe import (
        load_top100_symbols,
        load_top50pct_symbols,
        symbols_paper_active_universe,
        symbols_with_daily_models,
    )
    from model_trainer import training_saved_model

    scope = scope.lower().strip()
    if scope in ("top100", "mega"):
        return load_top100_symbols()
    if scope in ("top50", "top50pct", "half"):
        return load_top50pct_symbols()
    if scope in ("promoted", "fisher", "bottom_promote"):
        p = ROOT / "data" / "bottom_fisher_promoted.json"
        if p.is_file():
            try:
                return list(json.loads(p.read_text(encoding="utf-8")).get("symbols") or [])
            except Exception:
                return []
        return []
    if scope in ("active", "paper"):
        return symbols_paper_active_universe()
    # all modeled + top50 union — never shrink
    pool = set(symbols_with_daily_models()) | set(load_top50pct_symbols()[:2000])
    return sorted(s for s in pool if training_saved_model(s) or True)[: int(os.getenv("FILL_HEADS_MAX", "3000"))]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", default=os.getenv("FILL_HEADS_SCOPE", "top50pct"))
    ap.add_argument("--daily", action="store_true", default=True)
    ap.add_argument("--no-daily", action="store_true")
    ap.add_argument("--lstm", action="store_true", default=True)
    ap.add_argument("--no-lstm", action="store_true")
    ap.add_argument("--intraday", action="store_true", default=False)
    ap.add_argument("--limit", type=int, default=int(os.getenv("FILL_HEADS_LIMIT", "200")))
    args = ap.parse_args()
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))

    from utils import log

    syms = _scope_symbols(args.scope)[: max(1, args.limit)]
    log.info("[FILL_HEADS] scope=%s n=%d", args.scope, len(syms))
    if not syms:
        return 0

    batch = ROOT / "data" / "fill_blank_heads_batch.json"
    batch.write_text(json.dumps(syms), encoding="utf-8")
    env = os.environ.copy()
    env.update(
        {
            "TRAIN_SYMBOLS_FILE": str(batch),
            "INTRADAY_GAP_SKIP_CACHED_PLACEHOLDER": "false",
            "LSTM_REQUEUE_WEAK": "true",
            "LSTM_MIN_TEST_ACC": env.get("LSTM_MIN_TEST_ACC", "0.45"),
            "LSTM_SKIP_PERMANENT_FAILED": "false",
            "TRAIN_FORCE_YAHOO": "true",
            "USE_LSTM_HEAD": "true",
        }
    )

    if args.lstm and not args.no_lstm:
        subprocess.call(
            [str(PY), "-u", "tools/audit_lstm_heads.py", "--requeue", "--min-acc", env["LSTM_MIN_TEST_ACC"]],
            cwd=ROOT,
            env=env,
        )
        env["LSTM_TRAIN_SCOPE"] = "all" if args.scope == "all" else "top50pct" if "50" in args.scope else "active"
        # Background-friendly: launch via run_all if not running
        subprocess.Popen(
            [str(ROOT / "run_all.sh"), "train-lstm"],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        log.info("[FILL_HEADS] train-lstm launched for weak/blank LSTM heads")

    if args.daily and not args.no_daily:
        from model_trainer import training_saved_model

        missing = [s for s in syms if not training_saved_model(s)]
        if missing:
            batch.write_text(json.dumps(missing[: args.limit]), encoding="utf-8")
            subprocess.Popen(
                [
                    str(PY),
                    "-u",
                    "parallel_train.py",
                    "--pipeline",
                    "daily",
                    "--missing-only",
                    "--workers",
                    os.getenv("FILL_HEADS_WORKERS", "3"),
                ],
                cwd=ROOT,
                env=env,
                stdout=open(ROOT / "logs" / "fill_blank_daily.log", "a"),
                stderr=subprocess.STDOUT,
            )
            log.info("[FILL_HEADS] daily missing-only launched for %d symbols", len(missing))
        else:
            log.info("[FILL_HEADS] all scoped symbols already have daily models")

    if args.intraday:
        env["INTRADAY_GAP_SKIP_CACHED_PLACEHOLDER"] = "false"
        subprocess.Popen(
            [str(ROOT / "run_all.sh"), "train-intraday"],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        log.info("[FILL_HEADS] train-intraday launched (placeholders will be overwritten)")

    # AI IPO proxies + promoted overlay — advanced stack
    if os.getenv("AI_IPO_ADVANCED_TRAIN", "true").lower() in ("1", "true", "yes"):
        try:
            from tools.ai_ipo_autopilot import bootstrap

            out = bootstrap(train=True)
            log.info("[FILL_HEADS] ai_ipo bootstrap %s", {k: out.get(k) for k in ("proxies", "ipo_queued", "advanced")})
        except Exception as e:
            log.warning("[FILL_HEADS] ai_ipo: %s", e)

    print(json.dumps({"scope": args.scope, "n": len(syms), "batch": str(batch)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
