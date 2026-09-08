#!/usr/bin/env python3
"""Watch enhancement-queue phase changes and append alerts to logs/phase_watch.log."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "enhancement_queue_state.json"
LOG = ROOT / "logs" / "phase_watch.log"
POLL_SEC = int(os.getenv("PHASE_WATCH_POLL_SEC", "45"))


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _read_phase() -> str:
    if not STATE.is_file():
        return "unknown"
    try:
        return str(json.loads(STATE.read_text(encoding="utf-8")).get("phase", "unknown"))
    except Exception:
        return "unknown"


def _train_running() -> bool:
    pid_dir = ROOT / "pids"
    for name in ("train.pid",):
        p = pid_dir / name
        if not p.is_file():
            continue
        try:
            pid = int(p.read_text().strip())
            os.kill(pid, 0)
            return True
        except (OSError, ValueError):
            pass
    return False


def _append(msg: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"[{_now()}] {msg}\n"
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line)
    print(line, end="")


def main() -> int:
    last = _read_phase()
    _append(f"phase_watch started — current phase: {last}")
    while True:
        time.sleep(POLL_SEC)
        phase = _read_phase()
        if phase != last:
            train = "train=running" if _train_running() else "train=stopped"
            _append(f"PHASE CHANGE: {last} → {phase}  ({train})")
            last = phase
            if phase == "done":
                _append("QUEUE COMPLETE — proper finish done")
                return 0


if __name__ == "__main__":
    raise SystemExit(main())
