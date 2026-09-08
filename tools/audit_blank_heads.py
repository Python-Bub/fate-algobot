#!/usr/bin/env python3
"""Audit null horizon/meta heads inside saved daily pickles (presence ≠ completeness)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

HEADS = ("model_short", "model_long", "model_daily", "model_xlong", "model_meta")


def _audit_one(path: Path) -> dict:
    try:
        import joblib

        b = joblib.load(path)
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"[:160]}
    if not isinstance(b, dict):
        return {"ok": False, "error": "not_a_dict"}
    nulls = [k for k in HEADS if b.get(k) is None]
    return {"ok": True, "nulls": nulls, "complete": not nulls}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", choices=["top100", "all"], default="top100")
    ap.add_argument("--write", type=str, default="")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    from fortress_universe import load_top100_symbols
    from model_trainer import training_saved_model

    if args.scope == "top100":
        syms = load_top100_symbols()
    else:
        syms = sorted(
            p.name[: -len("_model.pkl")].upper()
            for p in (ROOT / "models").glob("*_model.pkl")
            if p.stat().st_size > 1000
        )
    if args.limit > 0:
        syms = syms[: args.limit]

    missing_file: list[str] = []
    corrupt: list[str] = []
    blank: dict[str, list[str]] = {}
    complete = 0
    for s in syms:
        if not training_saved_model(s):
            missing_file.append(s)
            continue
        r = _audit_one(ROOT / "models" / f"{s}_model.pkl")
        if not r.get("ok"):
            corrupt.append(s)
            continue
        if r["complete"]:
            complete += 1
        else:
            blank[s] = list(r["nulls"])

    out = {
        "scope": args.scope,
        "scanned": len(syms),
        "complete": complete,
        "missing_file": missing_file,
        "corrupt": corrupt,
        "blank": blank,
        "n_blank": len(blank),
    }
    print(
        f"[blank-heads] scope={args.scope} scanned={len(syms)} complete={complete} "
        f"blank={len(blank)} missing_file={len(missing_file)} corrupt={len(corrupt)}"
    )
    if blank:
        sample = list(blank.items())[:12]
        for s, n in sample:
            print(f"  {s}: {','.join(n)}")
    if args.write:
        Path(args.write).write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
        print(f"[blank-heads] wrote {args.write}")
    return 0 if not blank and not missing_file and not corrupt else 1


if __name__ == "__main__":
    raise SystemExit(main())
