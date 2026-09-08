#!/usr/bin/env python3
"""Auto-restart daily train if log stops moving (parallel_train hang recovery)."""
from __future__ import annotations

import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PID = ROOT / ".pids" / "train.pid"
LOG = ROOT / "logs" / "train_latest.log"
WLOG = ROOT / "logs" / "train_watchdog.log"
STALL_SEC = int(os.getenv("TRAIN_WATCHDOG_STALL_SEC", "120"))
POLL_SEC = int(os.getenv("TRAIN_WATCHDOG_POLL_SEC", "60"))


def _log(msg: str) -> None:
    line = f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}] {msg}\n"
    WLOG.parent.mkdir(parents=True, exist_ok=True)
    with WLOG.open("a", encoding="utf-8") as f:
        f.write(line)
    print(line, end="")


def _train_pid() -> int | None:
    if not PID.is_file():
        return None
    try:
        pid = int(PID.read_text(encoding="utf-8").strip())
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError):
        return None


def _log_mtime() -> float | None:
    try:
        p = LOG.resolve() if LOG.is_file() else LOG
        if not p.is_file():
            return None
        return p.stat().st_mtime
    except OSError:
        return None


def _restart_train() -> None:
    _log("STALL detected — restarting train-missing-proper")
    pid = _train_pid()
    if pid:
        os.kill(pid, 15)
        time.sleep(2)
        try:
            os.kill(pid, 9)
        except OSError:
            pass
    subprocess.run(["./run_all.sh", "train-missing-proper"], cwd=ROOT, check=False)


def main() -> int:
    _log("train_watchdog started")
    last_mtime = _log_mtime()
    last_change = time.time()
    while True:
        time.sleep(POLL_SEC)
        pid = _train_pid()
        if not pid:
            continue
        mt = _log_mtime()
        if mt is None:
            continue
        if last_mtime is None or mt > last_mtime + 0.5:
            last_mtime = mt
            last_change = time.time()
            continue
        stalled = time.time() - last_change
        if stalled >= STALL_SEC:
            _restart_train()
            last_mtime = _log_mtime()
            last_change = time.time()


if __name__ == "__main__":
    raise SystemExit(main())
