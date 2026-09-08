#!/usr/bin/env python3
"""Keep full-universe intraday parallel_train alive — restart when pid dies or log stalls.

Does not shrink to top50. Stall window is long enough for a real ticker (AER ~4 min).
"""

from __future__ import annotations

import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PID = ROOT / ".pids" / "train-intraday.pid"
LOG = ROOT / "logs" / "train-intraday_latest.log"
WLOG = ROOT / "logs" / "intraday_train_watchdog.log"
# Real intraday fits can take >3 min; 180s was killing healthy workers.
STALL_SEC = int(os.getenv("INTRADAY_WATCHDOG_STALL_SEC", "1200"))
POLL_SEC = int(os.getenv("INTRADAY_WATCHDOG_POLL_SEC", "45"))
PY = ROOT / "venv" / "bin" / "python"


def _log(msg: str) -> None:
    line = f"[{datetime.now(timezone.utc).isoformat()}] {msg}\n"
    WLOG.parent.mkdir(parents=True, exist_ok=True)
    with WLOG.open("a", encoding="utf-8") as f:
        f.write(line)
    print(line, end="")


def _pid_alive() -> bool:
    if not PID.is_file():
        return False
    try:
        os.kill(int(PID.read_text().strip()), 0)
        return True
    except (OSError, ValueError):
        return False


def _log_mtime() -> float | None:
    try:
        return LOG.stat().st_mtime if LOG.is_file() else None
    except OSError:
        return None


def _restart() -> None:
    _log("restarting train-intraday (full universe, missing-only, no top50 shrink)")
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(ROOT),
            "TRAIN_TOP50_ONLY": "false",
            "TRAIN_TOP100_ONLY": "false",
            "TRAIN_SYMBOLS_FILE": "",
            "TRAIN_MISSING_USE_SYMBOLS_FILE": "false",
            "INTRADAY_USE_POLYGON_FALLBACK": "true",
            "INTRADAY_LOOKBACK_DAYS": os.getenv("INTRADAY_LOOKBACK_DAYS", "365"),
            "INTRADAY_GAP_SKIP_CACHED_PLACEHOLDER": os.getenv(
                "INTRADAY_GAP_SKIP_CACHED_PLACEHOLDER", "false"
            ),
            "NETWORK_FIRST": os.getenv("NETWORK_FIRST", "true"),
            "ALPACA_HAS_SIP": os.getenv("ALPACA_HAS_SIP", "false"),
        }
    )
    cmd = [
        str(PY if PY.is_file() else "python3"),
        "-u",
        str(ROOT / "parallel_train.py"),
        "--pipeline",
        "intraday",
        "--missing-only",
        "--workers",
        os.getenv("INTRADAY_GAP_WORKERS", "6"),
    ]
    LOG.parent.mkdir(parents=True, exist_ok=True)
    PID.parent.mkdir(parents=True, exist_ok=True)
    logf = ROOT / "logs" / f"train-intraday_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    try:
        if LOG.is_symlink() or LOG.exists():
            LOG.unlink()
    except OSError:
        pass
    try:
        LOG.symlink_to(logf)
    except OSError:
        pass
    with logf.open("a", encoding="utf-8") as lf:
        proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=lf, stderr=subprocess.STDOUT)
    PID.write_text(str(proc.pid), encoding="utf-8")


def main() -> int:
    _log("intraday_train_watchdog started")
    last_mtime = _log_mtime()
    last_change = time.time()
    while True:
        time.sleep(POLL_SEC)
        if not _pid_alive():
            _restart()
            last_mtime = _log_mtime()
            last_change = time.time()
            continue
        mt = _log_mtime()
        if mt is None:
            continue
        if last_mtime is None or mt > last_mtime + 0.5:
            last_mtime = mt
            last_change = time.time()
            continue
        if time.time() - last_change >= STALL_SEC:
            _log("stall detected")
            try:
                os.kill(int(PID.read_text().strip()), 15)
            except Exception:
                pass
            time.sleep(3)
            try:
                os.kill(int(PID.read_text().strip()), 9)
            except Exception:
                pass
            _restart()
            last_mtime = _log_mtime()
            last_change = time.time()


if __name__ == "__main__":
    raise SystemExit(main())
