"""
Semiconductors industry anchor — Book-to-bill; inventory days; trade war headline risk.

Primary anchor: NVDA
Smoke tickers: NVDA, TSM, AVGO, AMD, INTC, QCOM
ETF proxy: SMH
"""

from __future__ import annotations

from typing import Any

from analytics.industries.anchors._base import IndustryAnchor


class SemiconductorsAnchor(IndustryAnchor):
    INDUSTRY_ID = 'semiconductors'
    INDUSTRY_NAME = 'Semiconductors'
    ETF_PROXY = 'SMH'
    ANCHOR_TICKER = 'NVDA'
    SMOKE_TICKERS = (
        'NVDA',
        'TSM',
        'AVGO',
        'AMD',
        'INTC',
        'QCOM'
    )
    HISTORICAL_START = "2023-06-01"
    HISTORICAL_END = "2024-06-30"
    COMOVEMENT_MODE = 'follow_nasdaq'
    RATE_SENSITIVITY = 0.0
    EXPANSION_BETA = 1.2

    NEWS_BULL_PHRASES = (
        'ai demand',
        'book-to-bill',
        'supply tight',
        'export license',
        'data center',
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
        if "ai demand" in text:
            self._boost_row(out, 0.04 + 0 * 0.005, "anchor_bull:ai demand")
        if "book-to-bill" in text:
            self._boost_row(out, 0.04 + 1 * 0.005, "anchor_bull:book-to-bill")
        if "supply tight" in text:
            self._boost_row(out, 0.04 + 2 * 0.005, "anchor_bull:supply tight")
        if "export license" in text:
            self._boost_row(out, 0.04 + 3 * 0.005, "anchor_bull:export license")
        if out.get("industry_pipeline", {}).get("score_delta", 0) > 0.05:
            self._boost_row(out, 0.01, "pipeline_tailwind")
        return out

    def enhance_score(self, symbol, score, p_up, *, row=None):
        s, p = super().enhance_score(symbol, score, p_up, row=row)
        if row and float(row.get("industry_z_20") or row.get("industry_sympathy_score") or 0) > 0.3:
            s += 0.006
        return s, p


ANCHOR = SemiconductorsAnchor()
