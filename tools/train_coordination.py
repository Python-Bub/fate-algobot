"""Avoid competing parallel_train jobs (top100 vs IPO batch)."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def top100_training_active() -> bool:
    try:
        r = subprocess.run(
            ["pgrep", "-f", "train_top100_perfect.py"],
            capture_output=True,
            text=True,
        )
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        return False


def enhancement_queue_phase() -> str:
    p = ROOT / "data/enhancement_queue_state.json"
    if not p.is_file():
        return "unknown"
    try:
        import json

        return str(json.loads(p.read_text(encoding="utf-8")).get("phase", "unknown"))
    except Exception:
        return "unknown"


def strong_retrain_active() -> bool:
    try:
        r = subprocess.run(
            ["pgrep", "-f", "retrain_top100_strong.py"],
            capture_output=True,
            text=True,
        )
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        return False


def fill_null_active() -> bool:
    try:
        r = subprocess.run(
            ["pgrep", "-f", "fill_null_horizon_heads.py"],
            capture_output=True,
            text=True,
        )
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        return False


def should_defer_secondary_training() -> bool:
    if os.getenv("DEFER_SECONDARY_TRAIN", "true").lower() in ("0", "false", "no"):
        return False
    if top100_training_active():
        return True
    if strong_retrain_active() or fill_null_active():
        return True
    return enhancement_queue_phase() == "top100_perfect"


def stop_competing_daily_trainers() -> int:
    """Stop IPO/listing parallel_train workers; keep top100 (workers 4) running."""
    if not should_defer_secondary_training():
        return 0
    stopped = 0
    try:
        r = subprocess.run(
            ["pgrep", "-f", "parallel_train.py"],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            return 0
        for pid_s in r.stdout.split():
            try:
                pid = int(pid_s)
            except ValueError:
                continue
            try:
                env_r = subprocess.run(
                    ["ps", "-E", "-p", str(pid)],
                    capture_output=True,
                    text=True,
                )
                envtxt = env_r.stdout or ""
            except Exception:
                envtxt = ""
            if "train_top100_perfect" in envtxt:
                continue
            if "TRAIN_SYMBOLS_FILE" in envtxt or "new_listing" in envtxt:
                os.kill(pid, 15)
                stopped += 1
            elif "--workers 2" in (subprocess.run(
                ["ps", "-o", "args=", "-p", str(pid)], capture_output=True, text=True
            ).stdout or ""):
                os.kill(pid, 15)
                stopped += 1
    except Exception:
        pass
    return stopped


if __name__ == "__main__":
    n = stop_competing_daily_trainers()
    if n:
        print(f"[train-coord] stopped {n} competing parallel_train job(s)")
    else:
        print("[train-coord] no competing trainers stopped")
