#!/usr/bin/env python3
"""Train talk brain on full open English dictionary (WordNet) — offline-capable."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Ingest Princeton WordNet (full open English defs) + retrain talk brain"
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=int(os.getenv("TALK_DICT_LIMIT", "0") or 0),
        help="Max entries (0 = all ~150k lemma-definition pairs)",
    )
    ap.add_argument("--every-n", type=int, default=1, help="Keep every Nth entry (1=all)")
    ap.add_argument("--steps", type=int, default=int(os.getenv("TALK_DICT_TRAIN_STEPS", "2500")))
    ap.add_argument("--corpus-only", action="store_true", help="Only write corpus, skip train")
    args = ap.parse_args()
    limit = args.limit if args.limit > 0 else None

    from intel.talk_opendict import ingest_and_train, save_corpus

    print(
        "[train-dict] open dictionary = Princeton WordNet via NLTK "
        "(~148k lemmas) — NOT Merriam-Webster (can't scrape their full dict)",
        flush=True,
    )
    if args.corpus_only:
        meta = save_corpus(limit=limit, every_n=args.every_n)
        print(json.dumps(meta, indent=2), flush=True)
        return 0

    out = ingest_and_train(steps=args.steps, limit=limit, every_n=args.every_n)
    c = out["corpus"]
    t = out["train"]
    print(
        f"[train-dict] corpus entries={c.get('entries')} chars={c.get('corpus_chars')} → {c.get('corpus_path')}",
        flush=True,
    )
    print(
        f"[train-dict] trained steps={t.get('steps')} loss={t.get('final_loss')} → {t.get('path')}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
