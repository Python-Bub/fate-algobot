"""
Commercial Office REITs industry anchor — WAULT; transit ridership; CRE lending standards.

Primary anchor: BXP
Smoke tickers: BXP, VNO, SLG, KRC, DEI, OFC
ETF proxy: VNQ
"""

from __future__ import annotations

from typing import Any

from analytics.industries.anchors._base import IndustryAnchor


class CommercialOfficeReitsAnchor(IndustryAnchor):
    INDUSTRY_ID = 'commercial_office_reits'
    INDUSTRY_NAME = 'Commercial Office REITs'
    ETF_PROXY = 'VNQ'
    ANCHOR_TICKER = 'BXP'
    SMOKE_TICKERS = (
        'BXP',
        'VNO',
        'SLG',
        'KRC',
        'DEI',
        'OFC'
    )
    HISTORICAL_START = "2023-06-01"
    HISTORICAL_END = "2024-06-30"
    COMOVEMENT_MODE = 'inverse_rates'
    RATE_SENSITIVITY = -0.65
    EXPANSION_BETA = 0.5

    NEWS_BULL_PHRASES = (
        'return to office',
        'lease signed',
        'occupancy stabil',
        'wault extended',
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
        if "return to office" in text:
            self._boost_row(out, 0.04 + 0 * 0.005, "anchor_bull:return to office")
        if "lease signed" in text:
            self._boost_row(out, 0.04 + 1 * 0.005, "anchor_bull:lease signed")
        if "occupancy stabil" in text:
            self._boost_row(out, 0.04 + 2 * 0.005, "anchor_bull:occupancy stabil")
        if "wault extended" in text:
            self._boost_row(out, 0.04 + 3 * 0.005, "anchor_bull:wault extended")
        if out.get("industry_pipeline", {}).get("score_delta", 0) > 0.05:
            self._boost_row(out, 0.01, "pipeline_tailwind")
        return out

    def enhance_score(self, symbol, score, p_up, *, row=None):
        s, p = super().enhance_score(symbol, score, p_up, row=row)
        if row and float(row.get("industry_z_20") or row.get("industry_sympathy_score") or 0) > 0.3:
            s += 0.006
        return s, p


ANCHOR = CommercialOfficeReitsAnchor()
