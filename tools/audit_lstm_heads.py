#!/usr/bin/env python3
"""Audit LSTM heads for fakes / weak holdout accuracy. Never deletes models.

By default:
  - reports tiny / corrupt / missing-state / weak test_acc heads
  - with --requeue: clears checkpoint 'done' + marks failed as weak so train-lstm
    will rebuild (keeps the .pt until overwrite — optimize, never remove)

Usage:
  ./venv/bin/python -u tools/audit_lstm_heads.py
  ./venv/bin/python -u tools/audit_lstm_heads.py --requeue --min-acc 0.45
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
CK = ROOT / "data" / "lstm_train_checkpoint.json"
OUT = ROOT / "data" / "lstm_head_audit.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-acc", type=float, default=float(os.getenv("LSTM_MIN_TEST_ACC", "0.45") or 0.45))
    ap.add_argument("--limit", type=int, default=0, help="0 = all heads")
    ap.add_argument("--requeue", action="store_true", help="Mark weak/corrupt for LSTM retrain")
    args = ap.parse_args()

    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    os.environ["LSTM_MIN_TEST_ACC"] = str(args.min_acc)

    from analytics.lstm_head import MODEL_DIR, lstm_head_quality
    from utils import log

    paths = sorted(MODEL_DIR.glob("*_lstm.pt"))
    if args.limit > 0:
        paths = paths[: args.limit]

    rows = []
    for p in paths:
        sym = p.name[: -len("_lstm.pt")].upper()
        rows.append(lstm_head_quality(sym))

    by_reason = Counter(str(r.get("reason")) for r in rows)
    weak = [r for r in rows if not r.get("ok")]
    payload = {
        "n_heads": len(rows),
        "n_ok": sum(1 for r in rows if r.get("ok")),
        "n_weak": len(weak),
        "min_acc": args.min_acc,
        "by_reason": dict(by_reason),
        "weak": weak[:500],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    log.info(
        "[LSTM-AUDIT] heads=%d ok=%d weak=%d reasons=%s → %s",
        payload["n_heads"],
        payload["n_ok"],
        payload["n_weak"],
        dict(by_reason),
        OUT,
    )

    if args.requeue and weak:
        done: set[str] = set()
        failed: dict[str, str] = {}
        if CK.is_file():
            try:
                data = json.loads(CK.read_text(encoding="utf-8"))
                done = set(data.get("done", []))
                failed = dict(data.get("failed", {}))
            except Exception:
                pass
        for r in weak:
            sym = str(r["ticker"]).upper()
            done.discard(sym)
            failed[sym] = f"requeue_{r.get('reason', 'weak')}"
            # Do NOT delete .pt — train_lstm_head(force=True) overwrites.
        tmp = CK.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"done": sorted(done), "failed": failed}, indent=0), encoding="utf-8")
        os.replace(tmp, CK)
        log.info("[LSTM-AUDIT] requeued %d weak/corrupt heads into checkpoint (files kept)", len(weak))

    print(json.dumps({"n_ok": payload["n_ok"], "n_weak": payload["n_weak"], "by_reason": payload["by_reason"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
