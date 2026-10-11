#!/usr/bin/env python3
"""Train missing per-ticker LSTM heads (models/lstm/{TICKER}_lstm.pt).

Requires an existing daily model bundle. Default scope: paper-active universe only
(fastest path to better paper_sim). Set LSTM_TRAIN_SCOPE=all for every daily model.

Usage:
  ./venv/bin/python -u tools/train_lstm_heads.py
  LSTM_TRAIN_SCOPE=all LSTM_WORKERS=4 ./venv/bin/python -u tools/train_lstm_heads.py
"""
from __future__ import annotations

import json
import multiprocessing as mp
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = ROOT / "data" / "lstm_train_checkpoint.json"


def _load_ck() -> tuple[set[str], dict[str, str]]:
    if not CHECKPOINT.is_file():
        return set(), {}
    try:
        data = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    except Exception:
        return set(), {}
    return set(data.get("done", [])), dict(data.get("failed", {}))


def _save_ck(done: set[str], failed: dict[str, str]) -> None:
    CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)
    tmp = CHECKPOINT.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps({"done": sorted(done), "failed": failed}, indent=0),
        encoding="utf-8",
    )
    os.replace(tmp, CHECKPOINT)


PERMANENT_LSTM_SKIP = frozenset(
    {"too_few_rows", "no_features", "no_daily_model", "exists"}
)


def _pending_symbols() -> list[str]:
    from analytics.lstm_head import has_quality_lstm_head, lstm_head_needs_upgrade
    from fortress_universe import prioritize_training_universe, symbols_paper_active_universe
    from model_trainer import training_saved_model

    done, failed = _load_ck()
    skip_perm = os.getenv("LSTM_SKIP_PERMANENT_FAILED", "true").lower() in ("1", "true", "yes")
    requeue_weak = os.getenv("LSTM_REQUEUE_WEAK", "true").lower() in ("1", "true", "yes")

    scope = os.getenv("LSTM_TRAIN_SCOPE", "active").strip().lower()
    if scope in ("top100", "top_100", "mega"):
        from fortress_universe import load_top100_symbols

        syms = load_top100_symbols()
    elif scope in ("top50", "top50pct", "half", "top_half"):
        from fortress_universe import load_top50pct_symbols

        syms = load_top50pct_symbols()
    elif scope in ("all", "daily", "universe"):
        from fortress_universe import is_core_trainable_equity

        model_dir = Path(os.getenv("MODEL_DIR", "models"))
        syms = sorted(
            {
                p.name[: -len("_model.pkl")].upper()
                for p in model_dir.glob("*_model.pkl")
                if p.stat().st_size > 1000
                and training_saved_model(p.name[: -len("_model.pkl")].upper())
                and is_core_trainable_equity(p.name[: -len("_model.pkl")].upper())
            }
        )
    else:
        syms = symbols_paper_active_universe()

    pending: list[str] = []
    for s in syms:
        if requeue_weak:
            if has_quality_lstm_head(s) and not lstm_head_needs_upgrade(s):
                continue
        else:
            from analytics.lstm_head import has_lstm_head

            if has_lstm_head(s) and not lstm_head_needs_upgrade(s):
                continue
        if skip_perm:
            reason = str(failed.get(s, "")).strip()
            # Stale no_daily_model: daily pickle may have appeared since last fail.
            if reason == "no_daily_model" and training_saved_model(s):
                failed.pop(s, None)
                reason = ""
            # Allow requeue_* reasons through.
            if reason in PERMANENT_LSTM_SKIP or (
                reason.startswith("no_") and not reason.startswith("requeue_")
            ):
                continue
        pending.append(s)
    return prioritize_training_universe(pending)


def _train_one(sym: str) -> tuple[str, bool, str]:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    from data_platform.market_prices import configure_process_prices

    configure_process_prices(training=True)
    if os.getenv("TRAIN_FORCE_YAHOO", "false").lower() in ("1", "true", "yes"):
        os.environ["PRICE_DATA_SOURCE"] = "yfinance"
        os.environ["FORCE_YAHOO_PRICES"] = "true"
    try:
        from analytics.lstm_head import has_quality_lstm_head, lstm_head_needs_upgrade, train_lstm_head
        from model_trainer import build_training_frame_for_lstm, training_saved_model

        sym = sym.upper()
        if not training_saved_model(sym):
            return sym, False, "no_daily_model"
        if has_quality_lstm_head(sym) and not lstm_head_needs_upgrade(sym):
            return sym, True, "exists"
        built = build_training_frame_for_lstm(sym)
        if built is None:
            return sym, False, "no_features"
        df, feat_cols = built
        res = train_lstm_head(sym, df, feat_cols, target_col="target_long", force=True)
        if res.get("saved"):
            return sym, True, str(res["saved"])
        return sym, False, str(res.get("skipped", "unknown"))
    except Exception as e:
        return sym, False, f"{type(e).__name__}: {str(e)[:120]}"


def main() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))

    from analytics.lstm_head import _TORCH_OK
    from utils import log

    if not _TORCH_OK:
        log.error("[LSTM-BATCH] PyTorch not available — pip install torch")
        return 1

    done, failed = _load_ck()
    pending = _pending_symbols()
    lim = os.getenv("LSTM_TRAIN_LIMIT", "").strip()
    if lim.isdigit():
        pending = pending[: int(lim)]

    if not pending:
        # Honest accounting — permanent skips ≠ "have heads".
        done, failed = _load_ck()
        perm = {
            s: r
            for s, r in failed.items()
            if str(r).strip() in PERMANENT_LSTM_SKIP or str(r).startswith("no_")
        }
        log.info(
            "[LSTM-BATCH] nothing pending — have_heads_or_done=%d permanent_skips=%d "
            "(not all symbols necessarily trained; skips=%s)",
            len(done),
            len(perm),
            {k: perm[k] for k in list(perm)[:5]} if perm else {},
        )
        return 0

    workers = max(1, int(os.getenv("LSTM_WORKERS", "2")))
    scope = os.getenv("LSTM_TRAIN_SCOPE", "active")
    log.info(
        "[LSTM-BATCH] scope=%s  pending=%d  workers=%d  first=%s",
        scope,
        len(pending),
        workers,
        pending[0],
    )

    started = time.time()
    ok_n = fail_n = 0
    if workers == 1:
        results = [_train_one(s) for s in pending]
    else:
        ctx = mp.get_context("spawn")
        with ctx.Pool(workers) as pool:
            results = pool.map(_train_one, pending, chunksize=1)

    for sym, ok, err in results:
        if ok:
            done.add(sym)
            failed.pop(sym, None)
            ok_n += 1
        else:
            failed[sym] = err
            fail_n += 1
        if (ok_n + fail_n) % 25 == 0:
            _save_ck(done, failed)
            rate = (ok_n + fail_n) / max(time.time() - started, 1.0) * 60
            left = len(pending) - ok_n - fail_n
            eta_h = left / max(rate, 1e-6) / 60.0
            log.info(
                "[LSTM-BATCH] %d/%d  saved=%d  failed=%d  rate=%.1f/min  ETA=%.1fh",
                ok_n + fail_n,
                len(pending),
                ok_n,
                fail_n,
                rate,
                eta_h,
            )

    _save_ck(done, failed)
    log.info("[LSTM-BATCH] complete  saved=%d  failed=%d  total_lstm=%d", ok_n, fail_n, len(done))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
