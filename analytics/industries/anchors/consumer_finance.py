"""
Consumer Finance industry anchor — NCO rate; consumer credit delinquency.

Primary anchor: V
Smoke tickers: V, MA, AXP, COF, SYF, ALLY
ETF proxy: XLF
"""

from __future__ import annotations

from typing import Any

from analytics.industries.anchors._base import IndustryAnchor


class ConsumerFinanceAnchor(IndustryAnchor):
    INDUSTRY_ID = 'consumer_finance'
    INDUSTRY_NAME = 'Consumer Finance'
    ETF_PROXY = 'XLF'
    ANCHOR_TICKER = 'V'
    SMOKE_TICKERS = (
        'V',
        'MA',
        'AXP',
        'COF',
        'SYF',
        'ALLY'
    )
    HISTORICAL_START = "2023-06-01"
    HISTORICAL_END = "2024-06-30"
    COMOVEMENT_MODE = 'hybrid'
    RATE_SENSITIVITY = 0.35
    EXPANSION_BETA = 0.8

    NEWS_BULL_PHRASES = (
        'spend growth',
        'delinquency stable',
        'loan growth',
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
        if "spend growth" in text:
            self._boost_row(out, 0.04 + 0 * 0.005, "anchor_bull:spend growth")
        if "delinquency stable" in text:
            self._boost_row(out, 0.04 + 1 * 0.005, "anchor_bull:delinquency stable")
        if "loan growth" in text:
            self._boost_row(out, 0.04 + 2 * 0.005, "anchor_bull:loan growth")
        if out.get("industry_pipeline", {}).get("score_delta", 0) > 0.05:
            self._boost_row(out, 0.01, "pipeline_tailwind")
        return out

    def enhance_score(self, symbol, score, p_up, *, row=None):
        s, p = super().enhance_score(symbol, score, p_up, row=row)
        if row and float(row.get("industry_z_20") or row.get("industry_sympathy_score") or 0) > 0.3:
            s += 0.006
        return s, p


ANCHOR = ConsumerFinanceAnchor()
