#!/usr/bin/env python3
"""Queue tier-2 retrains for symbols that failed inference / weak heads outside top-100."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "data" / "tier2_retrain_queue.json"


def load_queue() -> list[str]:
    if not QUEUE.is_file():
        return []
    try:
        doc = json.loads(QUEUE.read_text(encoding="utf-8"))
        syms = doc.get("symbols") or doc
        return [str(s).upper() for s in syms if s]
    except Exception:
        return []


def save_queue(symbols: list[str], *, note: str = "") -> None:
    QUEUE.parent.mkdir(parents=True, exist_ok=True)
    uniq = list(dict.fromkeys(s.strip().upper() for s in symbols if s))
    QUEUE.write_text(json.dumps({"symbols": uniq, "note": note}, indent=0), encoding="utf-8")


def enqueue(symbols: list[str], *, note: str = "") -> list[str]:
    cur = load_queue()
    merged = list(dict.fromkeys(cur + [s.upper() for s in symbols if s]))
    save_queue(merged, note=note)
    return merged


def drain(limit: int | None = None) -> int:
    """Train up to `limit` tier-2 symbols (default TRAIN_TIER2_LIMIT env)."""
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    from data_platform.market_prices import configure_process_prices

    configure_process_prices(training=True)
    if os.getenv("TRAIN_FORCE_YAHOO", "false").lower() in ("1", "true", "yes"):
        os.environ["PRICE_DATA_SOURCE"] = "yfinance"
        os.environ["FORCE_YAHOO_PRICES"] = "true"

    from fortress_universe import is_top100_equity, prioritize_training_universe
    from model_trainer import _train_single_ticker, training_saved_model
    from tools.retrain_weak_models import find_weak_symbols

    raw = load_queue()
    relax_weak = find_weak_symbols(min_top20=0.52, min_meta=0.48, top100_only=True)
    # Do not tier2-retrain top100 names that already pass the relaxed quality bar (avoids overwriting strong bundles).
    pending_raw = [
        s
        for s in raw
        if not (is_top100_equity(s) and s not in relax_weak)
    ]
    pending = prioritize_training_universe(pending_raw)
    lim = limit if limit is not None else int(os.getenv("TRAIN_TIER2_LIMIT", "5"))
    pending = pending[: max(0, lim)]
    if not pending:
        return 0

    done = 0
    remain = [s for s in load_queue() if s not in pending]
    for sym in pending:
        print(f"[tier2] training {sym} …", flush=True)
        try:
            if _train_single_ticker(sym) and training_saved_model(sym):
                done += 1
            else:
                remain.append(sym)
        except Exception as e:
            print(f"[tier2] fail {sym}: {e}", flush=True)
            remain.append(sym)
    save_queue(remain, note="tier2 pending")
    print(f"[tier2] trained {done}/{len(pending)}", flush=True)
    return done


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Tier-2 retrain queue (inference failures, non-priority weak)")
    ap.add_argument("--enqueue", nargs="+", help="add symbols to queue")
    ap.add_argument("--drain", action="store_true", help="train next batch from queue")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    if args.enqueue:
        syms = enqueue(args.enqueue, note="manual enqueue")
        print(f"queue ({len(syms)}): {', '.join(syms[:20])}")
        return 0
    if args.drain:
        return 0 if drain() >= 0 else 1
    if args.list:
        syms = load_queue()
        print(f"queue ({len(syms)}): {', '.join(syms)}")
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
