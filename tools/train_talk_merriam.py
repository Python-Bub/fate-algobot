#!/usr/bin/env python3
"""Ingest Merriam-Webster WOTD RSS + retrain talk brain. Opens MW in browser."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)


def main() -> int:
    from intel.talk_merriam import ingest_and_train

    print("[train-merriam] fetching Merriam-Webster Word of the Day RSS…", flush=True)
    out = ingest_and_train(
        steps=int(os.getenv("TALK_MERRIAM_TRAIN_STEPS", "1500")),
        open_browser=os.getenv("TALK_MERRIAM_OPEN_BROWSER", "true").lower()
        in ("1", "true", "yes"),
    )
    print(json.dumps({k: out[k] for k in ("words", "corpus", "browser")}, indent=2), flush=True)
    tr = out.get("train") or {}
    print(
        f"[train-merriam] trained steps={tr.get('steps')} loss={tr.get('final_loss')} → {tr.get('path')}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
