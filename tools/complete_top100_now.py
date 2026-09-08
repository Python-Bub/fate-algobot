#!/usr/bin/env python3
"""Fast completion: remaining top-100 daily gaps + last weak symbol + stack refresh."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / "venv/bin/python"


def main() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    os.environ["TRAIN_PRIORITIZE"] = "top100"
    from data_platform.market_prices import configure_process_prices

    configure_process_prices(training=True)
    os.environ.setdefault("FAST_UNIVERSE_TRAIN", "false")

    from fortress_universe import load_top100_symbols
    from model_trainer import _train_single_ticker, training_saved_model
    from tools.retrain_weak_models import find_weak_symbols

    missing = [s for s in load_top100_symbols() if not training_saved_model(s)]
    if missing:
        print(f"[complete] daily gaps ({len(missing)}): {', '.join(missing)}", flush=True)
        for sym in missing:
            print(f"[complete] training {sym} …", flush=True)
            try:
                ok = _train_single_ticker(sym)
                print(f"[complete] {sym} saved={ok} on_disk={training_saved_model(sym)}", flush=True)
            except Exception as e:
                print(f"[complete] {sym} FAIL: {e}", flush=True)

    weak = find_weak_symbols(min_top20=0.6, min_meta=0.52, top100_only=True)
    if not weak:
        weak = find_weak_symbols(min_top20=0.52, min_meta=0.48, top100_only=True)
    if weak:
        print(f"[complete] weak ({len(weak)}): {', '.join(weak)}", flush=True)
        from tools.retrain_top100_strong import run_until_clear

        os.environ.setdefault("STRONG_N_EST", "400")
        os.environ.setdefault("STRONG_BACKENDS", "xgb,lgb")
        rc = run_until_clear(
            min_top20=0.52,
            min_meta=0.48,
            max_rounds=5,
            max_attempts_per_symbol=3,
        )
        if rc != 0:
            print("[complete] some weak symbols remain after relaxed pass", flush=True)

    for label, cmd in (
        ("health", [str(PY), "-u", "tools/health_check.py"]),
        ("sync", [str(PY), "-u", "tools/sync_recent_trades.py"]),
        ("repatch", [str(PY), "-u", "tools/repatch_paper_report_asym.py"]),
        ("autotune", [str(PY), "-u", "tools/stack_autotune.py", "--once"]),
    ):
        print(f"[complete] {label} …", flush=True)
        subprocess.run(cmd, cwd=ROOT, check=False)

    subprocess.run(["./run_all.sh", "go-live-weekend"], cwd=ROOT, check=False)

    missing = [s for s in load_top100_symbols() if not training_saved_model(s)]
    weak = find_weak_symbols(min_top20=0.52, min_meta=0.48, top100_only=True)
    print("\n[complete] === DONE ===", flush=True)
    print(f"  top100 missing: {missing or 'none'}", flush=True)
    print(f"  weak: {list(weak) if weak else 'none'}", flush=True)
    return 1 if (missing or weak) else 0


if __name__ == "__main__":
    raise SystemExit(main())
