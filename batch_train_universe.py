#!/usr/bin/env python3
"""Batch-train the full US-listed universe with checkpoint resume."""

import argparse
import os

from dotenv import load_dotenv

load_dotenv()

from model_trainer import train_universe_batch
from utils import log


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-symbols", type=int, default=None)
    ap.add_argument("--refresh-universe", action="store_true")
    ap.add_argument("--checkpoint", default="data/train_checkpoint.json")
    args = ap.parse_args()

    os.environ.setdefault("FAST_UNIVERSE_TRAIN", "true")
    log.info("[CLI] FAST_UNIVERSE_TRAIN=%s", os.getenv("FAST_UNIVERSE_TRAIN"))

    train_universe_batch(
        max_symbols=args.max_symbols,
        refresh_universe=args.refresh_universe,
        checkpoint_path=args.checkpoint,
    )


if __name__ == "__main__":
    main()
