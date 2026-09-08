#!/usr/bin/env python3
"""Fail closed if critical trading files are empty (prevents silent wipe outages)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CRITICAL = [
    "run_all.sh",
    "fortress_live.py",
    "paper_sim_today.py",
    "fortress_portfolio.py",
    "alpaca_broker.py",
    "data/deploy_scale.env",
    "analytics/rank_pipeline.py",
    "analytics/limit_pricing.py",
    "analytics/earnings_gap_guard.py",
    "analytics/event_learn.py",
    "analytics/event_ingenuity.py",
    "analytics/proven_online.py",
    "analytics/sheldon_head.py",
    "analytics/algo_generation.py",
]


def main() -> int:
    bad: list[str] = []
    for rel in CRITICAL:
        p = ROOT / rel
        if not p.is_file() or p.stat().st_size < 200:
            bad.append(f"{rel} size={p.stat().st_size if p.is_file() else 'MISSING'}")
    if bad:
        print("[integrity] CRITICAL EMPTY/MISSING FILES:", file=sys.stderr)
        for b in bad:
            print(f"  - {b}", file=sys.stderr)
        print(
            "Restore from Cursor History or backup before trading.",
            file=sys.stderr,
        )
        return 2
    print("[integrity] ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
