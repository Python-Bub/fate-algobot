"""
Financial Data & Exchanges industry anchor — ADV and VIX drive exchange revenues.

Primary anchor: SPGI
Smoke tickers: SPGI, ICE, CME, MCO, MSCI, NDAQ
ETF proxy: XLF
"""

from __future__ import annotations

from typing import Any

from analytics.industries.anchors._base import IndustryAnchor


class FinancialDataExchangesAnchor(IndustryAnchor):
    INDUSTRY_ID = 'financial_data_exchanges'
    INDUSTRY_NAME = 'Financial Data & Exchanges'
    ETF_PROXY = 'XLF'
    ANCHOR_TICKER = 'SPGI'
    SMOKE_TICKERS = (
        'SPGI',
        'ICE',
        'CME',
        'MCO',
        'MSCI',
        'NDAQ'
    )
    HISTORICAL_START = "2023-06-01"
    HISTORICAL_END = "2024-06-30"
    COMOVEMENT_MODE = 'follow_market'
    RATE_SENSITIVITY = 0.3
    EXPANSION_BETA = 0.9

    NEWS_BULL_PHRASES = (
        'trading volume',
        'vix elevated',
        'aum growth',
        'data subscription',
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
        if "trading volume" in text:
            self._boost_row(out, 0.04 + 0 * 0.005, "anchor_bull:trading volume")
        if "vix elevated" in text:
            self._boost_row(out, 0.04 + 1 * 0.005, "anchor_bull:vix elevated")
        if "aum growth" in text:
            self._boost_row(out, 0.04 + 2 * 0.005, "anchor_bull:aum growth")
        if "data subscription" in text:
            self._boost_row(out, 0.04 + 3 * 0.005, "anchor_bull:data subscription")
        if out.get("industry_pipeline", {}).get("score_delta", 0) > 0.05:
            self._boost_row(out, 0.01, "pipeline_tailwind")
        return out

    def enhance_score(self, symbol, score, p_up, *, row=None):
        s, p = super().enhance_score(symbol, score, p_up, row=row)
        if row and float(row.get("industry_z_20") or row.get("industry_sympathy_score") or 0) > 0.3:
            s += 0.006
        return s, p


ANCHOR = FinancialDataExchangesAnchor()
