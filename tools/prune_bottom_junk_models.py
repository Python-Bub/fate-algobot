#!/usr/bin/env python3
"""Remove daily model files for bottom-universe junk that should not keep bundles on disk."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CK = ROOT / "data/train_checkpoint.json"


def _protected_symbols() -> set[str]:
    protected: set[str] = set()
    sys.path.insert(0, str(ROOT))
    from bottom_fisher.store import load_scan

    scan = load_scan()
    for p in scan.get("picks") or []:
        if p.get("trade_eligible", True):
            protected.add(str(p["ticker"]).upper())
    try:
        from fortress_universe import load_top100_symbols, load_top50pct_symbols, symbols_paper_active_universe

        protected.update(load_top100_symbols())
        protected.update(load_top50pct_symbols())
        protected.update(symbols_paper_active_universe())
    except Exception:
        pass
    q = ROOT / "data/new_listing_train_queue.json"
    if q.is_file():
        try:
            doc = json.loads(q.read_text(encoding="utf-8"))
            protected.update(str(s).upper() for s in doc.get("symbols", []) if s)
        except Exception:
            pass
    wl = ROOT / "data/ipo_watchlist.txt"
    if wl.is_file():
        for ln in wl.read_text(encoding="utf-8", errors="replace").splitlines():
            t = ln.strip().upper().split("#", 1)[0].strip()
            if t and len(t) <= 6 and t.isalnum():
                protected.add(t)
    extra = os.getenv("IPO_WATCH_TICKERS", "")
    protected.update(s.strip().upper() for s in extra.split(",") if s.strip())
    return protected


def _bottom_half_symbols() -> set[str]:
    from bottom_fisher.config import BottomFisherConfig
    from bottom_fisher.universe import load_bottom_universe

    cfg = BottomFisherConfig.from_env()
    # Full bottom slice before max_scan cap — who is in worst 50%.
    cfg_full = BottomFisherConfig(**{**cfg.__dict__, "max_scan_symbols": 50_000})
    return {c.ticker.upper() for c in load_bottom_universe(cfg_full)}


def _artifact_paths(sym: str) -> list[Path]:
    model_dir = Path(os.getenv("MODEL_DIR", "models"))
    paths = [
        model_dir / f"{sym}_model.pkl",
        model_dir / "meta" / f"{sym}_meta.pkl",
        model_dir / "lstm" / f"{sym}_lstm.pt",
        model_dir / "intraday" / f"{sym}_intraday.pkl",
    ]
    return [p for p in paths if p.is_file()]


def main() -> int:
    ap = argparse.ArgumentParser(description="Prune model files for bottom-half junk names")
    ap.add_argument("--run", action="store_true", help="Actually delete files (default dry-run)")
    ap.add_argument("--also-non-core", action="store_true", default=True, help="Drop non-core trainable tickers")
    args = ap.parse_args()
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))

    from fortress_universe import is_core_trainable_equity
    from model_trainer import training_saved_model

    protected = _protected_symbols()
    bottom = _bottom_half_symbols()
    model_dir = Path(os.getenv("MODEL_DIR", "models"))
    candidates: list[str] = []

    for p in model_dir.glob("*_model.pkl"):
        sym = p.name[: -len("_model.pkl")].upper()
        if sym in protected:
            continue
        if args.also_non_core and not is_core_trainable_equity(sym):
            candidates.append(sym)
            continue
        if sym in bottom:
            candidates.append(sym)

    candidates = sorted(set(candidates))
    freed = 0
    removed: list[str] = []
    for sym in candidates:
        paths = _artifact_paths(sym)
        if not paths:
            continue
        nbytes = sum(x.stat().st_size for x in paths)
        if args.run:
            for path in paths:
                path.unlink(missing_ok=True)
            removed.append(sym)
            freed += nbytes
        else:
            removed.append(sym)
            freed += nbytes

    if args.run and removed and CK.is_file():
        try:
            data = json.loads(CK.read_text(encoding="utf-8"))
            sym_set = set(removed)
            data["done"] = sorted(set(data.get("done", [])) - sym_set)
            failed = dict(data.get("failed", {}))
            for s in sym_set:
                failed.pop(s, None)
            data["failed"] = failed
            CK.write_text(json.dumps(data, indent=0), encoding="utf-8")
        except Exception:
            pass

    mode = "DELETED" if args.run else "would delete"
    print(f"[prune-bottom-junk] {mode} {len(removed)} symbols (~{freed / 1e6:.1f} MB)")
    for s in removed[:40]:
        print(f"  {s}")
    if len(removed) > 40:
        print(f"  ... +{len(removed) - 40} more")
    if not args.run and removed:
        print("  pass --run to apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
