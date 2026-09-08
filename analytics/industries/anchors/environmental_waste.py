"""
Environmental & Waste industry anchor — Pricing escalators pass diesel inflation.

Primary anchor: WM
Smoke tickers: WM, RSG, WCN, CWST, CLH
ETF proxy: XLI
"""

from __future__ import annotations

from typing import Any

from analytics.industries.anchors._base import IndustryAnchor


class EnvironmentalWasteAnchor(IndustryAnchor):
    INDUSTRY_ID = 'environmental_waste'
    INDUSTRY_NAME = 'Environmental & Waste'
    ETF_PROXY = 'XLI'
    ANCHOR_TICKER = 'WM'
    SMOKE_TICKERS = (
        'WM',
        'RSG',
        'WCN',
        'CWST',
        'CLH'
    )
    HISTORICAL_START = "2023-06-01"
    HISTORICAL_END = "2024-06-30"
    COMOVEMENT_MODE = 'defensive'
    RATE_SENSITIVITY = 0.0
    EXPANSION_BETA = 0.3

    NEWS_BULL_PHRASES = (
        'pricing escalator',
        'volume tonnage',
        'municipal contract',
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
        if "pricing escalator" in text:
            self._boost_row(out, 0.04 + 0 * 0.005, "anchor_bull:pricing escalator")
        if "volume tonnage" in text:
            self._boost_row(out, 0.04 + 1 * 0.005, "anchor_bull:volume tonnage")
        if "municipal contract" in text:
            self._boost_row(out, 0.04 + 2 * 0.005, "anchor_bull:municipal contract")
        if out.get("industry_pipeline", {}).get("score_delta", 0) > 0.05:
            self._boost_row(out, 0.01, "pipeline_tailwind")
        return out

    def enhance_score(self, symbol, score, p_up, *, row=None):
        s, p = super().enhance_score(symbol, score, p_up, row=row)
        if row and float(row.get("industry_z_20") or row.get("industry_sympathy_score") or 0) > 0.3:
            s += 0.006
        return s, p


ANCHOR = EnvironmentalWasteAnchor()
