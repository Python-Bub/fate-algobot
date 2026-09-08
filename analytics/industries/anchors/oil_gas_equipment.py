"""
Oil & Gas Equipment industry anchor — Lags crude 3-6 months.

Primary anchor: SLB
Smoke tickers: SLB, HAL, BKR, NOV, CHX, FTI
ETF proxy: XES
"""

from __future__ import annotations

from typing import Any

from analytics.industries.anchors._base import IndustryAnchor


class OilGasEquipmentAnchor(IndustryAnchor):
    INDUSTRY_ID = 'oil_gas_equipment'
    INDUSTRY_NAME = 'Oil & Gas Equipment'
    ETF_PROXY = 'XES'
    ANCHOR_TICKER = 'SLB'
    SMOKE_TICKERS = (
        'SLB',
        'HAL',
        'BKR',
        'NOV',
        'CHX',
        'FTI'
    )
    HISTORICAL_START = "2023-06-01"
    HISTORICAL_END = "2024-06-30"
    COMOVEMENT_MODE = 'commodity'
    RATE_SENSITIVITY = 0.0
    EXPANSION_BETA = 0.8

    NEWS_BULL_PHRASES = (
        'rig count',
        'international capex',
        'dayrate',
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
        if "rig count" in text:
            self._boost_row(out, 0.04 + 0 * 0.005, "anchor_bull:rig count")
        if "international capex" in text:
            self._boost_row(out, 0.04 + 1 * 0.005, "anchor_bull:international capex")
        if "dayrate" in text:
            self._boost_row(out, 0.04 + 2 * 0.005, "anchor_bull:dayrate")
        if out.get("industry_pipeline", {}).get("score_delta", 0) > 0.05:
            self._boost_row(out, 0.01, "pipeline_tailwind")
        return out

    def enhance_score(self, symbol, score, p_up, *, row=None):
        s, p = super().enhance_score(symbol, score, p_up, row=row)
        if row and float(row.get("industry_z_20") or row.get("industry_sympathy_score") or 0) > 0.3:
            s += 0.006
        return s, p


ANCHOR = OilGasEquipmentAnchor()
