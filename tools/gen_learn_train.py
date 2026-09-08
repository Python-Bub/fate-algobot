#!/usr/bin/env python3
"""Walk-forward next-gen combiner on historical daily bars.

Fits analytics.gen_learn (ridge on proven votes + residual momentum).
Does NOT overwrite proven_online Hedge weights (hist-cook owns those).

  ./venv/bin/python tools/gen_learn_train.py --once
  ./run_all.sh gen-learn-train
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
    _scale = ROOT / "data" / "deploy_scale.env"
    if _scale.is_file():
        load_dotenv(_scale, override=True)
except Exception:
    pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--max-symbols", type=int, default=int(os.getenv("GEN_LEARN_MAX_SYMBOLS", "48")))
    ap.add_argument("--years", type=int, default=int(os.getenv("GEN_LEARN_YEARS", "8")))
    ap.add_argument("--stride", type=int, default=int(os.getenv("GEN_LEARN_STRIDE", "5")))
    args = ap.parse_args()

    from analytics.gen_learn import fit_and_deploy
    from analytics.proven_online import default_state
    from tools.hist_cook import _COOK_UNIVERSE, _closes, cook_symbol

    end = date.today()
    start = end - timedelta(days=max(365 * max(2, args.years), 800))
    start_s, end_s = start.isoformat(), end.isoformat()
    syms = list(_COOK_UNIVERSE)[: max(1, int(args.max_symbols))]
    print(
        f"[GEN_LEARN] names={len(syms)} window={start_s}..{end_s} stride={args.stride}",
        flush=True,
    )
    spy_df = _closes("SPY", start_s, end_s)
    spy = None
    if spy_df is not None and not spy_df.empty:
        col = "Adj Close" if "Adj Close" in spy_df.columns else "Close"
        spy = spy_df[col].astype(float)
    st = default_state()
    xs: list = []
    ys: list[float] = []
    used = 0
    for i, sym in enumerate(syms, 1):
        try:
            df = _closes(sym, start_s, end_s)
            if df is None or getattr(df, "empty", True):
                continue
            rec = cook_symbol(sym, df, spy, stride=max(1, int(args.stride)), st=st)
            if rec.get("st"):
                st = rec["st"]
            xs.extend(rec.get("X") or [])
            ys.extend(rec.get("y") or [])
            used += 1
            if i % 8 == 0:
                print(f"[GEN_LEARN] {i}/{len(syms)} {sym} n={len(ys)}", flush=True)
        except Exception as e:
            print(f"[GEN_LEARN] skip {sym}: {e}", flush=True)
    if len(ys) < 400:
        print(f"[GEN_LEARN] too few samples n={len(ys)} names={used}", flush=True)
        return 0
    X = np.stack(xs)
    y = np.asarray(ys, dtype=np.float64)
    out = fit_and_deploy(X, y)
    print(
        f"[GEN_LEARN] done names={used} n={out.get('n')} oos={out.get('n_oos')} "
        f"ic={out.get('ic')} acc={out.get('acc')} skill={out.get('skill')}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
