#!/usr/bin/env python3
"""Always-on self-maintenance — daemons, gaps, weak retrain, universe, dip-buy scans."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "self_maintenance_state.json"
PY = ROOT / "venv/bin/python"
RUN = ROOT / "run_all.sh"


def _log(msg: str) -> None:
    print(f"[self-maint] {msg}", flush=True)


def _load_state() -> dict:
    if not STATE.is_file():
        return {}
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(**fields: object) -> None:
    st = _load_state()
    st.update(fields)
    st["updated_at"] = datetime.now(timezone.utc).isoformat()
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(st, indent=2), encoding="utf-8")
    os.replace(tmp, STATE)


def _run(cmd: list[str], *, timeout: int = 600) -> int:
    try:
        return subprocess.run(cmd, cwd=ROOT, timeout=timeout, check=False).returncode
    except subprocess.TimeoutExpired:
        _log(f"TIMEOUT {' '.join(cmd[:4])}")
        return 124


def _pid_alive(name: str) -> bool:
    pf = ROOT / ".pids" / f"{name}.pid"
    if not pf.is_file():
        return False
    try:
        pid = int(pf.read_text(encoding="utf-8").strip())
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def _autopilot_paused() -> bool:
    p = ROOT / "data" / "autopilot_state.json"
    if not p.is_file():
        return False
    try:
        return bool(json.loads(p.read_text(encoding="utf-8")).get("paused"))
    except Exception:
        return False


def _ensure(name: str, start_args: list[str]) -> None:
    if _pid_alive(name):
        return
    _log(f"restart {name}")
    _run(start_args)


def _gap_audit() -> dict:
    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)
    try:
        from tools.train_untrained import audit_gaps

        return audit_gaps()
    except Exception as e:
        return {"error": str(e)}


def _maybe_weak_retrain() -> None:
    if os.getenv("SELF_MAINT_WEAK_RETRAIN", "true").lower() not in ("1", "true", "yes"):
        return
    if _pid_alive("retrain-weak-loop"):
        return
    try:
        from tools.retrain_weak_models import find_weak_symbols

        weak = find_weak_symbols(
            min_top20=float(os.getenv("RETRAIN_MIN_TOP20", "0.6")),
            min_meta=float(os.getenv("MIN_META_AUC", "0.52")),
            top100_only=True,
        )
        if weak:
            _log(f"weak models {len(weak)} — starting retrain-weak-until")
            _run([str(RUN), "retrain-weak-until"], timeout=30)
    except Exception as e:
        _log(f"weak retrain skip: {e}")


def _maybe_train_gaps() -> None:
    gaps = _gap_audit()
    if gaps.get("error"):
        _log(f"gap audit error: {gaps['error']}")
        return
    daily = int(gaps.get("top100_daily_missing") or 0)
    intra = int(gaps.get("top100_intraday_missing") or 0)
    lstm = int(gaps.get("top100_lstm_missing") or 0)
    if daily + intra + lstm == 0:
        return
    _log(f"gaps daily={daily} intraday={intra} lstm={lstm} — train-untrained")
    _run([str(PY), "-u", "tools/train_untrained.py", "--launch", "--no-lstm-all"], timeout=120)


def _maybe_enhancement_cycle() -> None:
    """Re-run enhancement queue weekly if gaps remain or phase stale."""
    if os.getenv("SELF_MAINT_ENHANCE_WEEKLY", "true").lower() not in ("1", "true", "yes"):
        return
    if _pid_alive("enhancement-queue"):
        return
    st = _load_state()
    last = st.get("last_enhance_restart_utc", "")
    if last:
        try:
            last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - last_dt).total_seconds() / 86400.0
            if age_days < float(os.getenv("SELF_MAINT_ENHANCE_MIN_DAYS", "7")):
                return
        except Exception:
            pass
    eq = ROOT / "data" / "enhancement_queue_state.json"
    phase = ""
    if eq.is_file():
        try:
            phase = str(json.loads(eq.read_text(encoding="utf-8")).get("phase", ""))
        except Exception:
            pass
    gaps = _gap_audit()
    total_gaps = sum(
        int(gaps.get(k) or 0)
        for k in ("top100_daily_missing", "top100_intraday_missing", "top100_lstm_missing")
    )
    if phase == "done" and total_gaps == 0:
        return
    if phase not in ("", "done", "init") and phase:
        _log(f"enhancement queue mid-phase={phase} — relaunch")
    elif total_gaps > 0:
        _log(f"enhancement restart — {total_gaps} top100 gap(s)")
    else:
        return
    _run([str(RUN), "enhancement-queue-restart", "full"], timeout=60)
    _save_state(last_enhance_restart_utc=datetime.now(timezone.utc).isoformat())


def run_self_maintenance(*, force: bool = False) -> dict:
    if os.getenv("SELF_MAINTENANCE", "true").lower() not in ("1", "true", "yes") and not force:
        return {"skipped": True, "reason": "disabled"}
    if _autopilot_paused():
        return {"skipped": True, "reason": "autopilot_paused"}

    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))

    st = _load_state()
    interval = int(os.getenv("SELF_MAINTENANCE_INTERVAL_SEC", "3600"))
    if not force and st.get("last_pass_utc"):
        try:
            last = datetime.fromisoformat(str(st["last_pass_utc"]).replace("Z", "+00:00"))
            if (datetime.now(timezone.utc) - last).total_seconds() < interval:
                return {"skipped": True, "reason": "interval", "next_in_sec": interval}
        except Exception:
            pass

    out: dict = {"steps": []}

    # Keep maintenance daemons alive (watchdog also calls this hourly).
    daemons = [
        ("disk-cleanup", [str(RUN), "ensure-disk-cleanup"]),
        ("bottom-fisher-watch", [str(RUN), "bottom-fisher-watch"]),
        ("universe-lifecycle-watch", [str(RUN), "universe-lifecycle-watch"]),
        ("stack-autotune", [str(RUN), "ensure-autotune"]),
    ]
    for name, cmd in daemons:
        before = _pid_alive(name)
        _ensure(name, cmd)
        out["steps"].append({name: "ok" if _pid_alive(name) or before else "started"})

    # Universe + listings (light sync if lifecycle idle)
    if os.getenv("SELF_MAINT_UNIVERSE_SYNC", "true").lower() in ("1", "true", "yes"):
        rc = _run([str(RUN), "universe-sync"], timeout=900)
        out["steps"].append({"universe_sync": rc})

    _maybe_train_gaps()
    out["steps"].append({"train_gaps": "ran"})
    _maybe_weak_retrain()
    out["steps"].append({"weak_retrain": "checked"})
    _maybe_enhancement_cycle()
    out["steps"].append({"enhancement": "checked"})

    # Prune + health
    if os.getenv("SELF_MAINT_PRUNE", "true").lower() in ("1", "true", "yes"):
        rc = _run([str(PY), "-u", "tools/change_cleaner.py", "--reason", "self_maintenance"], timeout=300)
        out["steps"].append({"prune": rc})
    if os.getenv("SELF_MAINT_HEALTH", "true").lower() in ("1", "true", "yes"):
        rc = _run([str(PY), "-u", "tools/health_check.py"], timeout=180)
        out["steps"].append({"health": rc})

    if os.getenv("AUTO_VERIFY_TRADES", "true").lower() in ("1", "true", "yes"):
        rc = _run([str(PY), "-u", "tools/verify_trades.py", "--quiet"], timeout=180)
        out["steps"].append({"verify_trades": rc})

    _save_state(last_pass_utc=datetime.now(timezone.utc).isoformat())
    out["finished_at"] = datetime.now(timezone.utc).isoformat()
    _log(f"DONE {json.dumps(out['steps'])}")
    return out


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Self-maintenance pass")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    result = run_self_maintenance(force=args.force)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
