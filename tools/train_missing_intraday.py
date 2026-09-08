#!/usr/bin/env python3
"""
Train real intraday bundles for symbols that already have a daily model but only a
placeholder (or missing) intraday file — this is what expands paper_sim active universe.

Sequential, letter round-robin. Prunes intraday checkpoint rows with no real bundle.

Env:
  TRAIN_MISSING_INTRADAY_LIMIT   cap queue size
  INTRADAY_LOOKBACK_DAYS         Alpaca minute history (default 240)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = ROOT / "data" / "intraday_train_checkpoint.json"


def _prune_intraday_checkpoint() -> int:
    from fortress_universe import has_trained_intraday_bundle

    if not CHECKPOINT.is_file():
        return 0
    data = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    done = set(data.get("done", []))
    before = len(done)
    kept = sorted(s for s in done if has_trained_intraday_bundle(s))
    removed = before - len(kept)
    data["done"] = kept
    CHECKPOINT.write_text(json.dumps(data, indent=0), encoding="utf-8")
    return removed


def _pending() -> list[str]:
    from fortress_universe import (
        has_trained_intraday_bundle,
        is_core_trainable_equity,
        prioritize_training_universe,
    )
    from model_trainer import training_saved_model

    model_dir = Path(os.getenv("MODEL_DIR", "models"))
    have_daily = [
        p.name[: -len("_model.pkl")].upper()
        for p in model_dir.glob("*_model.pkl")
        if p.stat().st_size > 1000 and is_core_trainable_equity(p.name[: -len("_model.pkl")].upper())
    ]
    need = [s for s in have_daily if training_saved_model(s) and not has_trained_intraday_bundle(s)]
    return prioritize_training_universe(need)


def main() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("ALPACA_INTRADAY_FEED", "iex")

    from fortress_universe import has_trained_intraday_bundle
    from intraday.intraday_trainer import train_intraday
    from utils import log

    removed = _prune_intraday_checkpoint()
    if removed:
        log.warning("[INTRADAY-GAP] pruned %d false-done intraday checkpoint rows", removed)

    pending = _pending()
    lim = os.getenv("TRAIN_MISSING_INTRADAY_LIMIT", "").strip()
    if lim.isdigit():
        pending = pending[: int(lim)]

    if not pending:
        log.info("[INTRADAY-GAP] all daily symbols already have real intraday bundles")
        return 0

    log.info(
        "[INTRADAY-GAP] sequential n=%d  first=%s  last=%s",
        len(pending),
        pending[0],
        pending[-1],
    )

    ck_done: set[str] = set()
    if CHECKPOINT.is_file():
        try:
            ck_done = set(json.loads(CHECKPOINT.read_text(encoding="utf-8")).get("done", []))
        except Exception:
            pass

    saved_n = 0
    ph_n = 0
    fail_n = 0
    for i, sym in enumerate(pending, 1):
        log.info("[INTRADAY-GAP] (%d/%d) %s", i, len(pending), sym)
        try:
            rep = train_intraday(sym)
            if has_trained_intraday_bundle(sym):
                saved_n += 1
                ck_done.add(sym)
                log.info("[INTRADAY-GAP] OK real intraday %s", sym)
            else:
                ph_n += 1
                ck_done.discard(sym)
                log.warning("[INTRADAY-GAP] placeholder only %s (%s)", sym, rep.get("skipped"))
        except Exception:
            fail_n += 1
            ck_done.discard(sym)
            log.exception("[INTRADAY-GAP] failed %s", sym)

        CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)
        CHECKPOINT.write_text(json.dumps({"done": sorted(ck_done)}, indent=0), encoding="utf-8")

    log.info("[INTRADAY-GAP] finished real=%d placeholder=%d failed=%d", saved_n, ph_n, fail_n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
