#!/usr/bin/env python3
"""Final loose-end sweep: SHOP/T strong retrain, tier2, smoke, stack refresh."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / "venv/bin/python"


def _run(label: str, cmd: list[str], *, timeout: int | None = None) -> int:
    print(f"\n[finish-loose] === {label} ===", flush=True)
    try:
        return subprocess.run(cmd, cwd=ROOT, timeout=timeout, check=False).returncode
    except subprocess.TimeoutExpired:
        print(f"[finish-loose] TIMEOUT {label}", flush=True)
        return 124


def _strong_symbol(sym: str, *, min_top20: float, min_meta: float, attempts: int = 8) -> bool:
    env = os.environ.copy()
    env.update(
        {
            "STRONG_BACKENDS": "xgb,lgb",
            "STRONG_ATTEMPTS_PER_SYMBOL": str(attempts),
            "TRAIN_TICKER_TIMEOUT_SEC": "0",
        }
    )
    rc = subprocess.run(
        [
            str(PY),
            "-u",
            "tools/retrain_top100_strong.py",
            "--ticker",
            sym,
            "--min-top20",
            str(min_top20),
            "--min-meta",
            str(min_meta),
        ],
        cwd=ROOT,
        env=env,
        check=False,
    ).returncode
    sys.path.insert(0, str(ROOT))
    from tools.retrain_weak_models import find_weak_symbols

    still = sym in find_weak_symbols(min_top20=min_top20, min_meta=min_meta, top100_only=True)
    print(f"[finish-loose] {sym} rc={rc} still_weak={still}", flush=True)
    return not still


def main() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("TRAIN_PRIORITIZE", "top100")

    sys.path.insert(0, str(ROOT))
    from fortress_universe import load_top100_symbols
    from model_trainer import training_saved_model
    from tools.retrain_weak_models import find_weak_symbols

    missing = [s for s in load_top100_symbols() if not training_saved_model(s)]
    if missing:
        print(f"[finish-loose] WARN top100 missing: {missing}", flush=True)

    relax = find_weak_symbols(min_top20=0.52, min_meta=0.48, top100_only=True)
    if relax:
        for sym in list(relax.keys()):
            _strong_symbol(sym, min_top20=0.52, min_meta=0.48, attempts=8)
            if sym == "T":
                _strong_symbol(sym, min_top20=0.48, min_meta=0.45, attempts=5)

    # Tier2 after strong pass — avoids overwriting freshly fixed top100 bundles.
    _run("tier2_drain", [str(PY), "-u", "tools/tier2_retrain_queue.py", "--drain"], timeout=1800)

    # Re-verify top100 relaxed weak after tier2 (tier2 can downgrade quality).
    relax = find_weak_symbols(min_top20=0.52, min_meta=0.48, top100_only=True)
    for sym in list(relax.keys()):
        _strong_symbol(sym, min_top20=0.52, min_meta=0.48, attempts=6)
    _run("sync", [str(PY), "-u", "tools/sync_recent_trades.py"])
    _run("repatch", [str(PY), "-u", "tools/repatch_paper_report_asym.py"])
    _run("cleaner", [str(PY), "-u", "tools/change_cleaner.py", "--reason", "finish_loose_ends"])
    _run("smoke", [str(PY), "-u", "tools/smoke_launch.py"], timeout=900)
    _run("health", [str(PY), "-u", "tools/health_check.py"])
    _run("autotune", [str(PY), "-u", "tools/stack_autotune.py", "--once"], timeout=300)
    _run("launch_refresh", ["./run_all.sh", "refresh-paper"], timeout=120)

    relax = find_weak_symbols(min_top20=0.52, min_meta=0.48, top100_only=True)
    missing = [s for s in load_top100_symbols() if not training_saved_model(s)]
    print("\n[finish-loose] === DONE ===", flush=True)
    print(f"  top100 missing: {missing or 'none'}", flush=True)
    print(f"  weak relaxed: {list(relax) if relax else 'none'}", flush=True)
    return 1 if (missing or relax) else 0


if __name__ == "__main__":
    raise SystemExit(main())
