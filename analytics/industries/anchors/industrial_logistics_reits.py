"""
Industrial & Logistics REITs industry anchor — Rent reversion; e-commerce % of retail.

Primary anchor: PLD
Smoke tickers: PLD, EXR, PSA, REXR, FR, STAG
ETF proxy: IYR
"""

from __future__ import annotations

from typing import Any

from analytics.industries.anchors._base import IndustryAnchor


class IndustrialLogisticsReitsAnchor(IndustryAnchor):
    INDUSTRY_ID = 'industrial_logistics_reits'
    INDUSTRY_NAME = 'Industrial & Logistics REITs'
    ETF_PROXY = 'IYR'
    ANCHOR_TICKER = 'PLD'
    SMOKE_TICKERS = (
        'PLD',
        'EXR',
        'PSA',
        'REXR',
        'FR',
        'STAG'
    )
    HISTORICAL_START = "2023-06-01"
    HISTORICAL_END = "2024-06-30"
    COMOVEMENT_MODE = 'hybrid'
    RATE_SENSITIVITY = -0.55
    EXPANSION_BETA = 0.7

    NEWS_BULL_PHRASES = (
        'rent reversion',
        'e-commerce demand',
        'supply chain',
        'development yield',
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
        if "rent reversion" in text:
            self._boost_row(out, 0.04 + 0 * 0.005, "anchor_bull:rent reversion")
        if "e-commerce demand" in text:
            self._boost_row(out, 0.04 + 1 * 0.005, "anchor_bull:e-commerce demand")
        if "supply chain" in text:
            self._boost_row(out, 0.04 + 2 * 0.005, "anchor_bull:supply chain")
        if "development yield" in text:
            self._boost_row(out, 0.04 + 3 * 0.005, "anchor_bull:development yield")
        if out.get("industry_pipeline", {}).get("score_delta", 0) > 0.05:
            self._boost_row(out, 0.01, "pipeline_tailwind")
        return out

    def enhance_score(self, symbol, score, p_up, *, row=None):
        s, p = super().enhance_score(symbol, score, p_up, row=row)
        if row and float(row.get("industry_z_20") or row.get("industry_sympathy_score") or 0) > 0.3:
            s += 0.006
        return s, p


ANCHOR = IndustrialLogisticsReitsAnchor()
