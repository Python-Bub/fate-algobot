#!/usr/bin/env python3
"""One-shot priority daily rebuild for FORCE/STICK names (BX/SBUX/…)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

os.environ.setdefault("NETWORK_FIRST", "true")
os.environ["FRESH_MODEL_REBUILD"] = "true"
os.environ.setdefault("MULTI_HORIZON_TRAIN", "true")
os.environ.setdefault("HEAVY_NEWS_INTEL", "true")

NEED = ["BX", "SBUX", "META", "AMZN", "COST", "JNJ"]


def main() -> int:
    from model_trainer import _train_single_ticker

    ck = Path("data/train_checkpoint.json")
    d = json.loads(ck.read_text()) if ck.exists() else {"done": [], "failed": {}}
    need_set = set(NEED)
    d["done"] = [x for x in d.get("done", []) if str(x).upper() not in need_set]
    for s in list(d.get("failed", {})):
        if str(s).upper() in need_set:
            d["failed"].pop(s, None)
    ck.write_text(json.dumps(d, indent=0))

    rc = 0
    for sym in NEED:
        print(f"[priority] === training {sym} ===", flush=True)
        try:
            _train_single_ticker(sym)
            exists = Path(f"models/{sym}_model.pkl").exists()
            print(f"[priority] === done {sym} model_exists={exists} ===", flush=True)
            if not exists:
                rc = 1
        except Exception as e:
            print(f"[priority] FAIL {sym}: {e}", flush=True)
            rc = 1
    print("[priority] ALL COMPLETE", flush=True)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
