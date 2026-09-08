"""
Semiconductor Equipment industry anchor — Multi-year boom/bust; moves on fab capex headlines.

Primary anchor: ASML
Smoke tickers: ASML, LRCX, AMAT, KLAC, TER, ONTO
ETF proxy: SMH
"""

from __future__ import annotations

from typing import Any

from analytics.industries.anchors._base import IndustryAnchor


class SemiEquipmentAnchor(IndustryAnchor):
    INDUSTRY_ID = 'semi_equipment'
    INDUSTRY_NAME = 'Semiconductor Equipment'
    ETF_PROXY = 'SMH'
    ANCHOR_TICKER = 'ASML'
    SMOKE_TICKERS = (
        'ASML',
        'LRCX',
        'AMAT',
        'KLAC',
        'TER',
        'ONTO'
    )
    HISTORICAL_START = "2023-06-01"
    HISTORICAL_END = "2024-06-30"
    COMOVEMENT_MODE = 'follow_nasdaq'
    RATE_SENSITIVITY = 0.0
    EXPANSION_BETA = 1.3

    NEWS_BULL_PHRASES = (
        'fab build',
        'capex raise',
        'chips act',
        'order backlog',
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
        if "fab build" in text:
            self._boost_row(out, 0.04 + 0 * 0.005, "anchor_bull:fab build")
        if "capex raise" in text:
            self._boost_row(out, 0.04 + 1 * 0.005, "anchor_bull:capex raise")
        if "chips act" in text:
            self._boost_row(out, 0.04 + 2 * 0.005, "anchor_bull:chips act")
        if "order backlog" in text:
            self._boost_row(out, 0.04 + 3 * 0.005, "anchor_bull:order backlog")
        if out.get("industry_pipeline", {}).get("score_delta", 0) > 0.05:
            self._boost_row(out, 0.01, "pipeline_tailwind")
        return out

    def enhance_score(self, symbol, score, p_up, *, row=None):
        s, p = super().enhance_score(symbol, score, p_up, row=row)
        if row and float(row.get("industry_z_20") or row.get("industry_sympathy_score") or 0) > 0.3:
            s += 0.006
        return s, p


ANCHOR = SemiEquipmentAnchor()
