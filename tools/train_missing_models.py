#!/usr/bin/env python3
"""
Train daily models for universe symbols that have no *_model.pkl on disk.

Order: top-100 by market cap first, then hash-shuffled rest (not alphabet-first cap).
One ticker at a time (sequential). Prunes false "done" entries from train_checkpoint.json.

Usage:
  ./venv/bin/python -u tools/train_missing_models.py
  TRAIN_MISSING_LIMIT=20 ./venv/bin/python -u tools/train_missing_models.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = ROOT / "data" / "train_checkpoint.json"


def _prune_checkpoint() -> tuple[int, int]:
    """Remove checkpoint 'done' symbols that never got a model file."""
    from model_trainer import training_saved_model

    if not CHECKPOINT.is_file():
        return 0, 0
    data = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    done = set(data.get("done", []))
    before = len(done)
    kept = sorted(s for s in done if training_saved_model(s))
    removed = before - len(kept)
    data["done"] = kept
    CHECKPOINT.write_text(json.dumps(data, indent=0), encoding="utf-8")
    return removed, len(kept)


def _pending_missing() -> list[str]:
    from fortress_universe import is_core_trainable_equity, prioritize_training_universe
    from model_trainer import training_saved_model
    from universe_provider import load_universe_with_cap

    universe = [s for s in load_universe_with_cap(max_symbols=None) if is_core_trainable_equity(s)]
    missing = [s for s in universe if not training_saved_model(s)]
    return prioritize_training_universe(missing)


def main() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))

    from data_platform.market_prices import configure_process_prices

    configure_process_prices(training=True)
    if os.getenv("TRAIN_FORCE_YAHOO", "false").lower() in ("1", "true", "yes"):
        os.environ["PRICE_DATA_SOURCE"] = "yfinance"
        os.environ["FORCE_YAHOO_PRICES"] = "true"

    from model_trainer import _train_single_ticker, training_saved_model
    from utils import log

    removed, kept = _prune_checkpoint()
    if removed:
        log.warning("[TRAIN-MISSING] pruned %d false-done checkpoint rows (kept %d with models)", removed, kept)

    pending = _pending_missing()
    lim = os.getenv("TRAIN_MISSING_LIMIT", "").strip()
    if lim.isdigit():
        pending = pending[: int(lim)]

    if not pending:
        log.info("[TRAIN-MISSING] nothing to train — every tradeable symbol has a model bundle")
        return 0

    log.info(
        "[TRAIN-MISSING] sequential training n=%d  first=%s  last=%s  letters=%s…",
        len(pending),
        pending[0],
        pending[-1],
        ",".join(sorted({s[0] for s in pending[:26]})),
    )

    saved_n = 0
    skip_n = 0
    fail_n = 0
    ck_done: set[str] = set()
    ck_failed: dict[str, str] = {}
    if CHECKPOINT.is_file():
        try:
            raw = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
            ck_done = set(raw.get("done", []))
            ck_failed = dict(raw.get("failed", {}))
        except Exception:
            pass

    for i, sym in enumerate(pending, 1):
        log.info("[TRAIN-MISSING] (%d/%d) %s", i, len(pending), sym)
        try:
            _train_single_ticker(sym)
            if training_saved_model(sym):
                saved_n += 1
                ck_done.add(sym)
                ck_failed.pop(sym, None)
                log.info("[TRAIN-MISSING] OK saved model %s", sym)
            else:
                skip_n += 1
                ck_done.discard(sym)
                ck_failed[sym] = "skipped_no_model"
                log.warning("[TRAIN-MISSING] skip (no model file) %s", sym)
        except Exception as e:
            fail_n += 1
            ck_done.discard(sym)
            ck_failed[sym] = f"{type(e).__name__}: {str(e)[:120]}"
            log.exception("[TRAIN-MISSING] failed %s", sym)

        CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)
        CHECKPOINT.write_text(
            json.dumps({"done": sorted(ck_done), "failed": ck_failed}, indent=0),
            encoding="utf-8",
        )

    log.info(
        "[TRAIN-MISSING] finished saved=%d skipped=%d failed=%d",
        saved_n,
        skip_n,
        fail_n,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
