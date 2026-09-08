"""
Life Sciences Tools industry anchor — Backlog growth; VC funding into biotech drives instrument demand.

Primary anchor: TMO
Smoke tickers: TMO, DHR, A, IQV, CRL, WAT
ETF proxy: XLV
"""

from __future__ import annotations

from typing import Any

from analytics.industries.anchors._base import IndustryAnchor


class LifeSciencesToolsAnchor(IndustryAnchor):
    INDUSTRY_ID = 'life_sciences_tools'
    INDUSTRY_NAME = 'Life Sciences Tools'
    ETF_PROXY = 'XLV'
    ANCHOR_TICKER = 'TMO'
    SMOKE_TICKERS = (
        'TMO',
        'DHR',
        'A',
        'IQV',
        'CRL',
        'WAT'
    )
    HISTORICAL_START = "2023-06-01"
    HISTORICAL_END = "2024-06-30"
    COMOVEMENT_MODE = 'follow_nasdaq'
    RATE_SENSITIVITY = 0.1
    EXPANSION_BETA = 0.8

    NEWS_BULL_PHRASES = (
        'backlog growth',
        'biotech funding',
        'instrument demand',
        'academic grants',
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
        if "backlog growth" in text:
            self._boost_row(out, 0.04 + 0 * 0.005, "anchor_bull:backlog growth")
        if "biotech funding" in text:
            self._boost_row(out, 0.04 + 1 * 0.005, "anchor_bull:biotech funding")
        if "instrument demand" in text:
            self._boost_row(out, 0.04 + 2 * 0.005, "anchor_bull:instrument demand")
        if "academic grants" in text:
            self._boost_row(out, 0.04 + 3 * 0.005, "anchor_bull:academic grants")
        if out.get("industry_pipeline", {}).get("score_delta", 0) > 0.05:
            self._boost_row(out, 0.01, "pipeline_tailwind")
        return out

    def enhance_score(self, symbol, score, p_up, *, row=None):
        s, p = super().enhance_score(symbol, score, p_up, row=row)
        if row and float(row.get("industry_z_20") or row.get("industry_sympathy_score") or 0) > 0.3:
            s += 0.006
        return s, p


ANCHOR = LifeSciencesToolsAnchor()
