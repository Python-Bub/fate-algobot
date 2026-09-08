#!/usr/bin/env python3
"""One-hour finish: top-100 gaps, weak heads, tier-2, go-live paper open mode."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / "venv/bin/python"
LOG = ROOT / "logs" / "go_paper_open.log"


def _log(msg: str) -> None:
    line = f"{datetime.now(timezone.utc).isoformat()} {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _run(cmd: list[str], *, timeout: int | None = None) -> int:
    _log(f"[run] {' '.join(cmd[:4])}{'…' if len(cmd) > 4 else ''}")
    try:
        return subprocess.run(cmd, cwd=ROOT, timeout=timeout, check=False).returncode
    except subprocess.TimeoutExpired:
        _log(f"[run] TIMEOUT {' '.join(cmd[:3])}")
        return 124


def _missing_top100() -> list[str]:
    sys.path.insert(0, str(ROOT))
    from fortress_universe import load_top100_symbols
    from model_trainer import training_saved_model

    return [s for s in load_top100_symbols() if not training_saved_model(s)]


def _train_missing(*, fast: bool = True) -> None:
    missing = _missing_top100()
    if not missing:
        _log("[top100] all daily models present")
        return
    _log(f"[top100] training {len(missing)}: {', '.join(missing)}")
    if fast:
        os.environ["FAST_UNIVERSE_TRAIN"] = "true"
    from model_trainer import _train_single_ticker, training_saved_model

    for sym in missing:
        _log(f"[top100] {sym} start")
        try:
            ok = _train_single_ticker(sym)
            _log(f"[top100] {sym} saved={ok} disk={training_saved_model(sym)}")
        except Exception as e:
            _log(f"[top100] {sym} FAIL {e}")


def _finish_weak() -> None:
    sys.path.insert(0, str(ROOT))
    from tools.retrain_weak_models import find_weak_symbols

    weak = find_weak_symbols(min_top20=0.6, min_meta=0.52, top100_only=True)
    if not weak:
        _log("[weak] strict pass clear")
        return
    _log(f"[weak] {len(weak)} symbols — finish_weak_top100.py")
    rc = _run([str(PY), "-u", "tools/finish_weak_top100.py"], timeout=7200)
    still = find_weak_symbols(min_top20=0.52, min_meta=0.48, top100_only=True)
    _log(f"[weak] after finish rc={rc} still={list(still) if still else 'none'}")


def _tier2_drain() -> None:
    rc = _run([str(PY), "-u", "tools/tier2_retrain_queue.py", "--drain"], timeout=1800)
    _log(f"[tier2] drain rc={rc}")


def _go_live_paper() -> None:
    os.environ.setdefault("USE_REAL_MONEY", "false")
    os.environ.setdefault("BROKER", "alpaca")
    os.environ.setdefault("PAPER_USE_FORTRESS", "true")
    os.environ.setdefault("LONG_DECISION_THRESHOLD", "0.58")
    os.environ.setdefault("MIN_MODEL_CONFIDENCE", "0.65")
    _run([str(PY), "-u", "tools/sync_recent_trades.py"])
    _run([str(PY), "-u", "tools/repatch_paper_report_asym.py"])
    _run([str(PY), "-u", "tools/prune_disk.py"])
    _run(["./run_all.sh", "go-live-weekend"], timeout=180)
    _run([str(PY), "-u", "tools/stack_autotune.py", "--once"], timeout=300)


def _summary() -> int:
    sys.path.insert(0, str(ROOT))
    from tools.retrain_weak_models import find_weak_symbols

    missing = _missing_top100()
    weak = find_weak_symbols(min_top20=0.52, min_meta=0.48, top100_only=True)
    _log("=== SUMMARY ===")
    _log(f"  top100 missing: {missing or 'none'}")
    _log(f"  weak: {list(weak) if weak else 'none'}")
    _run([str(PY), "-u", "tools/health_check.py"])
    return 1 if (missing or weak) else 0


def main() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("TRAIN_PRIORITIZE", "top100")
    from data_platform.market_prices import configure_process_prices

    configure_process_prices(training=True)
    os.environ.setdefault("USE_LLM_SIGNAL", "true")
    os.environ.setdefault("NEWS_LLM_NO_HEADLINE_FALLBACK", "true")

    _log("=== go-paper-open START ===")
    _train_missing(fast=True)
    _finish_weak()
    _tier2_drain()
    _go_live_paper()
    rc = _summary()
    _log(f"=== go-paper-open END rc={rc} ===")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
