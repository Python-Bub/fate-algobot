#!/usr/bin/env python3
"""Drop checkpoint failed[] entries when a real daily model exists on disk."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CK = ROOT / "data/train_checkpoint.json"


def main() -> int:
    sys.path.insert(0, str(ROOT))
    from model_trainer import training_saved_model

    if not CK.is_file():
        print("[reconcile] no checkpoint")
        return 0
    data = json.loads(CK.read_text(encoding="utf-8"))
    failed = dict(data.get("failed", {}))
    done = set(data.get("done", []))
    removed: list[str] = []
    for sym in list(failed):
        if training_saved_model(sym):
            removed.append(sym)
            failed.pop(sym, None)
            done.add(sym.upper())
    if not removed:
        print(f"[reconcile] nothing to fix ({len(failed)} failed remain)")
        return 0
    data["failed"] = failed
    data["done"] = sorted(done)
    tmp = CK.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=0), encoding="utf-8")
    tmp.replace(CK)
    print(f"[reconcile] cleared {len(removed)} false failures (model on disk)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
