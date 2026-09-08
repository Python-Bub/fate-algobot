#!/usr/bin/env python3
"""Train missing priority alts (IBIT / BTC-USD / ETH-USD) without wiping existing models."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

os.environ.setdefault("NETWORK_FIRST", "true")
os.environ.setdefault("FAST_UNIVERSE_TRAIN", "false")
os.environ.setdefault("MULTI_HORIZON_TRAIN", "true")
os.environ.setdefault("TRAIN_TIME_ORDER_SPLIT", "true")
os.environ.setdefault("FILL_NULL_HEADS", "true")
os.environ.setdefault("KEEP_WEAK_HEADS", "true")
os.environ["FRESH_MODEL_REBUILD"] = "false"

NEED = ["IBIT", "BTC-USD", "ETH-USD", "SLV", "GLD", "USO"]


def main() -> int:
    from model_trainer import _train_single_ticker, training_saved_model

    rc = 0
    for sym in NEED:
        exists = training_saved_model(sym)
        print(f"[alts] {sym} exists={exists} — training", flush=True)
        try:
            ok = _train_single_ticker(sym)
            print(f"[alts] {sym} saved={ok} file={training_saved_model(sym)}", flush=True)
            if not training_saved_model(sym):
                rc = 1
        except Exception as e:
            print(f"[alts] FAIL {sym}: {e}", flush=True)
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
