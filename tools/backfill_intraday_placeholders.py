#!/usr/bin/env python3
"""Write neutral ``*_intraday.pkl`` files for symbols that do not have one yet.

Existing real models are never overwritten. Use after changing intraday training
so checkpoint ``done`` and on-disk bundles stay aligned, or to pre-fill the universe.

Examples:
  python tools/backfill_intraday_placeholders.py
  python tools/backfill_intraday_placeholders.py --checkpoint-only
  python tools/backfill_intraday_placeholders.py --limit 100
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--checkpoint-only",
        action="store_true",
        help="Only symbols in data/intraday_train_checkpoint.json done[] (not full universe)",
    )
    ap.add_argument("--limit", type=int, default=None, help="stop after this many new files")
    args = ap.parse_args()

    sys.path.insert(0, str(ROOT))
    from intraday.intraday_trainer import MODEL_DIR, save_intraday_placeholder

    if args.checkpoint_only:
        ck_path = ROOT / "data" / "intraday_train_checkpoint.json"
        syms = [str(s).upper() for s in json.loads(ck_path.read_text()).get("done", [])]
    else:
        from universe_provider import load_universe_with_cap

        syms = [str(s).upper() for s in load_universe_with_cap(max_symbols=None)]

    written = 0
    skipped = 0
    for i, sym in enumerate(syms, 1):
        p = MODEL_DIR / f"{sym}_intraday.pkl"
        if p.is_file():
            skipped += 1
            continue
        save_intraday_placeholder(
            sym,
            "backfill_missing_file",
            rows=0,
            start=None,
            record_stats=False,
            quiet=True,
        )
        written += 1
        if written % 500 == 0:
            print(f"... wrote {written} placeholders ({i}/{len(syms)} symbols scanned)", flush=True)
        if args.limit is not None and written >= args.limit:
            break

    print(f"Done. Wrote {written} placeholder bundle(s); skipped {skipped} (already on disk).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
