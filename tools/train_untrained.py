#!/usr/bin/env python3
"""Audit + launch training for missing top-100 intraday/LSTM and broader LSTM gaps."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / "venv/bin/python"
RUN = ROOT / "run_all.sh"


def audit_gaps() -> dict:
    """Summary counts for self-maintenance / watchdog."""
    rep = _gap_report()
    return {
        "top100_daily_missing": len(rep.get("missing_daily") or []),
        "top100_intraday_missing": len(rep.get("missing_intraday_top100") or []),
        "top100_lstm_missing": len(rep.get("missing_lstm_top100") or []),
        "lstm_pending_active": len(rep.get("lstm_pending_active") or []),
        "raw": rep,
    }


def _gap_report() -> dict:
    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)

    from analytics.lstm_head import has_lstm_head
    from fortress_universe import has_trained_intraday_bundle, load_top100_symbols
    from model_trainer import training_saved_model
    from tools.train_lstm_heads import _pending_symbols

    top = load_top100_symbols()
    missing_daily = [s for s in top if not training_saved_model(s)]
    missing_intraday = [
        s for s in top if training_saved_model(s) and not has_trained_intraday_bundle(s)
    ]
    missing_lstm_top = [s for s in top if training_saved_model(s) and not has_lstm_head(s)]

    os.environ["LSTM_TRAIN_SCOPE"] = "top100"
    lstm_top_pending = _pending_symbols()
    os.environ["LSTM_TRAIN_SCOPE"] = "active"
    lstm_active_pending = _pending_symbols()

    return {
        "top100_count": len(top),
        "missing_daily": missing_daily,
        "missing_intraday_top100": missing_intraday,
        "missing_lstm_top100": missing_lstm_top,
        "lstm_pending_top100": lstm_top_pending,
        "lstm_pending_active": lstm_active_pending,
    }


def _write_symbols(path: Path, symbols: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(set(s.upper() for s in symbols if s)), indent=0), encoding="utf-8")


def _is_running(name: str) -> bool:
    r = subprocess.run([str(RUN), "status"], cwd=ROOT, capture_output=True, text=True, check=False)
    return f"{name}" in r.stdout and "RUNNING" in r.stdout.split(f"{name}")[1][:40]


def launch_training(*, lstm_scope_all: bool = True) -> int:
    rep = _gap_report()
    print("[train-untrained] gap audit:", flush=True)
    print(f"  top100 daily missing:     {len(rep['missing_daily'])} {rep['missing_daily'][:8]}", flush=True)
    print(f"  top100 intraday missing:  {len(rep['missing_intraday_top100'])} {rep['missing_intraday_top100'][:8]}", flush=True)
    print(f"  top100 LSTM missing:      {len(rep['missing_lstm_top100'])} {rep['missing_lstm_top100'][:8]}", flush=True)
    print(f"  LSTM pending (active):    {len(rep['lstm_pending_active'])}", flush=True)

    started = 0

    if rep["missing_daily"]:
        sym_file = ROOT / "data" / "train_untrained_daily.json"
        _write_symbols(sym_file, rep["missing_daily"])
        if not _is_running("train"):
            print("[train-untrained] launching daily gap-fill for top100…", flush=True)
            env = {
                **os.environ,
                "TRAIN_SYMBOLS_FILE": str(sym_file),
                "TRAIN_TOP100_ONLY": "true",
                # Honor the symbols file under --missing-only (otherwise ignored).
                "TRAIN_MISSING_USE_SYMBOLS_FILE": "true",
                # Gap-fill must train top100 — junk skip would leave megas empty forever.
                "TRAIN_JUNK_SKIP_TOP100": "false",
                "FRESH_MODEL_REBUILD": "false",
                "TRAIN_FORCE_YAHOO": "true",
                "NETWORK_FIRST": "true",
                "TRAIN_MISSING_WORKERS": os.environ.get("TOP100_DAILY_WORKERS", "4"),
            }
            subprocess.Popen([str(RUN), "train-missing-fast"], cwd=ROOT, env=env)
            started += 1
        else:
            print("[train-untrained] train already running — skip daily", flush=True)

    intra = rep["missing_intraday_top100"]
    if intra:
        sym_file = ROOT / "data" / "train_untrained_intraday.json"
        _write_symbols(sym_file, intra)
        if not _is_running("train-intraday"):
            print(f"[train-untrained] launching intraday for {len(intra)} top100 names…", flush=True)
            env = os.environ.copy()
            env.update(
                {
                    "TRAIN_SYMBOLS_FILE": str(sym_file),
                    "INTRADAY_LOOKBACK_DAYS": env.get("TOP100_INTRADAY_LOOKBACK", "365"),
                    "INTRADAY_GAP_SKIP_CACHED_PLACEHOLDER": "false",
                    "INTRADAY_GAP_WORKERS": env.get("TOP100_INTRADAY_WORKERS", "4"),
                }
            )
            subprocess.Popen([str(RUN), "train-intraday-proper"], cwd=ROOT, env=env)
            started += 1
        else:
            print("[train-untrained] train-intraday already running — skip", flush=True)

    lstm_top = rep["lstm_pending_top100"] or rep["missing_lstm_top100"]
    if lstm_top:
        if not _is_running("train-lstm"):
            print(f"[train-untrained] launching LSTM top100 ({len(lstm_top)} pending)…", flush=True)
            env = os.environ.copy()
            env.update(
                {
                    "LSTM_TRAIN_SCOPE": "top100",
                    "LSTM_WORKERS": env.get("TOP100_LSTM_WORKERS", "3"),
                    "LSTM_EPOCHS": env.get("TOP100_LSTM_EPOCHS", "16"),
                    "USE_LSTM_HEAD": "true",
                    "TRAIN_FORCE_YAHOO": "true",
                }
            )
            logf = ROOT / "logs" / f"train_lstm_top100_{os.getpid()}.log"
            with open(logf, "w", encoding="utf-8") as lf:
                subprocess.Popen(
                    [str(PY), "-u", "tools/train_lstm_heads.py"],
                    cwd=ROOT,
                    env=env,
                    stdout=lf,
                    stderr=subprocess.STDOUT,
                )
            print(f"[train-untrained] LSTM top100 → {logf}", flush=True)
            started += 1
        else:
            print("[train-untrained] train-lstm already running — skip top100 pass", flush=True)

    lstm_active = rep["lstm_pending_active"]
    if lstm_scope_all and len(lstm_active) > len(lstm_top):
        print(
            f"[train-untrained] LSTM active-universe backlog queued ({len(lstm_active)} names after top100)",
            flush=True,
        )
        env = os.environ.copy()
        env.update(
            {
                "LSTM_TRAIN_SCOPE": "active",
                "LSTM_WORKERS": env.get("LSTM_WORKERS", "4"),
                "LSTM_EPOCHS": env.get("LSTM_EPOCHS", "12"),
                "USE_LSTM_HEAD": "true",
            }
        )
        logf = ROOT / "logs" / "train_lstm_active_backlog.log"
        wait_cmd = (
            f'while pgrep -f "train_lstm_heads.py" >/dev/null 2>&1; do sleep 45; done; '
            f'cd "{ROOT}" && LSTM_TRAIN_SCOPE=active LSTM_WORKERS={env["LSTM_WORKERS"]} '
            f'USE_LSTM_HEAD=true {PY} -u tools/train_lstm_heads.py >>"{logf}" 2>&1'
        )
        subprocess.Popen(["/bin/bash", "-c", wait_cmd], cwd=ROOT, env=env)
        started += 1

    if started == 0:
        print("[train-untrained] nothing to launch — all targeted gaps already training or complete", flush=True)
    else:
        print("[train-untrained] started.  progress: ./run_all.sh progress", flush=True)
        print("  tail -f logs/train-intraday_latest.log logs/train-lstm_latest.log", flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Train missing top100 intraday/LSTM + LSTM backlog")
    ap.add_argument("--audit", action="store_true", help="Print gaps only")
    ap.add_argument("--launch", action="store_true", help="Start background trainers")
    ap.add_argument("--no-lstm-all", action="store_true", help="Skip LSTM active-universe backlog after top100")
    args = ap.parse_args()

    os.chdir(ROOT)
    if args.launch:
        return launch_training(lstm_scope_all=not args.no_lstm_all)
    rep = _gap_report()
    print(json.dumps(rep, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
