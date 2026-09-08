#!/usr/bin/env python3
"""Teach talk brain polished English + typo understanding, then retrain."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)


def main() -> int:
    from intel.talk_grammar import save_grammar_corpus
    from intel.talk_culture import save_culture_corpus
    from intel.talk_brain import train

    # Grammar + slang/culture retrain: do not let WordNet drown dialogue structure.
    os.environ.setdefault("TALK_FOCUS", "grammar")
    os.environ.setdefault("TALK_DICT_WEIGHT", "0")
    os.environ.setdefault("TALK_EMBED", "128")
    os.environ.setdefault("TALK_HIDDEN", "384")
    os.environ.setdefault("TALK_LAYERS", "2")

    gmeta = save_grammar_corpus()
    cmeta = save_culture_corpus()
    print(f"[train-grammar] grammar corpus {gmeta}", flush=True)
    print(f"[train-grammar] culture corpus {cmeta}", flush=True)
    steps = int(os.getenv("TALK_GRAMMAR_TRAIN_STEPS", "5000"))
    print(
        f"[train-grammar] training larger brain for {steps} steps "
        f"(focus={os.environ.get('TALK_FOCUS')}, dict_weight={os.environ.get('TALK_DICT_WEIGHT')})…",
        flush=True,
    )
    out = train(
        steps=steps,
        seq=int(os.getenv("TALK_DICT_SEQ", "128")),
        batch=int(os.getenv("TALK_GRAMMAR_BATCH", "40")),
        lr=float(os.getenv("TALK_GRAMMAR_LR", "2.5e-3")),
    )
    print(
        f"[train-grammar] done loss={out.get('final_loss')} avg50={out.get('avg_loss_last50')} → {out.get('path')}",
        flush=True,
    )
    print(
        json.dumps(
            {
                "grammar_corpus": gmeta,
                "culture_corpus": cmeta,
                "train": {
                    k: out.get(k)
                    for k in (
                        "steps",
                        "final_loss",
                        "avg_loss_last50",
                        "vocab",
                        "corpus_chars",
                        "focus",
                        "dict_pair_budget",
                        "path",
                    )
                },
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
