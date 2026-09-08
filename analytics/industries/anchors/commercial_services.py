"""
Commercial Services industry anchor — White-collar employment linkage.

Primary anchor: ADP
Smoke tickers: ADP, PayX, CTAS, UNF, ABM, BCO
ETF proxy: XLI
"""

from __future__ import annotations

from typing import Any

from analytics.industries.anchors._base import IndustryAnchor


class CommercialServicesAnchor(IndustryAnchor):
    INDUSTRY_ID = 'commercial_services'
    INDUSTRY_NAME = 'Commercial Services'
    ETF_PROXY = 'XLI'
    ANCHOR_TICKER = 'ADP'
    SMOKE_TICKERS = (
        'ADP',
        'PayX',
        'CTAS',
        'UNF',
        'ABM',
        'BCO'
    )
    HISTORICAL_START = "2023-06-01"
    HISTORICAL_END = "2024-06-30"
    COMOVEMENT_MODE = 'hybrid'
    RATE_SENSITIVITY = 0.0
    EXPANSION_BETA = 0.5

    NEWS_BULL_PHRASES = (
        'white collar hiring',
        'contract renewal',
        'cross sell',
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
        if "white collar hiring" in text:
            self._boost_row(out, 0.04 + 0 * 0.005, "anchor_bull:white collar hiring")
        if "contract renewal" in text:
            self._boost_row(out, 0.04 + 1 * 0.005, "anchor_bull:contract renewal")
        if "cross sell" in text:
            self._boost_row(out, 0.04 + 2 * 0.005, "anchor_bull:cross sell")
        if out.get("industry_pipeline", {}).get("score_delta", 0) > 0.05:
            self._boost_row(out, 0.01, "pipeline_tailwind")
        return out

    def enhance_score(self, symbol, score, p_up, *, row=None):
        s, p = super().enhance_score(symbol, score, p_up, row=row)
        if row and float(row.get("industry_z_20") or row.get("industry_sympathy_score") or 0) > 0.3:
            s += 0.006
        return s, p


ANCHOR = CommercialServicesAnchor()
