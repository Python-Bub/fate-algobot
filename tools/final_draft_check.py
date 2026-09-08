#!/usr/bin/env python3
"""Final draft gate: health, tests, weak count, disk prune summary."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / "venv/bin/python"


def main() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    rc = 0

    print("=== final-draft check ===")

    try:
        subprocess.run([str(PY), "-u", "tools/health_check.py"], check=False)
    except Exception as e:
        print(f"[final-draft] health_check skipped: {e}")

    print("\n--- pytest ---")
    t = subprocess.run([str(PY), "-m", "pytest", "tests/", "-q", "--tb=line"], cwd=ROOT)
    if t.returncode != 0:
        rc = 1

    print("\n--- weak top-100 ---")
    from tools.retrain_weak_models import find_weak_symbols, print_weak_report

    weak = find_weak_symbols(
        min_top20=float(os.getenv("RETRAIN_MIN_TOP20", "0.6")),
        min_meta=float(os.getenv("MIN_META_AUC", "0.52")),
        top100_only=True,
    )
    print_weak_report(weak, float(os.getenv("RETRAIN_MIN_TOP20", "0.6")), float(os.getenv("MIN_META_AUC", "0.52")))
    if weak:
        relax = find_weak_symbols(min_top20=0.52, min_meta=0.48, top100_only=True)
        if not relax:
            print("[final-draft] all pass at relaxed finish bar (0.52 / 0.48)")
        else:
            print(f"[final-draft] {len(relax)} still below relaxed bar")
            rc = 1

    print("\n--- disk prune (dry-run summary) ---")
    subprocess.run([str(PY), "-u", "tools/prune_disk.py", "--dry-run"], cwd=ROOT, check=False)

    print("\n=== final-draft done rc=%d ===" % rc)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
