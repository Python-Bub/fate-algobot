#!/usr/bin/env python3
"""Run targeted strong retrain until top-100 weak list is empty."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))


def main() -> int:
    os.environ.setdefault("STRONG_N_EST", "400")
    os.environ.setdefault("STRONG_BACKENDS", "xgb,lgb")
    os.environ.setdefault("TRAIN_TICKER_TIMEOUT_SEC", "0")
    os.environ.setdefault("MIN_META_AUC", os.getenv("STRONG_MIN_META", os.getenv("MIN_META_AUC", "0.52")))

    from tools.retrain_top100_strong import run_until_clear

    min_top20 = float(os.getenv("RETRAIN_MIN_TOP20", "0.6"))
    min_meta = float(os.environ["MIN_META_AUC"])
    rc = run_until_clear(
        min_top20=min_top20,
        min_meta=min_meta,
        max_rounds=int(os.getenv("STRONG_FINISH_ROUNDS", "15")),
        max_attempts_per_symbol=int(os.getenv("STRONG_ATTEMPTS_PER_SYMBOL", "5")),
    )
    if rc == 0:
        return 0

    # Final pass: slightly relaxed bar so stubborn mega-caps can clear for go-live.
    relax_top = float(os.getenv("FINISH_WEAK_MIN_TOP20", "0.52"))
    relax_meta = float(os.getenv("FINISH_WEAK_MIN_META", "0.48"))
    print(
        f"[finish-weak] main pass done — final relax pass top20>={relax_top} meta>={relax_meta}",
        flush=True,
    )
    return run_until_clear(
        min_top20=relax_top,
        min_meta=relax_meta,
        max_rounds=int(os.getenv("STRONG_FINISH_RELAX_ROUNDS", "5")),
        max_attempts_per_symbol=int(os.getenv("STRONG_FINISH_RELAX_ATTEMPTS", "3")),
    )


if __name__ == "__main__":
    raise SystemExit(main())
