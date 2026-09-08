#!/usr/bin/env python3
"""Ensure a fresh, usable paper sim report — background start, no manual commands."""

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
RUN = ROOT / "run_all.sh"
LOG = ROOT / "logs" / "ensure_paper_sim.log"
STAMP = ROOT / "data" / "ensure_paper_sim_last.txt"


def _log(msg: str) -> None:
    line = f"{datetime.now(timezone.utc).isoformat()} {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def paper_sim_in_progress() -> bool:
    lock = ROOT / "data" / "paper_sim.lock"
    if lock.is_file():
        try:
            if time.time() - lock.stat().st_mtime < float(os.getenv("PAPER_SIM_LOCK_MAX_AGE_SEC", "7200")):
                return True
        except OSError:
            pass
    try:
        r = subprocess.run(
            ["pgrep", "-f", "paper_sim_today"],
            capture_output=True,
            text=True,
            check=False,
        )
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        return False


def needs_paper_sim() -> tuple[bool, str]:
    if os.getenv("AUTO_PAPER_SIM", "true").lower() not in ("1", "true", "yes"):
        return False, "AUTO_PAPER_SIM=false"

    from analytics.paper_report import is_usable_report, latest_valid_report, report_age_hours

    max_age = float(os.getenv("AUTO_PAPER_SIM_MAX_AGE_HOURS", os.getenv("AUTOTUNE_PAPER_SIM_MAX_AGE_HOURS", "20")))
    path, doc = latest_valid_report(min_rows=50)
    if not doc or not path:
        return True, "missing_report"

    ok, reason = is_usable_report(doc, path=path)
    if not ok:
        return True, f"unusable:{reason}"

    age = report_age_hours(path)
    if age > max_age:
        return True, f"stale:{age:.1f}h>{max_age:.0f}h"
    return False, "fresh"


def _paper_sim_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("PAPER_SIM_ACTIVE_ONLY", "true")
    env.setdefault("PAPER_SIM_ACTIVE_MODE", "top100_rotate")
    env.setdefault("PAPER_SIM_FORCE_YAHOO", "false")
    env.setdefault("PAPER_SIM_USE_POLYGON", "true")
    env.setdefault("PAPER_SIM_USE_ALPACA", "true")
    env.setdefault("PAPER_SIM_SAVE_PRICE_CACHE", "true")
    env.setdefault("USE_PRICE_CACHE", "true")
    env.setdefault("PAPER_SIM_ACTIVE_RUN", "true")
    env.setdefault("PAPER_SIM_SKIP_YAHOO_FALLBACK", "true")
    env.setdefault("PAPER_SIM_POLYGON_MAX_WORKERS", "1")
    workers = int(os.getenv("PAPER_SIM_WORKERS", "1"))
    cap = int(os.getenv("PAPER_SIM_POLYGON_MAX_WORKERS", "1"))
    env["PAPER_SIM_WORKERS"] = str(min(workers, cap))
    return env


def start_paper_sim_background(*, reason: str) -> bool:
    if paper_sim_in_progress():
        _log(f"skip in_progress ({reason})")
        return False

    cooldown = int(os.getenv("AUTO_PAPER_SIM_COOLDOWN_SEC", os.getenv("AUTOTUNE_PAPER_SIM_COOLDOWN_SEC", "1800")))
    if STAMP.is_file():
        try:
            last = float(STAMP.read_text(encoding="utf-8").strip())
            if time.time() - last < cooldown:
                _log(f"skip cooldown {int(cooldown - (time.time() - last))}s ({reason})")
                return False
        except (OSError, ValueError):
            pass

    logf = ROOT / "logs" / f"paper_sim_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    latest = ROOT / "logs" / "paper_sim_latest.log"
    try:
        latest.unlink(missing_ok=True)
        latest.symlink_to(logf.name)
    except OSError:
        pass

    STAMP.parent.mkdir(parents=True, exist_ok=True)
    STAMP.write_text(str(time.time()), encoding="utf-8")
    env = _paper_sim_env()
    cmd = [str(PY), "-u", str(ROOT / "paper_sim_today.py")]
    _log(f"start {reason} -> {logf.name}")
    with logf.open("a", encoding="utf-8") as out:
        subprocess.Popen(
            cmd,
            cwd=ROOT,
            env=env,
            stdout=out,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    return True


def ensure_paper_sim(*, force: bool = False) -> dict:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))

    if force:
        started = start_paper_sim_background(reason="force")
        return {"started": started, "reason": "force"}

    need, why = needs_paper_sim()
    if not need:
        return {"started": False, "reason": why}

    started = start_paper_sim_background(reason=why)
    return {"started": started, "reason": why}


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Ensure background paper sim when report stale/unusable")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    result = ensure_paper_sim(force=args.force)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
