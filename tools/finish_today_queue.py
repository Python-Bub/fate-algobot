#!/usr/bin/env python3
"""Finish trading-ready training today: active LSTM + priority daily retries. Skips LSTM-all."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "run_all.sh"
PY = ROOT / "venv/bin/python"
STATE = ROOT / "data/finish_today_state.json"
SYMS_FILE = ROOT / "data/finish_today_symbols.json"
CK_DAILY = ROOT / "data/train_checkpoint.json"


def _log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}Z] {msg}", flush=True)


def _pid_alive(name: str) -> bool:
    pf = ROOT / ".pids" / f"{name}.pid"
    if not pf.is_file():
        return False
    try:
        os.kill(int(pf.read_text().strip()), 0)
        return True
    except OSError:
        return False


def _wait_trainer(name: str, log_name: str, poll: int = 60) -> None:
    log = ROOT / "logs" / log_name
    _log(f"waiting for {name}…")
    while _pid_alive(name):
        time.sleep(poll)
    tail = log.read_text(encoding="utf-8", errors="ignore")[-100_000:] if log.is_file() else ""
    if "[PARALLEL] all workers complete" in tail or "LSTM] complete" in tail:
        _log(f"{name} complete")
    else:
        _log(f"{name} stopped")


def _build_symbol_list() -> list[str]:
    sys.path.insert(0, str(ROOT))
    from analytics.lstm_head import has_lstm_head
    from fortress_universe import load_top100_symbols, symbols_paper_active_universe

    syms: set[str] = set(load_top100_symbols())
    for s in symbols_paper_active_universe():
        if not has_lstm_head(s):
            syms.add(s)
    if CK_DAILY.is_file():
        try:
            data = json.loads(CK_DAILY.read_text(encoding="utf-8"))
            for s in (data.get("failed") or {}):
                if s.upper() in syms:
                    syms.add(s.upper())
        except Exception:
            pass
    return sorted(syms)


def _uncfail_daily(symbols: list[str]) -> int:
    if not CK_DAILY.is_file():
        return 0
    data = json.loads(CK_DAILY.read_text(encoding="utf-8"))
    failed = dict(data.get("failed") or {})
    allow = {s.upper() for s in symbols}
    n = 0
    for s in list(failed):
        if s in allow:
            failed.pop(s, None)
            n += 1
    if n:
        data["failed"] = failed
        CK_DAILY.write_text(json.dumps(data, indent=0), encoding="utf-8")
    return n


def _run(cmd: list[str], env: dict | None = None) -> None:
    e = os.environ.copy()
    if env:
        e.update({k: str(v) for k, v in env.items()})
    _log("exec: " + " ".join(cmd))
    subprocess.call(cmd, cwd=ROOT, env=e)
    time.sleep(2)


def main() -> int:
    os.chdir(ROOT)
    syms = _build_symbol_list()
    SYMS_FILE.write_text(json.dumps(syms, indent=0), encoding="utf-8")
    _log(f"priority symbols: {len(syms)}")

    st = {"phase": "lstm_active", "started_at": datetime.now(timezone.utc).isoformat()}
    STATE.write_text(json.dumps(st, indent=2), encoding="utf-8")

    sys.path.insert(0, str(ROOT))
    from tools.train_lstm_heads import _pending_symbols

    os.environ["LSTM_TRAIN_SCOPE"] = "active"
    pending_lstm = len(_pending_symbols())
    _log(f"LSTM active pending: {pending_lstm}")

    if pending_lstm > 0:
        if not _pid_alive("train-lstm"):
            _run(
                [str(RUN), "train-lstm"],
                {"LSTM_TRAIN_SCOPE": "active", "LSTM_WORKERS": "4", "LSTM_EPOCHS": "12"},
            )
        if _pid_alive("train-lstm"):
            _wait_trainer("train-lstm", "train-lstm_latest.log")

    st["phase"] = "daily_priority"
    STATE.write_text(json.dumps(st, indent=2), encoding="utf-8")

    unc = _uncfail_daily(syms)
    if unc:
        _log(f"cleared {unc} failed checkpoint rows for retry")

    # Only symbols still missing a saved daily model
    from model_trainer import training_saved_model

    need_daily = [s for s in syms if not training_saved_model(s)]
    if need_daily:
        SYMS_FILE.write_text(json.dumps(need_daily, indent=0), encoding="utf-8")
        _log(f"daily retry queue: {len(need_daily)} symbols")
        if not _pid_alive("train"):
            _run(
                [str(RUN), "train-missing-proper"],
                {
                    "TRAIN_SYMBOLS_FILE": str(SYMS_FILE),
                    "TRAIN_MISSING_WORKERS": os.getenv("FINISH_TODAY_WORKERS", "4"),
                },
            )
        if _pid_alive("train"):
            _wait_trainer("train", "train_latest.log")
    else:
        _log("all priority symbols already have daily models")

    st["phase"] = "done"
    st["finished_at"] = datetime.now(timezone.utc).isoformat()
    STATE.write_text(json.dumps(st, indent=2), encoding="utf-8")
    _log("finish-today done — active LSTM + priority daily. Skipped LSTM-all (~3.8k).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
