"""
Compact existing trained model bundles in models/:

  - Strip deprecated heads (`model_svm_rbf`, `model_rf_aux`, duplicate `model`)
    that the prediction path treats as optional (falls back gracefully).
  - Re-save with `joblib.dump(..., compress=3)` — typical 3-5x shrink, no
    quality change.

Safe to run while training is paused.  Skips any file that's been touched in
the last 60s (the trainer might be writing it right now).

Usage:
    ./venv/bin/python -m tools.compact_models           # all *_model.pkl
    ./venv/bin/python -m tools.compact_models AAPL MSFT # explicit list
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

import joblib

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("compact")

LEGACY_KEYS = ("model_svm_rbf", "model_rf_aux", "model")
REQUIRED_KEYS = ("model_short", "model_long", "model_daily", "model_xlong")


def compact_one(path: Path, compress: int = 3, keep_aux: bool = False) -> tuple[int, int]:
    """Return (before_bytes, after_bytes).  0,0 if skipped."""
    if time.time() - path.stat().st_mtime < 60:
        log.info("skip recent: %s", path.name)
        return 0, 0
    try:
        bundle = joblib.load(path)
    except Exception as e:
        log.warning("load failed: %s (%s)", path.name, e)
        return 0, 0

    # Must have at least one of the new horizon heads or we leave it alone.
    if not any(k in bundle for k in REQUIRED_KEYS):
        log.warning("legacy-only bundle (no new heads), skip: %s", path.name)
        return 0, 0

    before = path.stat().st_size
    if not keep_aux:
        for k in LEGACY_KEYS:
            bundle.pop(k, None)

    tmp = path.with_suffix(".pkl.compact.tmp")
    joblib.dump(bundle, tmp, compress=compress)
    os.replace(tmp, path)
    after = path.stat().st_size
    return before, after


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tickers", nargs="*", help="optional explicit ticker list (default: all *_model.pkl)")
    ap.add_argument("--compress", type=int, default=3, help="joblib compress level 0..9")
    ap.add_argument("--keep-aux", action="store_true", help="keep legacy svm/rf heads")
    ap.add_argument("--models-dir", default="models")
    args = ap.parse_args()

    root = Path(args.models_dir)
    if args.tickers:
        targets = [root / f"{t.upper()}_model.pkl" for t in args.tickers]
        targets = [t for t in targets if t.is_file()]
    else:
        targets = sorted(root.glob("*_model.pkl"))

    if not targets:
        log.error("no model bundles found in %s", root)
        return 1

    total_before = 0
    total_after = 0
    n = 0
    for i, p in enumerate(targets, 1):
        before, after = compact_one(p, compress=args.compress, keep_aux=args.keep_aux)
        if before == 0:
            continue
        total_before += before
        total_after += after
        n += 1
        if i % 25 == 0 or i == len(targets):
            saved = (total_before - total_after) / 1e6
            ratio = total_after / total_before if total_before else 1.0
            log.info(
                "(%d/%d) running total: -%0.1f MB (compact ratio %.2fx) over %d files",
                i,
                len(targets),
                saved,
                1.0 / ratio if ratio > 0 else 0,
                n,
            )

    saved_gb = (total_before - total_after) / 1e9
    log.info("DONE: %d files, freed %.2f GB (avg %.1f%% size reduction)",
             n,
             saved_gb,
             100.0 * (1 - (total_after / total_before)) if total_before else 0,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
