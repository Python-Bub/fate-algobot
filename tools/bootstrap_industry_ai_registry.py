#!/usr/bin/env python3
"""Seed ai_classifications.json from rule map + manual overrides (no LLM required)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load_overrides() -> dict[str, str]:
    p = ROOT / "data" / "industry" / "symbol_overrides.json"
    if not p.is_file():
        return {}
    doc = json.loads(p.read_text(encoding="utf-8"))
    raw = doc.get("symbols") or doc
    return {str(k).upper(): str(v).lower() for k, v in raw.items() if k and v}


def bootstrap(*, tier: str = "all", min_confidence: float = 0.55) -> dict:
    from analytics.industries.ai_registry import emit_ai_override_module, upsert_ai_classification
    from analytics.industry_taxonomy import load_industry_map, load_catalog

    catalog = load_catalog()
    imap = load_industry_map()
    overrides = _load_overrides()

    if tier == "top100":
        from fortress_universe import load_top100_symbols

        universe = set(load_top100_symbols())
    elif tier == "top50":
        from fortress_universe import load_top50pct_symbols

        universe = set(load_top50pct_symbols())
    else:
        universe = set(imap.keys()) | set(overrides.keys())

    seeded = 0
    skipped = 0
    for sym in sorted(universe):
        iid = overrides.get(sym)
        conf = 0.92
        source = "manual_override"
        if not iid:
            row = imap.get(sym) or {}
            iid = str(row.get("industry_id") or "").lower()
            conf = float(row.get("confidence") or 0.0)
            source = "rule_map_bootstrap"
            if not iid or iid == "unclassified" or conf < min_confidence:
                skipped += 1
                continue
            conf = min(0.88, max(0.62, conf + 0.15))

        if iid not in catalog:
            skipped += 1
            continue

        upsert_ai_classification(
            sym,
            industries=[{"industry_id": iid, "weight": 1.0, "role": "primary", "rationale": source}],
            source=source,
            confidence=conf,
            persist=True,
        )
        seeded += 1

    emit_ai_override_module()
    return {
        "tier": tier,
        "universe": len(universe),
        "seeded": seeded,
        "skipped": skipped,
        "registry_path": str(ROOT / "data" / "industry" / "ai_classifications.json"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Bootstrap AI industry registry from rule map")
    ap.add_argument("--tier", default="all", choices=("all", "top100", "top50"))
    ap.add_argument("--min-confidence", type=float, default=0.55)
    args = ap.parse_args()
    rep = bootstrap(tier=args.tier, min_confidence=args.min_confidence)
    print(json.dumps(rep, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
