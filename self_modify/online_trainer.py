"""
Traditional + online AI training orchestration for the free agent.

Triggers real trainers (LSTM, intraday gaps, neural ensemble online learning)
without blocking the trading stack indefinitely.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = Path("data/agi/training_log.jsonl")

ALLOWED_TRAIN_COMMANDS = frozenset(
    {
        "train-lstm",
        "train-gaps",
        "train-100gb",
        "train-top50",
        "ensure-training",
        "retrain-weak-until",
        "self-improve-once",
    }
)


def _log(event: str, payload: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    rec = {"ts_utc": datetime.now(timezone.utc).isoformat(), "event": event, **payload}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, sort_keys=True) + "\n")


def memory_guard(min_avail_gb: float | None = None) -> dict[str, Any]:
    """Return {'ok': bool, 'avail_gb': float, 'pct': float}. Heavy trainers must
    never be spawned when free RAM is low — on this memory-constrained Mac that
    triggers jetsam, which SIGKILLs the whole free-agent process group."""
    floor = float(os.getenv("FREE_AGENT_MIN_AVAIL_GB", "4.0")) if min_avail_gb is None else min_avail_gb
    try:
        import psutil

        vm = psutil.virtual_memory()
        avail_gb = vm.available / 1e9
        return {"ok": avail_gb >= floor, "avail_gb": round(avail_gb, 2), "pct": vm.percent, "floor_gb": floor}
    except Exception:
        # If we cannot measure, be conservative and allow (caller still detaches).
        return {"ok": True, "avail_gb": -1.0, "pct": -1.0, "floor_gb": floor}


def _run_bg(cmd: str) -> dict[str, Any]:
    if cmd not in ALLOWED_TRAIN_COMMANDS:
        return {"ok": False, "reason": f"train_cmd_blocked:{cmd}"}
    mem = memory_guard()
    if not mem["ok"]:
        _log("train_skipped_low_mem", {"cmd": cmd, **mem})
        return {"ok": False, "reason": "low_memory", "cmd": cmd, **mem}
    script = ROOT / "run_all.sh"
    logf = ROOT / "logs" / f"free_agent_{cmd.replace('-', '_')}.log"
    try:
        with logf.open("a", encoding="utf-8") as lf:
            lf.write(f"\n--- {datetime.now(timezone.utc).isoformat()} free_agent launch {cmd} ---\n")
        proc = subprocess.Popen(
            [str(script), cmd],
            cwd=ROOT,
            stdout=logf.open("a"),
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        _log("train_launched", {"cmd": cmd, "pid": proc.pid, "log": str(logf)})
        return {"ok": True, "cmd": cmd, "pid": proc.pid, "log": str(logf)}
    except Exception as e:
        return {"ok": False, "cmd": cmd, "reason": str(e)[:200]}


def _run_py_bg(script_rel: str, *args: str) -> dict[str, Any]:
    """Launch a project python script fully detached (own session) so heavy
    work (e.g. torch training) cannot OOM-kill the calling daemon."""
    mem = memory_guard()
    if not mem["ok"]:
        _log("py_skipped_low_mem", {"script": script_rel, **mem})
        return {"ok": False, "reason": "low_memory", "script": script_rel, **mem}
    py = os.environ.get("FATE_PYTHON") or str(ROOT / "venv" / "bin" / "python")
    if not Path(py).exists():
        py = "python3"
    script = ROOT / script_rel
    logf = ROOT / "logs" / f"free_agent_{Path(script_rel).stem}.log"
    try:
        logf.parent.mkdir(parents=True, exist_ok=True)
        with logf.open("a", encoding="utf-8") as lf:
            lf.write(f"\n--- {datetime.now(timezone.utc).isoformat()} free_agent launch {script_rel} {' '.join(args)} ---\n")
        proc = subprocess.Popen(
            [py, "-u", str(script), *args],
            cwd=ROOT,
            stdout=open(logf, "a"),
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        _log("py_launched", {"script": script_rel, "pid": proc.pid, "log": str(logf)})
        return {"ok": True, "script": script_rel, "pid": proc.pid, "log": str(logf)}
    except Exception as e:
        return {"ok": False, "script": script_rel, "reason": str(e)[:200]}


def train_neural_online(*, max_tickers: int | None = None) -> dict[str, Any]:
    """Launch neural-ensemble online training as a DETACHED subprocess.

    Heavy PyTorch work must never run inside the free-agent daemon process — a
    memory spike there gets the whole agent SIGKILL'd silently. The actual
    training runs in tools/neural_online_once.py via _train_neural_online_inproc.
    """
    n = max_tickers or int(os.getenv("FREE_AGENT_NEURAL_TICKERS", "12"))
    return _run_py_bg("tools/neural_online_once.py", f"--tickers={n}")


def _train_neural_online_inproc(*, max_tickers: int | None = None) -> dict[str, Any]:
    """Bootstrap replay + incremental PyTorch ensemble training (in-process).

    Only call this from a standalone/detached process (tools/neural_online_once.py),
    never directly from the free-agent daemon loop.
    """
    n = max_tickers or int(os.getenv("FREE_AGENT_NEURAL_TICKERS", "12"))
    out: dict[str, Any] = {"ok": True, "trained": [], "errors": []}
    seeded = 0
    try:
        from online_learning.neural_ensemble import (
            bootstrap_replay_from_reports,
            train_neural_ensemble_for_ticker,
            use_neural_ensemble,
        )

        if not use_neural_ensemble():
            return {"ok": False, "reason": "neural_ensemble_disabled"}
        seeded = int(
            bootstrap_replay_from_reports(max_files=int(os.getenv("NEURAL_BOOTSTRAP_DAYS", "21")))
        )
        out["replay_seeded"] = seeded
    except Exception as e:
        out["errors"].append(f"bootstrap:{e}")
        return out

    tickers: list[str] = []
    try:
        from fortress_universe import load_active_universe

        tickers = list(load_active_universe())[:n]
    except Exception:
        tickers = ["SPY", "QQQ", "AAPL", "NVDA", "MSFT"][:n]

    for t in tickers:
        try:
            rep = train_neural_ensemble_for_ticker(t)
            if rep:
                out["trained"].append(t)
        except Exception as e:
            out["errors"].append(f"{t}:{e}")
    out["ok"] = len(out["trained"]) > 0 or seeded > 0
    _log("neural_online", out)
    return out


def train_lstm_batch(*, scope: str | None = None) -> dict[str, Any]:
    return _run_bg("train-lstm")


def train_intraday_gaps() -> dict[str, Any]:
    return _run_bg("train-gaps")


def train_full_stack() -> dict[str, Any]:
    return _run_bg("train-100gb")


def retrain_weak_background() -> dict[str, Any]:
    return _run_bg("retrain-weak-until")


def execute_train_action(action: str) -> dict[str, Any]:
    mapping = {
        "train_lstm": train_lstm_batch,
        "train_gaps": train_intraday_gaps,
        "train_100gb": train_full_stack,
        "train_neural": lambda: train_neural_online(),
        "retrain_weak": retrain_weak_background,
        "self_improve": lambda: _run_bg("self-improve-once"),
    }
    fn = mapping.get(action)
    if not fn:
        return {"ok": False, "reason": f"unknown_train_action:{action}"}
    return {"action": action, **fn()}
