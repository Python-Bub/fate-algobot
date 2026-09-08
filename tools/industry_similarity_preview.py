#!/usr/bin/env python3
"""Preview soft industry similarity blend for a symbol."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser(description="Preview industry similarity blend")
    ap.add_argument("symbol", nargs="?", default="AMZN")
    ap.add_argument("--headlines", nargs="*", default=[])
    args = ap.parse_args()

    from analytics.industries.integration import get_industry_profile
    from analytics.industries.similarity_engine import nearest_categories

    sym = args.symbol.strip().upper()
    prof = get_industry_profile(sym, news_headlines=args.headlines or None)
    near = nearest_categories(sym, {"industry_id": prof.get("primary_industry_id"), "confidence": prof.get("confidence")}, top_k=6)

    out = {
        "symbol": sym,
        "primary": prof.get("primary_industry_id"),
        "blend_weights": prof.get("blend_weights"),
        "industries": prof.get("industries"),
        "similarity_neighbors": prof.get("similarity_neighbors"),
        "nearest_raw": [{"industry_id": i, "score": round(s, 4)} for i, s in near],
    }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
