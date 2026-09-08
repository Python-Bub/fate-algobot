#!/usr/bin/env python3
"""Deep blank / gap hunter — top100 + paper universe + promoted symbols.

Fills null heads and missing pickles without deleting anything.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def collect_symbols() -> list[str]:
    syms: set[str] = set()
    try:
        from fortress_universe import load_top100_symbols, load_top50pct_symbols, symbols_paper_active_universe

        syms |= {s.upper() for s in load_top100_symbols()}
        syms |= {s.upper() for s in load_top50pct_symbols()[:200]}
        syms |= {s.upper() for s in symbols_paper_active_universe()}
    except Exception:
        pass
    for extra in (
        ROOT / "data" / "bottom_fisher_eligible.json",
        ROOT / "data" / "new_listing_train_queue.json",
        ROOT / "data" / "tier2_retrain_queue.json",
    ):
        if not extra.is_file():
            continue
        try:
            doc = json.loads(extra.read_text(encoding="utf-8"))
            if isinstance(doc, list):
                syms |= {str(x).upper() for x in doc if x}
            elif isinstance(doc, dict):
                for k in ("symbols", "tickers", "queue"):
                    if isinstance(doc.get(k), list):
                        syms |= {str(x).upper() for x in doc[k] if x}
        except Exception:
            pass
    return sorted(syms)


def audit(symbols: list[str]) -> dict:
    import joblib

    missing_file = []
    corrupt = []
    blank: dict[str, list[str]] = {}
    complete = 0
    for s in symbols:
        p = ROOT / "models" / f"{s}_model.pkl"
        if not p.is_file():
            missing_file.append(s)
            continue
        try:
            b = joblib.load(p)
        except Exception:
            corrupt.append(s)
            continue
        nulls = [
            k
            for k in ("model_short", "model_long", "model_daily", "model_xlong", "model_meta")
            if b.get(k) is None
        ]
        if nulls:
            blank[s] = nulls
        else:
            complete += 1
    return {
        "scanned": len(symbols),
        "complete": complete,
        "missing_file": missing_file,
        "corrupt": corrupt,
        "blank": blank,
        "n_blank": len(blank),
    }


def main() -> int:
    os.environ.setdefault("FILL_NULL_HEADS", "true")
    os.environ.setdefault("KEEP_WEAK_HEADS", "true")
    os.environ.setdefault("COALESCE_EXISTING_HEADS", "true")
    os.environ.setdefault("AUTO_IMPROVE_NEVER_DELETE", "true")

    symbols = collect_symbols()
    rep = audit(symbols)
    out = ROOT / "data" / "deep_blank_audit.json"
    out.write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")
    print(
        f"[deep-blank] scanned={rep['scanned']} complete={rep['complete']} "
        f"blank={rep['n_blank']} missing={len(rep['missing_file'])} corrupt={len(rep['corrupt'])}",
        flush=True,
    )

    # Fill null heads inside existing pickles (top100 priority already handled elsewhere)
    need_fill = sorted(rep["blank"].keys())[: int(os.getenv("DEEP_BLANK_FILL_CAP", "40"))]
    if need_fill and os.getenv("DEEP_BLANK_EXECUTE", "true").lower() in ("1", "true", "yes"):
        from tools.retrain_top100_strong import strong_train_ticker
        from tools.retrain_weak_models import weak_heads_from_reasons

        for i, sym in enumerate(need_fill, 1):
            reasons = [f"null:{k.replace('model_', '')}" for k in rep["blank"][sym]]
            heads = weak_heads_from_reasons(reasons) or {"daily", "xlong", "meta"}
            print(f"[deep-blank] ({i}/{len(need_fill)}) {sym} {sorted(heads)}", flush=True)
            try:
                strong_train_ticker(sym, min_top20=0.28, min_meta=0.38, weak_heads=heads)
            except Exception as e:
                print(f"[deep-blank] {sym} ERROR {e}", flush=True)

    # Missing files — train full stack lean
    missing = rep["missing_file"][: int(os.getenv("DEEP_MISSING_FILL_CAP", "15"))]
    if missing and os.getenv("DEEP_BLANK_EXECUTE", "true").lower() in ("1", "true", "yes"):
        from tools.retrain_top100_strong import strong_train_ticker

        for i, sym in enumerate(missing, 1):
            print(f"[deep-blank] missing ({i}/{len(missing)}) {sym}", flush=True)
            try:
                strong_train_ticker(
                    sym,
                    min_top20=0.28,
                    min_meta=0.38,
                    weak_heads={"short", "long", "daily", "xlong", "meta"},
                )
            except Exception as e:
                print(f"[deep-blank] {sym} ERROR {e}", flush=True)

    rep2 = audit(symbols)
    out.write_text(json.dumps({"before": rep, "after": rep2}, indent=2) + "\n", encoding="utf-8")
    print(
        f"[deep-blank] AFTER complete={rep2['complete']} blank={rep2['n_blank']} "
        f"missing={len(rep2['missing_file'])}",
        flush=True,
    )
    return 0 if rep2["n_blank"] == 0 and not rep2["missing_file"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
