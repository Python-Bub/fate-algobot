#!/usr/bin/env python3
"""Trading-day autorun — unpause, intel, paper sim, playbook, training gaps. No manual commands."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / "venv" / "bin" / "python"
RUN = ROOT / "run_all.sh"
STATE = ROOT / "data" / "trading_day_autorun.json"
LOG = ROOT / "logs" / "trading_day_autorun.log"


def _log(msg: str) -> None:
    line = f"{datetime.now(timezone.utc).isoformat()} {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _run(cmd: list[str], *, timeout: int = 3600, env: dict | None = None) -> int:
    _log(f"RUN {' '.join(cmd[:6])}{'...' if len(cmd) > 6 else ''}")
    try:
        return subprocess.run(
            cmd,
            cwd=ROOT,
            env=env or os.environ.copy(),
            timeout=timeout,
            check=False,
        ).returncode
    except subprocess.TimeoutExpired:
        _log(f"TIMEOUT {' '.join(cmd[:4])}")
        return 124


def _today() -> str:
    from analytics.market_session import now_et

    return now_et().date().isoformat()


def _load_state() -> dict:
    if not STATE.is_file():
        return {}
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(doc: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    os.replace(tmp, STATE)


def _needs_paper_sim() -> bool:
    from tools.ensure_paper_sim import needs_paper_sim

    need, _ = needs_paper_sim()
    return need


def run_trading_day_autorun(*, force: bool = False) -> dict:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))

    from analytics.market_session import auto_unpause_window_open, intel_window_open, is_trading_day

    if not is_trading_day() and not force:
        return {"skipped": True, "reason": "not_trading_day"}

    today = _today()
    st = _load_state()
    if st.get("last_run_date") == today and not force:
        return {"skipped": True, "reason": "already_ran_today", "last": st}

    out: dict = {"date": today, "started_at": datetime.now(timezone.utc).isoformat(), "steps": []}

    # 1) Unpause if still paused (watchdog may have done this already)
    autopilot = ROOT / "data" / "autopilot_state.json"
    paused = False
    if autopilot.is_file():
        try:
            paused = bool(json.loads(autopilot.read_text()).get("paused"))
        except Exception:
            pass
    if paused and auto_unpause_window_open()[0]:
        rc = _run([str(RUN), "unpause"], timeout=300)
        out["steps"].append({"unpause": rc})

    # 2) Morning intel prefetch (6 AM API window)
    if intel_window_open()[0]:
        rc = _run([str(RUN), "morning-prefetch"], timeout=600)
        out["steps"].append({"morning_prefetch": rc})

    # 3) Fresh paper sim when report stale/empty/unusable
    if _needs_paper_sim():
        from tools.ensure_paper_sim import start_paper_sim_background

        _log("paper_sim starting (stale, missing, or unusable report)")
        started = start_paper_sim_background(reason="trading_day_autorun")
        out["steps"].append({"paper_sim": "started" if started else "skipped_in_progress"})
    else:
        out["steps"].append({"paper_sim": "skipped_fresh"})

    # 4) Monday playbook + family forecast cache
    rc = _run([str(PY), "-u", "tools/monday_playbook.py", "--skip-sim"], timeout=120)
    out["steps"].append({"monday_playbook": rc})

    rc = _run([str(PY), "-u", "tools/family_forecast.py", "--json"], timeout=120)
    out["steps"].append({"family_forecast": rc})

    # 5) Training gaps (top100 only — no junk LSTM-all)
    rc = _run([str(PY), "-u", "tools/train_untrained.py", "--launch", "--no-lstm-all"], timeout=60)
    out["steps"].append({"train_untrained": rc})

    # 6) Ensure stack up
    rc = _run([str(RUN), "ensure-stack"], timeout=180)
    out["steps"].append({"ensure_stack": rc})

    # 7) Full trade verification + auto-remediation
    rc = _run([str(PY), "-u", "tools/verify_trades.py", "--quiet"], timeout=180)
    out["steps"].append({"verify_trades": rc})

    out["finished_at"] = datetime.now(timezone.utc).isoformat()
    _save_state({**st, "last_run_date": today, "last_result": out})
    _log(f"DONE {json.dumps(out['steps'])}")
    return out


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Trading-day full autorun")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    result = run_trading_day_autorun(force=args.force)
    print(json.dumps(result, indent=2))
    return 0 if not result.get("skipped") else 0


if __name__ == "__main__":
    raise SystemExit(main())
