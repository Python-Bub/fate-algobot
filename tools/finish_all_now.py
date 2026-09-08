#!/usr/bin/env python3
"""One-shot finish: missing top-100 daily models → weak clear → health → stack refresh."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / "venv/bin/python"


def _run(label: str, cmd: list[str], *, timeout: int | None = None) -> int:
    print(f"\n[finish-all-now] === {label} ===", flush=True)
    try:
        return subprocess.run(cmd, cwd=ROOT, timeout=timeout, check=False).returncode
    except subprocess.TimeoutExpired:
        print(f"[finish-all-now] TIMEOUT: {label}", flush=True)
        return 124


def _missing_top100() -> list[str]:
    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)
    from fortress_universe import load_top100_symbols
    from model_trainer import training_saved_model

    return [s for s in load_top100_symbols() if not training_saved_model(s)]


def _train_missing_top100() -> int:
    missing = _missing_top100()
    if not missing:
        print("[finish-all-now] top-100 daily models complete", flush=True)
        return 0
    print(f"[finish-all-now] training {len(missing)} missing top-100: {', '.join(missing)}", flush=True)
    from model_trainer import _train_single_ticker, training_saved_model

    failed = 0
    for sym in missing:
        print(f"[finish-all-now] daily {sym} …", flush=True)
        try:
            ok = _train_single_ticker(sym)
            if not ok or not training_saved_model(sym):
                failed += 1
                print(f"[finish-all-now] WARN {sym} no model saved", flush=True)
            else:
                print(f"[finish-all-now] OK {sym}", flush=True)
        except Exception as e:
            failed += 1
            print(f"[finish-all-now] FAIL {sym}: {e}", flush=True)
    return 1 if failed else 0


def _clear_calib_checkpoint_failures() -> None:
    cp = ROOT / "data/train_checkpoint.json"
    if not cp.is_file():
        return
    try:
        data = json.loads(cp.read_text(encoding="utf-8"))
    except Exception:
        return
    failed = data.get("failed") or {}
    if not isinstance(failed, dict):
        return
    new_failed = {k: v for k, v in failed.items() if "fitted_" not in str(v)}
    if len(new_failed) != len(failed):
        data["failed"] = new_failed
        cp.write_text(json.dumps(data, indent=0), encoding="utf-8")
        print(f"[finish-all-now] cleared {len(failed) - len(new_failed)} calib failures from checkpoint", flush=True)


def main() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("TRAIN_PRIORITIZE", "top100")
    from data_platform.market_prices import configure_process_prices

    configure_process_prices(training=True)

    rc = 0
    _clear_calib_checkpoint_failures()
    rc |= _train_missing_top100()

    print("\n[finish-all-now] weak top-100 strong retrain (strict then relaxed) …", flush=True)
    rc |= _run("finish_weak_top100", [str(PY), "-u", "tools/finish_weak_top100.py"], timeout=7200)

    rc |= _run("health_check", [str(PY), "-u", "tools/health_check.py"])
    rc |= _run("sync_trades", [str(PY), "-u", "tools/sync_recent_trades.py"])
    rc |= _run("repatch_asym", [str(PY), "-u", "tools/repatch_paper_report_asym.py"])
    rc |= _run("autotune_once", [str(PY), "-u", "tools/stack_autotune.py", "--once"])
    rc |= _run("go_live", ["./run_all.sh", "go-live-weekend"], timeout=120)

    # Tier-2 queue: inference failures / non-megacap weak names train after top-100.
    rc |= _run("tier2_drain", [str(PY), "-u", "tools/tier2_retrain_queue.py", "--drain"], timeout=3600)

    sys.path.insert(0, str(ROOT))
    from tools.retrain_weak_models import find_weak_symbols

    weak = find_weak_symbols(min_top20=0.52, min_meta=0.48, top100_only=True)
    missing = _missing_top100()
    print("\n[finish-all-now] === SUMMARY ===", flush=True)
    print(f"  top100 missing daily: {missing or 'none'}", flush=True)
    print(f"  weak after relaxed pass: {list(weak) if weak else 'none'}", flush=True)
    return 1 if (missing or weak) else rc


if __name__ == "__main__":
    raise SystemExit(main())
