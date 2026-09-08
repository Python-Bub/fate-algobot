#!/usr/bin/env python3
"""Repeat the math/HFT quality suite so it is proven many times before open.

Default: 12 rounds of pytest + 1 HFT npm test.
Overnight:  --hours 8  (re-runs until wall clock elapses).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = [
    "tests/test_trade_math.py",
    "tests/test_hft_firm_risk.py",
    "tests/test_contract_select.py",
    "tests/test_bottom_fisher_math.py",
    "tests/test_industry_sector_fallback.py",
    "tests/test_feature_weights.py",
    "tests/test_tpm_pace.py",
    "tests/test_sleeve_weights.py",
    "tests/test_event_calendar.py",
    "tests/test_event_learn.py",
    "tests/test_event_ingenuity.py",
    "tests/test_proven_online.py",
    "tests/test_limit_pricing.py",
    "tests/test_earnings_gap_guard.py",
    "tests/test_hft_advanced_charts.py",
    "tests/test_alpaca_order_pace.py",
]
OUT = ROOT / "data" / "ops" / "math_soak_latest.json"


def _run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    tail = ((p.stdout or "") + (p.stderr or ""))[-4000:]
    return p.returncode, tail


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=int(os.getenv("MATH_SOAK_ROUNDS", "12")))
    ap.add_argument("--hours", type=float, default=0.0)
    ap.add_argument("--skip-hft", action="store_true")
    args = ap.parse_args()
    py = sys.executable
    rounds: list[dict] = []
    t_end = time.time() + args.hours * 3600 if args.hours > 0 else None
    n = 0
    failed = 0
    while True:
        n += 1
        t0 = time.time()
        code, tail = _run([py, "-m", "pytest", "-q", *TESTS], ROOT)
        rec = {"n": n, "pytest": code, "sec": round(time.time() - t0, 2)}
        if code != 0:
            failed += 1
            rec["tail"] = tail[-1500:]
        if not args.skip_hft and (n == 1 or n % 4 == 0):
            hcode, htail = _run(["npm", "test"], ROOT / "hft")
            rec["hft"] = hcode
            if hcode != 0:
                failed += 1
                rec["hft_tail"] = htail[-1500:]
        rounds.append(rec)
        print(f"[SOAK] round={n} pytest={code} elapsed={rec['sec']}s failed_so_far={failed}", flush=True)
        if t_end is None and n >= args.rounds:
            break
        if t_end is not None and time.time() >= t_end:
            break
        if failed and t_end is None:
            break
        if t_end is not None:
            time.sleep(float(os.getenv("MATH_SOAK_SLEEP_SEC", "25")))
    doc = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "rounds": n,
        "failed": failed,
        "ok": failed == 0,
        "detail": rounds[-8:],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    print(json.dumps({"ok": doc["ok"], "rounds": n, "failed": failed, "path": str(OUT)}))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
