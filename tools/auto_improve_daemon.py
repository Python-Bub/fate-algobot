#!/usr/bin/env python3
"""Durable auto-improve daemon — research → plan → execute → verify.

Never deletes models / never shrinks universe. Cycles learning actions from the
free-agent allowlist + overlay evolution + blank-head fill + media intel refresh.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

QUEUE = ROOT / "data" / "agi" / "auto_improve_queue.jsonl"
STATE = ROOT / "data" / "agi" / "auto_improve_state.json"
LOG = ROOT / "logs" / "auto_improve_daemon.log"
PY = ROOT / "venv" / "bin" / "python"

# Optimize-only charter — these strings must never appear in executed shell.
_BAN = (
    "prune_bottom_junk",
    "rm -rf models",
    "FRESH_MODEL_REBUILD=true",
    "cleanup_orphan",
    "shrink_universe",
    "--delete-models",
)


def _log(msg: str) -> None:
    line = f"{datetime.now(timezone.utc).isoformat()} {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _load_state() -> dict[str, Any]:
    if STATE.is_file():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"generation": 0, "last_actions": [], "wins": 0}


def _save_state(st: dict[str, Any]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, indent=2) + "\n", encoding="utf-8")


def _enqueue(plan: dict[str, Any]) -> None:
    QUEUE.parent.mkdir(parents=True, exist_ok=True)
    with QUEUE.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.time(), **plan}) + "\n")


def research_plan() -> list[dict[str, Any]]:
    """Deep-ish local research → actionable plan (no external dependency required)."""
    plans: list[dict[str, Any]] = []
    # 1) Blank heads
    try:
        from fortress_universe import load_top100_symbols
        import joblib

        blanks = []
        for s in load_top100_symbols():
            p = ROOT / "models" / f"{s}_model.pkl"
            if not p.is_file():
                blanks.append({"sym": s, "missing_file": True})
                continue
            try:
                b = joblib.load(p)
                miss = [k for k in ("model_short", "model_long", "model_daily", "model_xlong", "model_meta") if not b.get(k)]
                if miss:
                    blanks.append({"sym": s, "null": miss})
            except Exception:
                blanks.append({"sym": s, "corrupt": True})
        if blanks:
            plans.append({"action": "fill_null_heads", "priority": 0, "detail": blanks[:30]})
    except Exception as e:
        plans.append({"action": "log", "priority": 9, "detail": f"blank_scan:{e}"})

    # 2) Rate-limit rotator health
    plans.append({"action": "refresh_media_intel", "priority": 2})
    plans.append({"action": "source_rotator_status", "priority": 3})

    # 3) Learning loops
    plans.append({"action": "evolve_overlay", "priority": 2})
    plans.append({"action": "free_agent_step", "priority": 2})
    plans.append({"action": "ensure_stack", "priority": 1})
    plans.append({"action": "extended_hours_check", "priority": 1})

    # 4) Weak retrain if strong idle
    try:
        r = subprocess.run(["pgrep", "-f", "retrain_top100_strong.py"], capture_output=True)
        if r.returncode != 0:
            plans.append({"action": "retrain_weak", "priority": 2})
    except Exception:
        pass

    plans.sort(key=lambda x: int(x.get("priority", 5)))
    return plans


def _banned(cmd: str) -> bool:
    low = cmd.lower()
    return any(b.lower() in low for b in _BAN)


def execute(plan: dict[str, Any]) -> dict[str, Any]:
    os.environ["AUTO_IMPROVE_NEVER_DELETE"] = "true"
    os.environ["CLEANER_NEVER_DELETE_MODELS"] = "true"
    os.environ["KEEP_WEAK_HEADS"] = "true"
    os.environ["COALESCE_EXISTING_HEADS"] = "true"
    os.environ["FILL_NULL_HEADS"] = "true"

    action = str(plan.get("action") or "")
    out: dict[str, Any] = {"action": action, "ok": False}

    if action == "fill_null_heads":
        cmd = [
            str(PY),
            "-u",
            "tools/fill_null_horizon_heads.py",
            "--top100-only",
            "--min-top20",
            "0.30",
            "--min-meta",
            "0.40",
        ]
        if _banned(" ".join(cmd)):
            return {"action": action, "ok": False, "banned": True}
        # Don't stack if already running
        r = subprocess.run(["pgrep", "-f", "fill_null_horizon_heads"], capture_output=True)
        if r.returncode == 0:
            out["ok"] = True
            out["skipped"] = "already_running"
            return out
        # Prefer strong path if RAM tight — spawn detached
        subprocess.Popen(
            [str(PY), "tools/spawn_daemon.py", "logs/fill_null_heads_latest.log", *cmd],
            cwd=str(ROOT),
        )
        out["ok"] = True
        out["spawned"] = True
        return out

    if action == "refresh_media_intel":
        from intel.media_intel import refresh_media_intel
        from fortress_universe import load_top100_symbols

        syms = [s.upper() for s in load_top100_symbols()[:40]]
        rep = refresh_media_intel(symbols=syms)
        out["ok"] = True
        out["n_podcast"] = (rep.get("podcast") or {}).get("n")
        return out

    if action == "source_rotator_status":
        from data_platform.source_rotator import available_sources, _load

        st = _load()
        out["ok"] = True
        out["available"] = available_sources()
        out["cooling"] = st.get("cooling_until")
        out["hits"] = st.get("hits")
        return out

    if action == "evolve_overlay":
        try:
            from self_modify.code_evolver import evolve_once

            evolve_once()
            out["ok"] = True
        except Exception as e:
            out["error"] = str(e)
        return out

    if action == "free_agent_step":
        try:
            from self_modify.free_agent import free_agent_step

            free_agent_step()
            out["ok"] = True
        except Exception as e:
            # Fallback: ensure_training style
            out["error"] = str(e)
            try:
                from self_modify.code_evolver import evolve_once

                evolve_once()
                out["ok"] = True
                out["fallback"] = "evolve_once"
            except Exception as e2:
                out["error2"] = str(e2)
        return out

    if action == "ensure_stack":
        live = {
            "fortress": subprocess.run(["pgrep", "-f", "fortress_live.py"], capture_output=True).returncode == 0,
            "hft": subprocess.run(["pgrep", "-f", "obi-tape/index"], capture_output=True).returncode == 0,
            "strong": subprocess.run(["pgrep", "-f", "retrain_top100_strong"], capture_output=True).returncode == 0,
        }
        out["ok"] = bool(live["fortress"] and live["hft"])
        out["live"] = live
        if not live["fortress"]:
            subprocess.Popen(
                [
                    str(PY),
                    "tools/spawn_daemon.py",
                    "logs/intraday_latest.log",
                    "bash",
                    "tools/daemon_loop.sh",
                    "30",
                    str(PY),
                    "-u",
                    "fortress_live.py",
                ],
                cwd=str(ROOT),
            )
            out["spawned_fortress"] = True
        return out

    if action == "extended_hours_check":
        from analytics.market_session import session_summary

        summ = session_summary() if callable(session_summary) else {}
        out["ok"] = True
        out["session"] = summ
        out["trade_session_mode"] = os.getenv("TRADE_SESSION_MODE")
        out["hft_extended"] = os.getenv("HFT_EXTENDED_HOURS")
        out["alpaca_extended"] = os.getenv("ALPACA_EXTENDED_HOURS")
        return out

    if action == "retrain_weak":
        subprocess.Popen(
            [
                str(PY),
                "tools/spawn_daemon.py",
                "logs/retrain_strong_until_clear.log",
                str(PY),
                "-u",
                "tools/retrain_top100_strong.py",
                "--until-clear",
                "--min-top20",
                "0.48",
                "--min-meta",
                "0.45",
            ],
            cwd=str(ROOT),
            env={
                **os.environ,
                "KEEP_WEAK_HEADS": "true",
                "FILL_NULL_HEADS": "true",
                "STRONG_N_EST": "200",
                "OMP_NUM_THREADS": "1",
            },
        )
        out["ok"] = True
        out["spawned"] = True
        return out

    if action == "log":
        out["ok"] = True
        out["detail"] = plan.get("detail")
        return out

    out["error"] = f"unknown_action:{action}"
    return out


def run_once() -> dict[str, Any]:
    # Load scale env so session / AH checks match live trading.
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env", override=False)
        load_dotenv(ROOT / "data" / "deploy_scale.env", override=True)
    except Exception:
        pass
    st = _load_state()
    plans = research_plan()
    for p in plans:
        _enqueue(p)
    results = []
    # Execute top N by priority each cycle
    for p in plans[:5]:
        _log(f"exec {p.get('action')}")
        r = execute(p)
        results.append(r)
        _log(f"result {json.dumps(r, default=str)[:500]}")
    st["generation"] = int(st.get("generation") or 0) + 1
    st["last_actions"] = results
    st["last_ts"] = time.time()
    if any(r.get("ok") for r in results):
        st["wins"] = int(st.get("wins") or 0) + 1
    _save_state(st)
    return {"generation": st["generation"], "results": results}


def main() -> int:
    os.chdir(ROOT)
    interval = int(os.getenv("AUTO_IMPROVE_INTERVAL_SEC", "900"))
    loops = int(os.getenv("AUTO_IMPROVE_LOOPS", "0"))  # 0 = forever
    n = 0
    while True:
        try:
            run_once()
        except Exception as e:
            _log(f"ERROR {type(e).__name__}: {e}")
        n += 1
        if loops > 0 and n >= loops:
            break
        time.sleep(max(60, interval))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
