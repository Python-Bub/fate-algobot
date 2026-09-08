"""
Healthcare Providers industry anchor — Bed occupancy; payer mix; CMS reimbursement updates.

Primary anchor: UNH
Smoke tickers: UNH, ELV, CI, HUM, CVS, HCA
ETF proxy: XLV
"""

from __future__ import annotations

from typing import Any

from analytics.industries.anchors._base import IndustryAnchor


class HealthcareProvidersAnchor(IndustryAnchor):
    INDUSTRY_ID = 'healthcare_providers'
    INDUSTRY_NAME = 'Healthcare Providers'
    ETF_PROXY = 'XLV'
    ANCHOR_TICKER = 'UNH'
    SMOKE_TICKERS = (
        'UNH',
        'ELV',
        'CI',
        'HUM',
        'CVS',
        'HCA'
    )
    HISTORICAL_START = "2023-06-01"
    HISTORICAL_END = "2024-06-30"
    COMOVEMENT_MODE = 'defensive'
    RATE_SENSITIVITY = -0.2
    EXPANSION_BETA = 0.2

    NEWS_BULL_PHRASES = (
        'membership growth',
        'medical loss ratio beat',
        'rate increase',
        'utilization stable',
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
        if "membership growth" in text:
            self._boost_row(out, 0.04 + 0 * 0.005, "anchor_bull:membership growth")
        if "medical loss ratio beat" in text:
            self._boost_row(out, 0.04 + 1 * 0.005, "anchor_bull:medical loss ratio b")
        if "rate increase" in text:
            self._boost_row(out, 0.04 + 2 * 0.005, "anchor_bull:rate increase")
        if "utilization stable" in text:
            self._boost_row(out, 0.04 + 3 * 0.005, "anchor_bull:utilization stable")
        if out.get("industry_pipeline", {}).get("score_delta", 0) > 0.05:
            self._boost_row(out, 0.01, "pipeline_tailwind")
        return out

    def enhance_score(self, symbol, score, p_up, *, row=None):
        s, p = super().enhance_score(symbol, score, p_up, row=row)
        if row and float(row.get("industry_z_20") or row.get("industry_sympathy_score") or 0) > 0.3:
            s += 0.006
        return s, p


ANCHOR = HealthcareProvidersAnchor()
