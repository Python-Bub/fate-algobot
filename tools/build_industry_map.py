#!/usr/bin/env python3
"""Classify universe symbols into 50 industries + compute leader lists."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MAP_PATH = ROOT / "data" / "industry" / "industry_map.json"
LEADER_PATH = ROOT / "data" / "cache" / "industry_leaders.json"


def _universe_symbols() -> list[str]:
    syms: list[str] = []
    snap = ROOT / "data" / "universe" / "universe_snapshot.json"
    if snap.is_file():
        try:
            doc = json.loads(snap.read_text(encoding="utf-8"))
            syms.extend(str(s).upper() for s in (doc.get("symbols") or doc.get("tickers") or []))
        except Exception:
            pass
    try:
        from bundled_universe import load_universe

        syms.extend(load_universe())
    except Exception:
        pass
    models = ROOT / "models"
    if models.is_dir():
        for p in models.glob("*_model.pkl"):
            syms.append(p.name.replace("_model.pkl", "").upper())
    return sorted({s for s in syms if s and len(s) <= 6 and s.isalpha()})


def build_map(*, use_yfinance: bool = True, limit: int = 0) -> dict:
    from analytics.industry_taxonomy import classify_symbol, load_catalog, persist_taxonomy

    persist_taxonomy()
    symbols = _universe_symbols()
    if limit > 0:
        symbols = symbols[:limit]

    out: dict[str, dict] = {}
    by_industry: dict[str, list[str]] = {}
    for i, sym in enumerate(symbols, 1):
        meta = classify_symbol(sym, use_yfinance=use_yfinance)
        iid = str(meta.get("industry_id") or "unclassified")
        cap = 0.0
        if use_yfinance:
            try:
                import yfinance as yf

                info = yf.Ticker(sym).info or {}
                cap = float(info.get("marketCap") or 0.0)
            except Exception:
                pass
        row = {
            "industry_id": iid,
            "industry_name": meta.get("name"),
            "etf_proxy": meta.get("etf_proxy"),
            "sector": meta.get("sector"),
            "yahoo_industry": meta.get("yahoo_industry"),
            "market_cap": cap,
            "nasdaq_heavy": bool(meta.get("nasdaq_heavy")),
            "rate_sensitive": bool(meta.get("rate_sensitive")),
        }
        out[sym] = row
        by_industry.setdefault(iid, []).append(sym)
        if i % 50 == 0:
            print(f"[industry-map] classified {i}/{len(symbols)}", flush=True)

    leaders: dict[str, list[str]] = {}
    for iid, peers in by_industry.items():
        ranked = sorted(
            peers,
            key=lambda s: float(out[s].get("market_cap") or 0.0),
            reverse=True,
        )
        leaders[iid] = ranked[:5]

    MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    MAP_PATH.write_text(
        json.dumps({"version": 1, "symbols": out, "industry_count": len(by_industry)}, indent=0),
        encoding="utf-8",
    )
    LEADER_PATH.parent.mkdir(parents=True, exist_ok=True)
    LEADER_PATH.write_text(
        json.dumps({"version": 1, "by_industry": leaders, "updated": len(out)}, indent=0),
        encoding="utf-8",
    )
    return {"symbols": len(out), "industries": len(by_industry), "leaders": leaders}


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Build 50-industry symbol map")
    ap.add_argument("--no-yfinance", action="store_true", help="Use overrides + patterns only")
    ap.add_argument("--limit", type=int, default=0, help="Max symbols (0=all)")
    args = ap.parse_args()
    os.chdir(ROOT)
    stats = build_map(use_yfinance=not args.no_yfinance, limit=args.limit)
    print(
        f"[industry-map] wrote {MAP_PATH} — {stats['symbols']} symbols, "
        f"{stats['industries']} industries",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
