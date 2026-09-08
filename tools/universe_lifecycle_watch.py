#!/usr/bin/env python3
"""Background watch: run universe maintenance on schedule (monthly full, weekly light)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / "venv" / "bin" / "python"
STATE = ROOT / "data" / "universe_lifecycle_state.json"
LOG = ROOT / "logs" / "universe_lifecycle_watch.log"
POLL_SEC = int(os.getenv("UNIVERSE_LIFECYCLE_POLL_SEC", "3600"))


def _log(msg: str) -> None:
    line = f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}] {msg}\n"
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line)
    print(line, end="")


def _load_state() -> dict:
    if not STATE.is_file():
        return {}
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _days_since(key: str) -> float:
    st = _load_state()
    ts = st.get(key)
    if not ts:
        return 9999.0
    try:
        then = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - then).total_seconds() / 86400.0
    except Exception:
        return 9999.0


def _run_maintenance(mode: str, extra: list[str] | None = None) -> int:
    cmd = [str(PY), "-u", "tools/universe_monthly_maintenance.py", "--mode", mode] + (extra or [])
    _log(f"starting maintenance mode={mode}")
    rc = subprocess.call(cmd, cwd=ROOT, env=os.environ.copy())
    _log(f"maintenance finished rc={rc}")
    return rc


def main() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    _log("universe_lifecycle_watch started")

    monthly_days = float(os.getenv("UNIVERSE_MONTHLY_DAYS", "28"))
    weekly_days = float(os.getenv("UNIVERSE_WEEKLY_DAYS", "7"))

    while True:
        try:
            if _days_since("last_maintenance_utc") >= monthly_days:
                _run_maintenance("monthly")
            elif _days_since("last_sync_utc") >= weekly_days:
                _run_maintenance("weekly", ["--skip-train"])
            else:
                # Light: IPO listing watch between full cycles
                rc = subprocess.call(
                    [str(PY), "-u", "tools/listing_watch.py", "--train"],
                    cwd=ROOT,
                    env=os.environ.copy(),
                    timeout=7200,
                )
                if rc == 0:
                    subprocess.call(
                        [str(PY), "-u", "tools/change_cleaner.py", "--reason", "lifecycle_watch_listing"],
                        cwd=ROOT,
                    )
        except Exception as e:
            _log(f"error: {e}")

        time.sleep(POLL_SEC)


if __name__ == "__main__":
    raise SystemExit(main())
