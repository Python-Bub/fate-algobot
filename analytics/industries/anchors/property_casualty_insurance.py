"""
Property & Casualty Insurance industry anchor — Combined ratio; NOAA hurricane season.

Primary anchor: PGR
Smoke tickers: PGR, TRV, ALL, CB, AIG, HIG
ETF proxy: KIE
"""

from __future__ import annotations

from typing import Any

from analytics.industries.anchors._base import IndustryAnchor


class PropertyCasualtyInsuranceAnchor(IndustryAnchor):
    INDUSTRY_ID = 'property_casualty_insurance'
    INDUSTRY_NAME = 'Property & Casualty Insurance'
    ETF_PROXY = 'KIE'
    ANCHOR_TICKER = 'PGR'
    SMOKE_TICKERS = (
        'PGR',
        'TRV',
        'ALL',
        'CB',
        'AIG',
        'HIG'
    )
    HISTORICAL_START = "2023-06-01"
    HISTORICAL_END = "2024-06-30"
    COMOVEMENT_MODE = 'defensive'
    RATE_SENSITIVITY = 0.1
    EXPANSION_BETA = 0.3

    NEWS_BULL_PHRASES = (
        'combined ratio beat',
        'rate increase approved',
        'pricing firm',
    )

    def _boost_row(self, row: dict[str, Any], amount: float, note: str) -> None:
        row["score"] = float(row.get("score") or 0.0) + amount
        notes = list(row.get("anchor_notes") or [])
        notes.append(note)
        row["anchor_notes"] = notes[:8]

    def enhance_row(self, row: dict[str, Any]) -> dict[str, Any]:
        out = super().enhance_row(row)
        text = " ".join(
            str(x) for x in (
                (out.get("news_ai") or {}).get("top_bullish") or []
            )
        ).lower()
        if "combined ratio beat" in text:
            self._boost_row(out, 0.04 + 0 * 0.005, "anchor_bull:combined ratio beat")
        if "rate increase approved" in text:
            self._boost_row(out, 0.04 + 1 * 0.005, "anchor_bull:rate increase approv")
        if "pricing firm" in text:
            self._boost_row(out, 0.04 + 2 * 0.005, "anchor_bull:pricing firm")
        if out.get("industry_pipeline", {}).get("score_delta", 0) > 0.05:
            self._boost_row(out, 0.01, "pipeline_tailwind")
        return out

    def enhance_score(self, symbol, score, p_up, *, row=None):
        s, p = super().enhance_score(symbol, score, p_up, row=row)
        if row and float(row.get("industry_z_20") or row.get("industry_sympathy_score") or 0) > 0.3:
            s += 0.006
        return s, p


ANCHOR = PropertyCasualtyInsuranceAnchor()
