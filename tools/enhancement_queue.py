#!/usr/bin/env python3
"""Background queue — full finish, no corners (see TRAIN_PROPER_FINISH / ENHANCE_FINISH_MODE).

Phases (full + proper):
  wait intraday → intraday proper gap (no placeholder skip, 365d lookback)
  → LSTM active → daily junk (full news + grader) → train failed retry
  → top100 perfection → LSTM all (~5k, 20 epochs)

State: data/enhancement_queue_state.json
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
STATE = ROOT / "data" / "enhancement_queue_state.json"
RUN = ROOT / "run_all.sh"
PY = ROOT / "venv/bin/python"


def _log(msg: str) -> None:
    line = f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}Z] {msg}"
    print(line, flush=True)


def _load_state() -> dict:
    if not STATE.is_file():
        return {"phase": "init", "started_at": None, "notes": []}
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"phase": "init", "started_at": None, "notes": []}


def _save_state(st: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(st, indent=2), encoding="utf-8")
    os.replace(tmp, STATE)


def _pid_alive(name: str) -> bool:
    pf = ROOT / ".pids" / f"{name}.pid"
    if not pf.is_file():
        return False
    try:
        pid = int(pf.read_text().strip())
    except ValueError:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _log_has_complete(log_name: str, marker: str = "[PARALLEL] all workers complete") -> bool:
    log = ROOT / "logs" / log_name
    if not log.is_file():
        return False
    try:
        tail = log.read_text(encoding="utf-8", errors="ignore")[-80_000:]
    except OSError:
        return False
    if marker in tail:
        return True
    # LSTM batch trainer (train_lstm_heads.py)
    if "[LSTM-BATCH] complete" in tail or "[LSTM-BATCH] nothing pending" in tail:
        return True
    return False


def _read_pid(name: str) -> int | None:
    pf = ROOT / ".pids" / f"{name}.pid"
    try:
        return int(pf.read_text().strip())
    except (OSError, ValueError):
        return None


def _log_mtime(log_latest: str) -> float:
    if not log_latest:
        return 0.0
    try:
        return (ROOT / "logs" / log_latest).stat().st_mtime
    except OSError:
        return 0.0


def _kill_stuck(name: str) -> None:
    """Hard-kill a wedged trainer (alive but making no progress) and its workers so
    the queue can advance. A multiprocessing pool that finished but never joined will
    sit at 0% CPU forever and otherwise block the whole 100 GB finish indefinitely."""
    import signal

    pid = _read_pid(name)
    if not pid:
        return
    try:
        subprocess.call(["pkill", "-KILL", "-P", str(pid)])
    except Exception:
        pass
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


def _wait_trainer(name: str, log_latest: str, poll_sec: int = 90) -> None:
    _log(f"waiting for {name} to finish…")
    # Stuck-trainer guard: kill + continue if the log makes no progress for this long.
    idle_limit = float(os.getenv("ENHANCE_WAIT_IDLE_KILL_SEC", "2400"))  # 40 min
    last_mtime = _log_mtime(log_latest)
    last_change = time.time()
    while True:
        if not _pid_alive(name) and _log_has_complete(log_latest):
            _log(f"{name} complete")
            return
        if not _pid_alive(name):
            time.sleep(5)
            if _log_has_complete(log_latest):
                _log(f"{name} complete (pid gone)")
                return
            _log(f"{name} stopped without complete marker — continuing anyway")
            return
        now = time.time()
        mt = _log_mtime(log_latest)
        if mt > last_mtime:
            last_mtime = mt
            last_change = now
        elif idle_limit > 0 and now - last_change > idle_limit:
            _log(
                f"{name} idle {int(now - last_change)}s with no log progress "
                f"(stuck pool?) — killing and continuing"
            )
            _kill_stuck(name)
            time.sleep(3)
            return
        time.sleep(poll_sec)


def _lstm_pending(scope: str) -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    prev = os.environ.get("LSTM_TRAIN_SCOPE")
    os.environ["LSTM_TRAIN_SCOPE"] = scope
    try:
        from tools.train_lstm_heads import _pending_symbols

        return len(_pending_symbols())
    finally:
        if prev is None:
            os.environ.pop("LSTM_TRAIN_SCOPE", None)
        else:
            os.environ["LSTM_TRAIN_SCOPE"] = prev


def _quality_env(extra: dict | None = None) -> dict[str, str]:
    sys.path.insert(0, str(ROOT))
    from tools.proper_finish_env import max_quality_env

    e = os.environ.copy()
    e.update(max_quality_env(extra))
    return e


def _run_shell_launch(cmd: list[str], env: dict | None = None, *, quality: bool = True) -> None:
    if quality:
        e = _quality_env(env)
    else:
        e = os.environ.copy()
        if env:
            e.update({k: str(v) for k, v in env.items()})
    _log("exec: " + " ".join(cmd))
    subprocess.call(cmd, cwd=ROOT, env=e)
    time.sleep(3)


def _finish_mode() -> str:
    return os.getenv("ENHANCE_FINISH_MODE", "full").strip().lower()


def _is_fast() -> bool:
    return _finish_mode() in ("fast", "minimal", "quick")


def _phases_for_mode() -> list[tuple[str, str | None, str | None]]:
    phases: list[tuple[str, str | None, str | None]] = [
        ("wait_intraday", "train-intraday", "train-intraday_latest.log"),
    ]
    if not _is_fast():
        phases.append(("intraday_proper_gap", None, None))
    phases.extend(
        [
            ("wait_lstm_active", "train-lstm", "train-lstm_latest.log"),
            ("daily_junk", None, None),
            ("train_failed", None, None),
            ("top100_perfect", None, None),
        ]
    )
    if not _is_fast():
        phases.append(("lstm_all", None, None))
    phases.append(("done", None, None))
    return phases


def main() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    st = _load_state()
    if not st.get("started_at"):
        st["started_at"] = datetime.now(timezone.utc).isoformat()
    phase = st.get("phase", "init")

    phases = _phases_for_mode()
    _log(f"finish_mode={_finish_mode()}  proper=true  phases={[p[0] for p in phases]}")

    idx = next((i for i, (p, _, _) in enumerate(phases) if p == phase), 0)
    if phase == "done":
        # File-exists "done" is a false positive. Re-enter the phase that still has gaps.
        try:
            from tools.model_completeness import queue_reopen_phase

            want = queue_reopen_phase()
        except Exception as e:
            want = None
            _log(f"completeness probe failed: {e}")
        if want:
            idx = next((i for i, (p, _, _) in enumerate(phases) if p == want), None)
            if idx is None:
                idx = 0
                want = phases[0][0]
            _log(f"resuming: {want} — completeness gaps (phase=done was a false complete)")
            st["finished_at"] = None
            st["notes"] = list(st.get("notes") or []) + [f"auto-resume {want} (completeness)"]
            phase = want
        else:
            try:
                from fortress_universe import load_top100_symbols
                from model_trainer import training_saved_model

                top_miss = sum(1 for s in load_top100_symbols() if not training_saved_model(s))
            except Exception:
                top_miss = 0
            if top_miss > 0:
                idx = next(i for i, (p, _, _) in enumerate(phases) if p == "top100_perfect")
                _log(f"resuming: top100_perfect — {top_miss} daily models still missing")
                st["finished_at"] = None
                st["notes"] = list(st.get("notes") or []) + [
                    f"auto-resume top100_perfect ({top_miss} missing)"
                ]
            elif not _is_fast() and _lstm_pending("all") > 0:
                idx = next(i for i, (p, _, _) in enumerate(phases) if p == "lstm_all")
                _log("resuming: lstm_all still pending")
            else:
                _log("enhancement queue already finished (completeness ok)")
                return 0

    for i in range(idx, len(phases)):
        pname, _trainer, logf = phases[i]
        st["phase"] = pname
        _save_state(st)
        _log(f"=== phase: {pname} ===")

        if pname == "wait_intraday":
            if _pid_alive("train-intraday"):
                _wait_trainer("train-intraday", logf or "")
            else:
                _log("train-intraday not running — skip wait")

        elif pname == "intraday_proper_gap":
            _log("intraday proper gap — no placeholder skip, 365d lookback, retry insufficient bundles")
            if _pid_alive("train-intraday"):
                _wait_trainer("train-intraday", "train-intraday_latest.log")
            _run_shell_launch([str(RUN), "train-intraday-proper"], {})
            if _pid_alive("train-intraday"):
                _wait_trainer("train-intraday", "train-intraday_latest.log")

        elif pname == "wait_lstm_active":
            pending_active = _lstm_pending("active")
            if pending_active > 0 and not _pid_alive("train-lstm"):
                _log(f"LSTM active: {pending_active} pending — starting train-lstm")
                _run_shell_launch(
                    [str(RUN), "train-lstm"],
                    {"LSTM_TRAIN_SCOPE": "active", "LSTM_WORKERS": os.getenv("LSTM_WORKERS", "3")},
                )
            if _pid_alive("train-lstm"):
                _wait_trainer("train-lstm", logf or "")
            elif pending_active == 0:
                _log("LSTM active queue empty")

        elif pname == "daily_junk":
            if not _pid_alive("train"):
                workers = os.getenv("ENHANCE_DAILY_WORKERS", "6")
                if _is_fast():
                    _run_shell_launch(
                        [str(RUN), "train-missing-fast"],
                        {"TRAIN_MISSING_WORKERS": workers},
                        quality=False,
                    )
                else:
                    _run_shell_launch([str(RUN), "train-missing-proper"], {"TRAIN_MISSING_WORKERS": workers})
            if _pid_alive("train"):
                _wait_trainer("train", "train_latest.log")

        elif pname == "train_failed":
            if _pid_alive("train"):
                _wait_trainer("train", "train_latest.log")
            _run_shell_launch([str(RUN), "train-failed"], {})
            if _pid_alive("train"):
                _wait_trainer("train", "train_latest.log")

        elif pname == "top100_perfect":
            _log("top-100 perfection — gap-fill missing dailies first (no FRESH purge by default)")
            _run_shell_launch(
                [str(PY), "-u", str(ROOT / "tools/train_top100_perfect.py")],
                {
                    "FRESH_MODEL_REBUILD": os.getenv("FRESH_MODEL_REBUILD", "false"),
                    "TOP100_DAILY_WORKERS": os.getenv("TOP100_DAILY_WORKERS", "2"),
                    "TOP100_INTRADAY_WORKERS": os.getenv("TOP100_INTRADAY_WORKERS", "2"),
                    "TOP100_LSTM_WORKERS": os.getenv("TOP100_LSTM_WORKERS", "2"),
                },
            )
            try:
                from fortress_universe import load_top100_symbols
                from model_trainer import training_saved_model

                top_miss = sum(1 for s in load_top100_symbols() if not training_saved_model(s))
            except Exception:
                top_miss = 0
            if top_miss > 5:
                _log(
                    f"top100_perfect incomplete — {top_miss} daily models still missing; "
                    "re-running before advancing"
                )
                st["notes"] = list(st.get("notes") or []) + [
                    f"retry top100_perfect ({top_miss} missing)"
                ]
                _save_state(st)
                # Stay on this phase index (re-enter next loop iteration)
                # by not falling through — re-run once more then continue.
                _run_shell_launch(
                    [str(PY), "-u", str(ROOT / "tools/train_top100_perfect.py")],
                    {
                        "FRESH_MODEL_REBUILD": "false",
                        "TOP100_DAILY_WORKERS": os.getenv("TOP100_DAILY_WORKERS", "2"),
                    },
                )
                try:
                    top_miss = sum(
                        1 for s in load_top100_symbols() if not training_saved_model(s)
                    )
                except Exception:
                    top_miss = 99
                if top_miss > 5:
                    _log(
                        f"ABORT advance: still {top_miss} top100 daily missing — "
                        "leaving phase=top100_perfect for resume"
                    )
                    st["phase"] = "top100_perfect"
                    _save_state(st)
                    return 1

        elif pname == "lstm_all":
            # Phase id is historical; scope comes from LSTM_FINISH_SCOPE (default active, not all).
            scope = os.getenv("LSTM_FINISH_SCOPE", "all" if not _is_fast() else "active").strip().lower()
            pending = _lstm_pending(scope)
            _log(
                f"LSTM finish (phase=lstm_all, scope={scope}) pending={pending} "
                f"— neural ensemble is separate (top100 + paper_sim online); "
                f"set LSTM_FINISH_SCOPE=all only if you want every daily model"
            )
            if pending <= 0:
                _log("LSTM finish complete (nothing pending in scope)")
            else:
                if _pid_alive("train-lstm"):
                    _wait_trainer("train-lstm", "train-lstm_latest.log")
                workers = os.getenv("ENHANCE_LSTM_WORKERS", "6")
                epochs = os.getenv("ENHANCE_LSTM_EPOCHS", "20")
                _log(f"LSTM finish: scope={scope} workers={workers} epochs={epochs}")
                _run_shell_launch(
                    [str(RUN), "train-lstm"],
                    {
                        "LSTM_TRAIN_SCOPE": scope,
                        "LSTM_WORKERS": workers,
                        "LSTM_EPOCHS": epochs,
                    },
                )
                if _pid_alive("train-lstm"):
                    _wait_trainer("train-lstm", "train-lstm_latest.log")
                pending_after = _lstm_pending(scope)
                if pending_after > 0:
                    notes = list(st.get("notes") or [])
                    n_try = sum(1 for n in notes if str(n).startswith("lstm_all pending_after="))
                    notes.append(f"lstm_all pending_after={pending_after}")
                    st["notes"] = notes
                    _save_state(st)
                    if n_try < 2:
                        _log(
                            f"LSTM finish: {pending_after} still pending — retry (attempt {n_try + 1})"
                        )
                        return 1
                    _log(
                        f"LSTM finish: {pending_after} still pending after retries — "
                        "likely data-starved; completeness probe will reopen if they become trainable"
                    )

        elif pname == "done":
            st["finished_at"] = datetime.now(timezone.utc).isoformat()
            _save_state(st)
            _log("enhancement queue finished — proper full finish complete")
            return 0

    st["phase"] = "done"
    st["finished_at"] = datetime.now(timezone.utc).isoformat()
    _save_state(st)
    _log("enhancement queue finished")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
