#!/usr/bin/env python3
"""Generate comprehensive ticker->industry database from handler hints + heuristics."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "data" / "industry" / "ticker_database.json"


def main() -> int:
    from analytics.industries.handlers import ALL_HANDLERS
    from analytics.industries.classifier import iter_universe_symbols, load_overrides

    db: dict[str, dict] = {}
    overrides = load_overrides()

    for iid, handler in ALL_HANDLERS.items():
        for sym in handler.TICKER_HINTS:
            db[sym.upper()] = {
                "industry_id": iid,
                "confidence": 0.94,
                "source": "handler_hint",
            }
        for sym in handler.LEADER_TICKERS:
            s = sym.upper()
            if s not in db:
                db[s] = {"industry_id": iid, "confidence": 0.92, "source": "leader"}

    for sym, iid in overrides.items():
        db[sym.upper()] = {"industry_id": iid, "confidence": 0.99, "source": "override"}

    # Weak symbol heuristics (suffix only — avoid false positives)
    try:
        from analytics.industries.name_lexicon import suffix_industry
    except Exception:
        suffix_industry = None  # type: ignore[assignment]

    for sym in iter_universe_symbols():
        if sym in db:
            continue
        if suffix_industry:
            hit = suffix_industry(sym)
            if hit:
                db[sym] = {"industry_id": hit, "confidence": 0.42, "source": "symbol_suffix"}
                continue
        if sym.endswith("BIO") or sym.endswith("PHM"):
            db[sym] = {"industry_id": "biotech", "confidence": 0.4, "source": "symbol_heuristic"}

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps({"version": 1, "symbol_count": len(db), "symbols": db}, indent=0),
        encoding="utf-8",
    )
    print(f"[ticker-db] wrote {len(db)} entries -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
