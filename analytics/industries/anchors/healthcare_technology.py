"""
Healthcare Technology industry anchor — LTV/CAC; privacy regulation hits entire group.

Primary anchor: VEEV
Smoke tickers: VEEV, TDOC, HIMS, DOCS, CERN, MDRX
ETF proxy: XLV
"""

from __future__ import annotations

from typing import Any

from analytics.industries.anchors._base import IndustryAnchor


class HealthcareTechnologyAnchor(IndustryAnchor):
    INDUSTRY_ID = 'healthcare_technology'
    INDUSTRY_NAME = 'Healthcare Technology'
    ETF_PROXY = 'XLV'
    ANCHOR_TICKER = 'VEEV'
    SMOKE_TICKERS = (
        'VEEV',
        'TDOC',
        'HIMS',
        'DOCS',
        'CERN',
        'MDRX'
    )
    HISTORICAL_START = "2023-06-01"
    HISTORICAL_END = "2024-06-30"
    COMOVEMENT_MODE = 'follow_nasdaq'
    RATE_SENSITIVITY = 0.2
    EXPANSION_BETA = 0.9

    NEWS_BULL_PHRASES = (
        'contract win',
        'hospital go-live',
        'saas growth',
        'ARR beat',
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
        if "contract win" in text:
            self._boost_row(out, 0.04 + 0 * 0.005, "anchor_bull:contract win")
        if "hospital go-live" in text:
            self._boost_row(out, 0.04 + 1 * 0.005, "anchor_bull:hospital go-live")
        if "saas growth" in text:
            self._boost_row(out, 0.04 + 2 * 0.005, "anchor_bull:saas growth")
        if "ARR beat" in text:
            self._boost_row(out, 0.04 + 3 * 0.005, "anchor_bull:ARR beat")
        if out.get("industry_pipeline", {}).get("score_delta", 0) > 0.05:
            self._boost_row(out, 0.01, "pipeline_tailwind")
        return out

    def enhance_score(self, symbol, score, p_up, *, row=None):
        s, p = super().enhance_score(symbol, score, p_up, row=row)
        if row and float(row.get("industry_z_20") or row.get("industry_sympathy_score") or 0) > 0.3:
            s += 0.006
        return s, p


ANCHOR = HealthcareTechnologyAnchor()
