#!/usr/bin/env python3
"""Generate 50 industry anchor modules (one per classification bucket)."""

from __future__ import annotations

from pathlib import Path

from analytics.industries._generate_industry_handlers import MASTER

ROOT = Path(__file__).resolve().parents[2]
ANCHOR_DIR = ROOT / "analytics" / "industries" / "anchors"


def _cls(iid: str) -> str:
    return "".join(p.capitalize() for p in iid.split("_")) + "Anchor"


def _anchor_source(spec: dict) -> str:
    iid = spec["id"]
    cls = _cls(iid)
    leaders = spec["leaders"]
    anchor = leaders[0]
    smoke = leaders[: min(6, len(leaders))]
    smoke_repr = ",\n        ".join(repr(x) for x in smoke)
    bull = spec["bull"][:5]
    notes = spec["notes"].replace('"', "'")

    bull_methods = []
    for i, phrase in enumerate(bull[:4]):
        bull_methods.append(
            f'        if "{phrase}" in text:\n'
            f'            self._boost_row(out, 0.04 + {i} * 0.005, "anchor_bull:{phrase[:20]}")'
        )
    bull_block = "\n".join(bull_methods) if bull_methods else "        pass"

    return (
        f'"""\n'
        f'{spec["name"]} industry anchor — {notes}\n\n'
        f"Primary anchor: {anchor}\n"
        f"Smoke tickers: {', '.join(smoke)}\n"
        f"ETF proxy: {spec['etf']}\n"
        f'"""\n\n'
        f"from __future__ import annotations\n\n"
        f"from typing import Any\n\n"
        f"from analytics.industries.anchors._base import IndustryAnchor\n\n\n"
        f"class {cls}(IndustryAnchor):\n"
        f"    INDUSTRY_ID = {iid!r}\n"
        f"    INDUSTRY_NAME = {spec['name']!r}\n"
        f"    ETF_PROXY = {spec['etf']!r}\n"
        f"    ANCHOR_TICKER = {anchor!r}\n"
        f"    SMOKE_TICKERS = (\n        {smoke_repr}\n    )\n"
        f"    HISTORICAL_START = \"2023-06-01\"\n"
        f"    HISTORICAL_END = \"2024-06-30\"\n"
        f"    COMOVEMENT_MODE = {spec['mode']!r}\n"
        f"    RATE_SENSITIVITY = {spec['rate']}\n"
        f"    EXPANSION_BETA = {spec['exp']}\n\n"
        f"    NEWS_BULL_PHRASES = (\n"
        + "".join(f"        {p!r},\n" for p in bull)
        + f"    )\n\n"
        f"    def _boost_row(self, row: dict[str, Any], amount: float, note: str) -> None:\n"
        f"        row[\"score\"] = float(row.get(\"score\") or 0.0) + amount\n"
        f"        notes = list(row.get(\"anchor_notes\") or [])\n"
        f"        notes.append(note)\n"
        f"        row[\"anchor_notes\"] = notes[:8]\n\n"
        f"    def enhance_row(self, row: dict[str, Any]) -> dict[str, Any]:\n"
        f"        out = super().enhance_row(row)\n"
        f"        text = \" \".join(\n"
        f"            str(x) for x in (\n"
        f"                (out.get(\"news_ai\") or {{}}).get(\"top_bullish\") or []\n"
        f"            )\n"
        f"        ).lower()\n"
        f"{bull_block}\n"
        f"        if out.get(\"industry_pipeline\", {{}}).get(\"score_delta\", 0) > 0.05:\n"
        f"            self._boost_row(out, 0.01, \"pipeline_tailwind\")\n"
        f"        return out\n\n"
        f"    def enhance_score(self, symbol, score, p_up, *, row=None):\n"
        f"        s, p = super().enhance_score(symbol, score, p_up, row=row)\n"
        f"        if row and float(row.get(\"industry_z_20\") or row.get(\"industry_sympathy_score\") or 0) > 0.3:\n"
        f"            s += 0.006\n"
        f"        return s, p\n\n\n"
        f"ANCHOR = {cls}()\n"
    )


def generate_all() -> int:
    ANCHOR_DIR.mkdir(parents=True, exist_ok=True)
    init_lines = ['"""Auto-generated industry anchor registry (50 buckets)."""\n']
    count = 0
    for spec in MASTER:
        iid = spec["id"]
        (ANCHOR_DIR / f"{iid}.py").write_text(_anchor_source(spec), encoding="utf-8")
        init_lines.append(f"from analytics.industries.anchors.{iid} import ANCHOR as _a_{iid}")
        count += 1
    init_lines.append("\nfrom analytics.industries.anchors._unclassified import ANCHOR as _a_unclassified\n")
    init_lines.append("\nALL_ANCHORS = {")
    for spec in MASTER:
        init_lines.append(f'    "{spec["id"]}": _a_{spec["id"]},')
    init_lines.append('    "unclassified": _a_unclassified,')
    init_lines.append("}\n")
    init_lines.append(
        "\ndef get_anchor(industry_id: str):\n"
        '    return ALL_ANCHORS.get(str(industry_id or "unclassified"), _a_unclassified)\n'
        "\n\n"
        "def anchor_for_symbol(symbol: str):\n"
        '    from analytics.industries.integration import get_industry_profile\n'
        "    prof = get_industry_profile(symbol.strip().upper())\n"
        '    return get_anchor(prof.get("primary_industry_id") or "unclassified")\n'
    )
    (ANCHOR_DIR / "__init__.py").write_text("\n".join(init_lines), encoding="utf-8")
    return count


if __name__ == "__main__":
    n = generate_all()
    print(f"Generated {n} industry anchor modules in {ANCHOR_DIR}")
