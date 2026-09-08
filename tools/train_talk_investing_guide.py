#!/usr/bin/env python3
"""Distill investing-guide 292 topics + deep chapters → talk brain Q&A, then optional retrain.

  ./run_all.sh train-talk-guide
  ./venv/bin/python -u tools/train_talk_investing_guide.py --no-train
"""

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
    ap.add_argument("--no-train", action="store_true", help="Only write corpus, skip CharLSTM steps")
    ap.add_argument("--steps", type=int, default=int(os.getenv("TALK_GUIDE_TRAIN_STEPS", "2500")))
    args = ap.parse_args()

    from intel.talk_investing_guide import save_investing_guide_corpus

    meta = save_investing_guide_corpus()
    print(
        f"[train-talk-guide] question bank complete: {meta['pairs']:,} pairs, remaining=0",
        flush=True,
    )
    if args.no_train:
        return 0

    os.environ.setdefault("TALK_FOCUS", "dialogue")
    os.environ.setdefault("TALK_DICT_WEIGHT", "0")
    os.environ.setdefault("TALK_INCLUDE_DICT", "false")
    from intel.talk_brain import train

    print(f"[train-talk-guide] retraining CharLSTM steps={args.steps}…", flush=True)
    tmeta = train(steps=args.steps, seq=96, batch=32)
    print(
        f"[train-talk-guide] brain → {tmeta.get('path')} loss={tmeta.get('final_loss'):.3f}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
