"""
Chemicals industry anchor — Spread over nat gas; early cycle.

Primary anchor: LIN
Smoke tickers: LIN, APD, ECL, DD, DOW, LYB
ETF proxy: XLB
"""

from __future__ import annotations

from typing import Any

from analytics.industries.anchors._base import IndustryAnchor


class ChemicalsAnchor(IndustryAnchor):
    INDUSTRY_ID = 'chemicals'
    INDUSTRY_NAME = 'Chemicals'
    ETF_PROXY = 'XLB'
    ANCHOR_TICKER = 'LIN'
    SMOKE_TICKERS = (
        'LIN',
        'APD',
        'ECL',
        'DD',
        'DOW',
        'LYB'
    )
    HISTORICAL_START = "2023-06-01"
    HISTORICAL_END = "2024-06-30"
    COMOVEMENT_MODE = 'hybrid'
    RATE_SENSITIVITY = 0.0
    EXPANSION_BETA = 1.0

    NEWS_BULL_PHRASES = (
        'spread widen',
        'volume up',
        'auto build',
        'crop acreage',
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
        if "spread widen" in text:
            self._boost_row(out, 0.04 + 0 * 0.005, "anchor_bull:spread widen")
        if "volume up" in text:
            self._boost_row(out, 0.04 + 1 * 0.005, "anchor_bull:volume up")
        if "auto build" in text:
            self._boost_row(out, 0.04 + 2 * 0.005, "anchor_bull:auto build")
        if "crop acreage" in text:
            self._boost_row(out, 0.04 + 3 * 0.005, "anchor_bull:crop acreage")
        if out.get("industry_pipeline", {}).get("score_delta", 0) > 0.05:
            self._boost_row(out, 0.01, "pipeline_tailwind")
        return out

    def enhance_score(self, symbol, score, p_up, *, row=None):
        s, p = super().enhance_score(symbol, score, p_up, row=row)
        if row and float(row.get("industry_z_20") or row.get("industry_sympathy_score") or 0) > 0.3:
            s += 0.006
        return s, p


ANCHOR = ChemicalsAnchor()
