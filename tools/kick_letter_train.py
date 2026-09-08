#!/usr/bin/env python3
"""Kick letter-fair training focused on weak letters (F/O and low daily_pct).

Does NOT shrink universe or skip phases. Uses letter_rr + optional weak-letter
boost so under-covered first letters advance first within the fair scheduler.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def weak_letters() -> list[str]:
    p = ROOT / "data" / "ops" / "letter_training_coverage.json"
    if not p.is_file():
        return ["F", "O", "E", "R", "I"]
    doc = json.loads(p.read_text(encoding="utf-8"))
    letters = doc.get("letters") or []
    weak = []
    if isinstance(letters, list):
        rows = [r for r in letters if isinstance(r, dict)]
        rows.sort(key=lambda r: float(r.get("daily_pct") or 0))
        weak = [str(r.get("letter") or "").upper() for r in rows if float(r.get("daily_pct") or 0) < 1.5]
    # Always include F/O
    for L in ("F", "O"):
        if L not in weak:
            weak.insert(0, L)
    return [L for L in weak if L][:10]


def models_report() -> dict:
    models = ROOT / "models"
    n = len(list(models.glob("*_model.pkl"))) if models.is_dir() else 0
    gb = 0.0
    if models.is_dir():
        total = sum(f.stat().st_size for f in models.rglob("*") if f.is_file())
        gb = total / (1024**3)
    cov = {}
    p = ROOT / "data" / "ops" / "letter_training_coverage.json"
    if p.is_file():
        try:
            cov = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "models_n": n,
        "models_gb": round(gb, 2),
        "target_gb": cov.get("target_gb", 100),
        "progress_pct": round(100.0 * gb / float(cov.get("target_gb") or 100), 2),
        "universe_n": cov.get("universe_n"),
        "daily_n": cov.get("daily_n"),
        "train_prioritize": (cov.get("bias") or {}).get("train_prioritize"),
    }


def free_refetchable_caches() -> dict:
    """Free refetchable caches only — never models/."""
    cmd = [sys.executable, "-u", str(ROOT / "tools" / "prune_disk.py")]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return {"ok": r.returncode == 0, "stdout": (r.stdout or "")[-500:], "stderr": (r.stderr or "")[-300:]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def kick_train(*, workers: int = 4) -> dict:
    os.environ["TRAIN_PRIORITIZE"] = os.getenv("TRAIN_PRIORITIZE", "letter_rr")
    os.environ["TRAIN_WEAK_LETTER_BOOST"] = "true"
    os.environ["TRAIN_WEAK_LETTERS"] = ",".join(weak_letters())
    # Prefer missing-only gap fill — full capability, letter-fair
    logf = ROOT / "logs" / "letter_weak_train_latest.log"
    py = ROOT / "venv" / "bin" / "python"
    if not py.is_file():
        py = Path(sys.executable)
    cmd = [
        str(py),
        "-u",
        str(ROOT / "parallel_train.py"),
        "--pipeline",
        "daily",
        "--missing-only",
        "--workers",
        str(workers),
    ]
    # If an existing missing-only train is alive, do not duplicate — report it
    pid_path = ROOT / ".pids" / "train.pid"
    if pid_path.is_file():
        try:
            pid = int(pid_path.read_text().strip())
            os.kill(pid, 0)
            return {
                "ok": True,
                "already_running": True,
                "pid": pid,
                "weak_letters": weak_letters(),
                "note": "existing parallel_train alive — letter_rr continues; weak boost env set for next spawn",
            }
        except (OSError, ValueError):
            pass

    env = os.environ.copy()
    with logf.open("w", encoding="utf-8") as fh:
        proc = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT, env=env, cwd=str(ROOT))
    (ROOT / ".pids").mkdir(exist_ok=True)
    (ROOT / ".pids" / "letter-weak-train.pid").write_text(str(proc.pid), encoding="utf-8")
    return {
        "ok": True,
        "already_running": False,
        "pid": proc.pid,
        "weak_letters": weak_letters(),
        "log": str(logf),
        "cmd": " ".join(cmd),
    }


def main() -> int:
    report = models_report()
    print(json.dumps({"models": report}, indent=2))
    pruned = free_refetchable_caches()
    print(json.dumps({"prune_caches": {"ok": pruned.get("ok")}}, indent=2))
    kicked = kick_train(workers=int(os.getenv("LETTER_TRAIN_WORKERS", "4")))
    print(json.dumps({"train": kicked}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
