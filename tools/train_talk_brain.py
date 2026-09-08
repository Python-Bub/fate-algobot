#!/usr/bin/env python3
"""Train the homemade talk brain (no cloud, no ollama)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=int(os.getenv("TALK_TRAIN_STEPS", "1200")))
    ap.add_argument("--seq", type=int, default=96)
    ap.add_argument("--batch", type=int, default=32)
    args = ap.parse_args()
    from intel.talk_brain import train

    print("[train-talk] training self-contained chat brain…", flush=True)
    meta = train(steps=args.steps, seq=args.seq, batch=args.batch)
    print(f"[train-talk] done → {meta.get('path')} loss={meta.get('final_loss'):.3f}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
