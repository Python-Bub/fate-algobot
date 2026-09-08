#!/usr/bin/env python3
"""Online / opportunistic trainer for short-history top100 names (SPCX).

SPCX stays in top100 market-cap but often has <<400 bars. We still train the
horizons that fit (short/long/daily; xlong when enough rows) so the universe
gap is not permanent. Safe to run on a loop whenever the bot is online.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _symbols(extra: list[str]) -> list[str]:
    from fortress_universe import load_top100_symbols

    top = {s.upper() for s in load_top100_symbols()}
    # Default: hard-skip names that are still listed in top100.
    hard = {
        x.strip().upper()
        for x in os.getenv("TOP100_ONLINE_SHORT_HIST", "SPCX").split(",")
        if x.strip()
    }
    out = sorted((hard | {s.upper() for s in extra}) & top)
    return out


def train_one(sym: str, *, min_top20: float, min_meta: float) -> dict:
    os.environ.setdefault("FILL_NULL_HEADS", "true")
    os.environ.setdefault("KEEP_WEAK_HEADS", "true")
    os.environ.setdefault("MULTI_HORIZON_TRAIN", "true")
    os.environ.setdefault("COALESCE_EXISTING_HEADS", "true")
    os.environ.setdefault("TRAIN_FORCE_YAHOO", "true")
    os.environ.setdefault("NETWORK_FIRST", "true")
    os.environ.setdefault("USE_PRICE_CACHE", "true")
    # Short listings: allow thin caches / short rows; skip 60d until history grows.
    os.environ["PRICE_CACHE_MIN_MULTI_HORIZON"] = os.getenv("SPCX_MIN_BARS", "30")
    os.environ["PRICE_CACHE_MAX_START_GAP_DAYS"] = "99999"
    os.environ["STRONG_MIN_ROWS_HEAD"] = os.getenv("SPCX_MIN_ROWS_HEAD", "25")
    os.environ["STRONG_MIN_ROWS_HEAD_FILL"] = "20"
    os.environ["STRONG_MIN_TRAIN_ROWS"] = os.getenv("SPCX_MIN_TRAIN_ROWS", "25")
    os.environ["MIN_TRAIN_ROWS"] = os.getenv("SPCX_MIN_TRAIN_ROWS", "25")
    os.environ["STRONG_USE_RANK_TARGETS"] = "false"  # direction labels need fewer bars
    os.environ["STRONG_N_EST"] = os.getenv("STRONG_N_EST", "80")
    os.environ["STRONG_BACKENDS"] = os.getenv("STRONG_BACKENDS", "lgb")
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"
    os.environ["MIN_TRAIN_ROWS"] = os.getenv("SPCX_MIN_TRAIN_ROWS", "25")

    from tools.retrain_top100_strong import strong_train_ticker

    # Prefer horizons that fit short history; include xlong only if enough bars later.
    heads = {"short", "long", "daily", "meta"}
    try:
        from feature_engineering import build_features

        df = build_features(sym, os.getenv("STRONG_TRAIN_DATA_START", "2010-01-01"), None)
        n = len(df)
        if n >= int(os.getenv("SPCX_XLONG_MIN_BARS", "120")):
            heads.add("xlong")
        print(f"[spcx-online] {sym} bars={n} heads={sorted(heads)}", flush=True)
    except Exception as e:
        print(f"[spcx-online] {sym} feature probe failed: {e}", flush=True)

    st = strong_train_ticker(sym, min_top20=min_top20, min_meta=min_meta, weak_heads=heads)
    path = ROOT / "models" / f"{sym}_model.pkl"
    ok = path.is_file() and not (st or {}).get("error")
    return {"ticker": sym, "ok": bool(ok), "path": str(path) if path.is_file() else None, "stats": st}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="*", default=[], help="Extra symbols (must be in top100)")
    ap.add_argument("--min-top20", type=float, default=0.28)
    ap.add_argument("--min-meta", type=float, default=0.40)
    ap.add_argument("--loop-sec", type=int, default=0, help="If >0, retry forever every N seconds")
    args = ap.parse_args()

    import time

    while True:
        syms = _symbols(list(args.symbols))
        if not syms:
            print("[spcx-online] no short-history top100 symbols to train", flush=True)
            return 0
        report = []
        for s in syms:
            try:
                report.append(train_one(s, min_top20=args.min_top20, min_meta=args.min_meta))
            except Exception as e:
                report.append({"ticker": s, "ok": False, "error": f"{type(e).__name__}: {e}"})
        out = ROOT / "data" / "spcx_online_train.json"
        out.write_text(json.dumps({"report": report}, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2, default=str), flush=True)
        if args.loop_sec <= 0:
            return 0 if all(r.get("ok") for r in report) else 1
        print(f"[spcx-online] sleeping {args.loop_sec}s…", flush=True)
        time.sleep(args.loop_sec)


if __name__ == "__main__":
    raise SystemExit(main())
