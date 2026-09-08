#!/usr/bin/env python3
"""Fill null multi-horizon / meta heads inside existing daily pickles.

Why blanks happen
-----------------
Quality gates reject weak 1d/60d heads (`MIN_HEAD_TOP20`) and save the bundle with
`model_daily`/`model_xlong` = None. Stats JSON then omits those metrics, so the
weak-retrain queue never sees them. This tool scans pickles and forces a strong
refill with KEEP_WEAK_HEADS / FILL_NULL_HEADS so every timeframe has a calibrated
classifier (smart multi-TF / mean-rev stacks need all horizons, not just speed).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _blank_map(*, top100_only: bool) -> dict[str, list[str]]:
    from tools.retrain_weak_models import _null_heads_from_bundles
    from fortress_universe import load_top100_symbols

    uni = {s.upper() for s in load_top100_symbols()} if top100_only else None
    return _null_heads_from_bundles(uni)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top100-only", action="store_true", default=True)
    ap.add_argument("--all", action="store_true", help="Scan full models/ (not just top100)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--min-top20", type=float, default=0.40)
    ap.add_argument("--min-meta", type=float, default=0.50)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    top100_only = not args.all
    blanks = _blank_map(top100_only=top100_only)
    # Prefer null:daily / null:xlong / null:meta first (multi-TF stack).
    ordered = sorted(
        blanks.items(),
        key=lambda kv: (
            0 if any(x.startswith("null:daily") or x.startswith("null:xlong") for x in kv[1]) else 1,
            kv[0],
        ),
    )
    if args.limit > 0:
        ordered = ordered[: args.limit]

    out = ROOT / "data/fill_null_heads_queue.json"
    out.write_text(
        json.dumps({"n": len(ordered), "symbols": [s for s, _ in ordered], "detail": dict(ordered)}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    print(f"[fill-null] {len(ordered)} symbols with null heads → {out}")
    for s, reasons in ordered[:20]:
        print(f"  {s:8} {' | '.join(reasons)}")
    if len(ordered) > 20:
        print(f"  ... +{len(ordered) - 20} more")
    if args.dry_run or not ordered:
        return 0

    # Soft gates + keep weak: fill the slot, then strong loops can improve later.
    os.environ["FILL_NULL_HEADS"] = "true"
    os.environ["KEEP_WEAK_HEADS"] = "true"
    os.environ["MIN_HEAD_TOP20"] = str(args.min_top20)
    os.environ["RETRAIN_MIN_TOP20"] = str(max(args.min_top20, 0.45))
    os.environ["MIN_META_AUC"] = str(args.min_meta)
    os.environ["AUTO_RETRAIN_LOW_TOP20"] = "false"
    os.environ["STRONG_USE_RANK_TARGETS"] = "true"
    # Shorter causal rank window so 2y histories can still label 60d heads.
    os.environ["STRONG_RANK_WINDOW"] = os.getenv("STRONG_RANK_WINDOW", "120")
    os.environ["MULTI_HORIZON_TRAIN"] = "true"
    os.environ["HORIZON_USE_ENSEMBLE"] = "true"
    os.environ["NETWORK_FIRST"] = "true"
    # Prefer live history over fresh-but-truncated caches (~130d) that cannot train 60d heads.
    os.environ["USE_PRICE_CACHE"] = os.getenv("FILL_USE_PRICE_CACHE", "true")
    os.environ["PRICE_CACHE_MAX_START_GAP_DAYS"] = os.getenv("PRICE_CACHE_MAX_START_GAP_DAYS", "400")
    os.environ["PRICE_CACHE_MIN_MULTI_HORIZON"] = os.getenv("PRICE_CACHE_MIN_MULTI_HORIZON", "400")
    os.environ["MULTI_HORIZON_TRAIN"] = "true"
    os.environ["STRONG_TRAIN_DATA_START"] = os.getenv("STRONG_TRAIN_DATA_START", "2010-01-01")
    os.environ["USE_POLYGON_FIRST"] = os.getenv("USE_POLYGON_FIRST", "false")
    os.environ["TRAIN_FORCE_YAHOO"] = "true"

    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"

    from tools.retrain_top100_strong import strong_train_ticker
    from tools.retrain_weak_models import weak_heads_from_reasons

    saved = 0
    failed = 0
    for i, (sym, reasons) in enumerate(ordered, 1):
        heads = weak_heads_from_reasons(reasons)
        if not heads:
            heads = {"daily", "xlong", "meta"}
        print(f"[fill-null] ({i}/{len(ordered)}) {sym} heads={sorted(heads)}", flush=True)
        try:
            st = strong_train_ticker(
                sym, min_top20=args.min_top20, min_meta=args.min_meta, weak_heads=heads
            )
            if not st or st.get("strong_skipped"):
                print(f"[fill-null] {sym} skipped", flush=True)
                failed += 1
            else:
                saved += 1
                print(f"[fill-null] {sym} saved", flush=True)
        except Exception as e:
            failed += 1
            print(f"[fill-null] {sym} ERROR {type(e).__name__}: {e}", flush=True)

    print(f"[fill-null] done saved={saved} failed={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
