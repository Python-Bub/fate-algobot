#!/usr/bin/env python3
"""Emit analytics/industries/peer_ticker_map.py from industry_map.json for O(1) lookups."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "data" / "industry" / "industry_map.json"
OUT = ROOT / "analytics" / "industries" / "peer_ticker_map.py"


def main() -> int:
    doc = json.loads(MAP.read_text(encoding="utf-8"))
    symbols = doc.get("symbols") or {}
    lines = [
        '"""Auto-generated ticker -> industry map (%d symbols). Do not edit by hand."""',
        "",
        "from __future__ import annotations",
        "",
        "TICKER_INDUSTRY: dict[str, str] = {",
    ]
    for sym in sorted(symbols.keys()):
        iid = str(symbols[sym].get("industry_id") or "unclassified")
        lines.append(f'    "{sym}": "{iid}",')
    lines.append("}")
    lines.append("")
    lines.append("TICKER_META: dict[str, dict] = {")
    for sym in sorted(symbols.keys()):
        row = symbols[sym]
        meta = {
            "industry_id": row.get("industry_id"),
            "etf_proxy": row.get("etf_proxy"),
            "comovement_mode": row.get("comovement_mode"),
            "confidence": row.get("confidence"),
        }
        lines.append(f'    "{sym}": {meta!r},')
    lines.append("}")
    lines.append("")
    lines.append("")
    lines.append("def lookup(symbol: str) -> str:")
    lines.append('    return TICKER_INDUSTRY.get(symbol.strip().upper(), "unclassified")')
    lines.append("")
    OUT.write_text("\n".join(lines) % len(symbols), encoding="utf-8")
    print(f"[peer-map] wrote {OUT} ({len(symbols)} symbols, {len(lines)} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
