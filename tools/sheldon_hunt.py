#!/usr/bin/env python3
"""Sheldon hunt: score the whole trained book, rewrite the bests board.

  ./venv/bin/python tools/sheldon_hunt.py --once
  ./run_all.sh sheldon-hunt
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()
    pause = float(os.getenv("SHELDON_HUNT_LOOP_SEC", "120"))

    from analytics.sheldon_head import hunt

    while True:
        payload = hunt()
        hot = payload.get("hot") or []
        print(
            json.dumps(
                {
                    "generation": payload.get("generation"),
                    "scanned": payload.get("scanned"),
                    "paper_scores": payload.get("paper_scores"),
                    "hot": hot[:12],
                },
                indent=2,
            ),
            flush=True,
        )
        if args.once:
            return 0
        time.sleep(max(30.0, pause))


if __name__ == "__main__":
    raise SystemExit(main())
