#!/usr/bin/env python3
"""Expand finance English lexicon via open WordNet (not Merriam-Webster dump)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

OUT = ROOT / "data" / "intel" / "english_lexicon_expanded.json"


def main() -> int:
    from intel.english_lexicon import expand_and_save_lexicon

    meta = expand_and_save_lexicon(OUT)
    print(json.dumps(meta, indent=2), flush=True)
    print(f"[train-english-lexicon] wrote {OUT} pos={meta.get('n_pos')} neg={meta.get('n_neg')}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
