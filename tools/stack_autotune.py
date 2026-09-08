#!/usr/bin/env python3
"""Stack autotune — small self-healing tweaks (daemons, gates, cooldown, disk).

Runs safe fixes only: restart stopped daemons, repatch asym, sync trades, prune logs.
Logs every action to data/autotune_log.jsonl for audit.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = ROOT / "data" / "autotune_log.jsonl"
PY = ROOT / "venv/bin/python"


def _log(action: str, detail: str, *, ok: bool = True) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "detail": detail,
        "ok": ok,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    tag = "OK" if ok else "WARN"
    print(f"[autotune][{tag}] {action}: {detail}", flush=True)


def _run(cmd: list[str], *, cwd: Path | None = None) -> int:
    try:
        return subprocess.run(cmd, cwd=cwd or ROOT, check=False).returncode
    except Exception as e:
        _log("run_error", f"{cmd}: {e}", ok=False)
        return 1


def _pid_running(name: str) -> bool:
    pf = ROOT / ".pids" / f"{name}.pid"
    if not pf.is_file():
        return False
    try:
        pid = int(pf.read_text(encoding="utf-8").strip())
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def _ensure_daemon(name: str, start_cmd: list[str]) -> None:
    if _pid_running(name):
        return
    _log("restart_daemon", name)
    _run(start_cmd)


def _check_family_forecast_sanity() -> None:
    """Flag bearish/DOWN hero picks — triggers asym repatch if broken."""
    if not PY.is_file():
        return
    r = subprocess.run(
        [str(PY), "-u", "tools/family_forecast.py", "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if r.returncode != 0:
        _log("family_forecast", "no picks or missing report", ok=False)
        return
    try:
        doc = json.loads(r.stdout)
    except json.JSONDecodeError:
        return
    picks = doc.get("best_per_horizon") or []
    down = [p for p in picks if str(p.get("signal", "")).upper() == "DOWN"]
    try:
        from analytics.horizon_picks import horizon_independent

        independent = horizon_independent()
    except Exception:
        independent = False
    if down and not independent:
        tickers = ", ".join(f"{p.get('ticker')}@{p.get('chance_pct')}%" for p in down)
        _log("family_forecast_down_picks", tickers, ok=False)
        _run([str(PY), "-u", "tools/repatch_paper_report_asym.py"])
    else:
        extra = f" ({len(down)} down)" if down else ""
        _log("family_forecast", f"{len(picks)} picks{extra}")


def _check_asym_gate() -> None:
    rep = sorted((ROOT / "reports").glob("paper_sim_*.json"), reverse=True)
    if not rep:
        return
    try:
        doc = json.loads(rep[0].read_text(encoding="utf-8"))
    except Exception:
        return
    m = doc.get("asym_filter_metrics") or {}
    long_zone = int(m.get("n_asym_long_zone") or 0)
    if long_zone <= 0 and int(m.get("n_scored") or 0) > 50:
        _log("asym_zero_long", "repatching asym thresholds")
        _run([str(PY), "-u", "tools/repatch_paper_report_asym.py"])


def _retrain_mega_missing() -> None:
    """One-shot retrain for missing top-15 megacap daily bundles (NVDA-class gaps)."""
    if os.getenv("AUTOTUNE_MEGA_RETRAIN", "true").lower() not in ("1", "true", "yes"):
        return
    from fortress_universe import load_top100_symbols
    from model_trainer import _train_single_ticker, training_saved_model

    top = load_top100_symbols()
    missing = [s for s in top[:15] if not training_saved_model(s)]
    if not missing:
        return
    limit = int(os.getenv("AUTOTUNE_MEGA_RETRAIN_LIMIT", "2"))
    for sym in missing[:limit]:
        _log("retrain_mega", sym)
        try:
            if _train_single_ticker(sym):
                _log("retrain_mega_ok", sym)
            else:
                _log("retrain_mega_skip", sym, ok=False)
        except Exception as e:
            _log("retrain_mega_fail", f"{sym}: {e}", ok=False)


def _ensure_usable_paper_report() -> None:
    """Kick background paper sim when report is partial, stale, or missing."""
    if os.getenv("AUTOTUNE_PAPER_SIM_REFRESH", "true").lower() not in ("1", "true", "yes"):
        return
    from tools.ensure_paper_sim import ensure_paper_sim

    result = ensure_paper_sim()
    if result.get("started"):
        _log("paper_sim_refresh", str(result.get("reason", "started")))
    elif result.get("reason") not in ("fresh",):
        _log("paper_sim_skip", str(result.get("reason")), ok=True)


def _maintenance_pass() -> None:
    _run([str(PY), "-u", "tools/sync_recent_trades.py"])
    if os.getenv("AUTOTUNE_VERIFY_TRADES", "true").lower() in ("1", "true", "yes"):
        rc = _run([str(PY), "-u", "tools/verify_trades.py", "--quiet"])
        _log("verify_trades", f"exit={rc}", ok=rc == 0)
    if os.getenv("AUTOTUNE_PRUNE_DISK", "true").lower() in ("1", "true", "yes"):
        _run([str(PY), "-u", "tools/change_cleaner.py", "--reason", "stack_autotune"])


def run_once() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))

    _ensure_daemon("intraday", ["./run_all.sh", "ensure-intraday"])
    _ensure_daemon("subsecond-obi", ["./run_all.sh", "ensure-subsecond"])
    _ensure_daemon("subsecond-earnings", ["./run_all.sh", "ensure-earnings"])
    _ensure_daemon("hft-rotator", ["./run_all.sh", "hft-rotator"])
    _ensure_daemon("paper-awake", ["./run_all.sh", "ensure-paper-awake"])
    _ensure_daemon("paper-hygiene", ["./run_all.sh", "ensure-paper-hygiene"])
    _ensure_daemon("weekly", ["./run_all.sh", "ensure-weekly"])
    if os.getenv("PAPER_USE_LONGTERM", "false").lower() in ("1", "true", "yes"):
        _ensure_daemon("longterm", ["./run_all.sh", "ensure-longterm"])
    _ensure_daemon("disk-cleanup", ["./run_all.sh", "ensure-disk-cleanup"])
    _ensure_daemon("bottom-fisher-watch", ["./run_all.sh", "bottom-fisher-watch"])
    _ensure_daemon("universe-lifecycle-watch", ["./run_all.sh", "universe-lifecycle-watch"])
    _check_asym_gate()
    _check_family_forecast_sanity()
    _ensure_usable_paper_report()
    _retrain_mega_missing()
    _maintenance_pass()

    if os.getenv("SELF_IMPROVE_ON_AUTOTUNE", "true").lower() in ("1", "true", "yes"):
        try:
            sys.path.insert(0, str(ROOT))
            from self_modify.code_evolver import evolve_once

            out = evolve_once()
            _log("self_improve", str(out.get("rationale") or out.get("reason", "")), ok=bool(out.get("ok")))
        except Exception as e:
            _log("self_improve", str(e), ok=False)

    if os.getenv("AUTOTUNE_RUN_HEALTH", "true").lower() in ("1", "true", "yes"):
        rc = _run([str(PY), "-u", "tools/health_check.py"])
        if rc != 0:
            _log("health_check", f"exit {rc}", ok=False)

    return 0


def main() -> int:
    once = "--once" in sys.argv or os.getenv("AUTOTUNE_ONCE", "").lower() in ("1", "true", "yes")
    poll = int(os.getenv("AUTOTUNE_POLL_SEC", "300"))
    if once:
        return run_once()
    _log("start", f"poll={poll}s")
    while True:
        try:
            run_once()
        except Exception as e:
            _log("loop_error", str(e), ok=False)
        time.sleep(poll)


if __name__ == "__main__":
    raise SystemExit(main())
