"""
Auto Manufacturers industry anchor — Dealer days supply; union negotiations.

Primary anchor: TSLA
Smoke tickers: TSLA, TM, GM, F, RIVN, LCID
ETF proxy: CARZ
"""

from __future__ import annotations

from typing import Any

from analytics.industries.anchors._base import IndustryAnchor


class AutoManufacturersAnchor(IndustryAnchor):
    INDUSTRY_ID = 'auto_manufacturers'
    INDUSTRY_NAME = 'Auto Manufacturers'
    ETF_PROXY = 'CARZ'
    ANCHOR_TICKER = 'TSLA'
    SMOKE_TICKERS = (
        'TSLA',
        'TM',
        'GM',
        'F',
        'RIVN',
        'LCID'
    )
    HISTORICAL_START = "2023-06-01"
    HISTORICAL_END = "2024-06-30"
    COMOVEMENT_MODE = 'hybrid'
    RATE_SENSITIVITY = 0.0
    EXPANSION_BETA = 0.9

    NEWS_BULL_PHRASES = (
        'delivery beat',
        'ev demand',
        'inventory days low',
        'incentive cut',
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
        if "delivery beat" in text:
            self._boost_row(out, 0.04 + 0 * 0.005, "anchor_bull:delivery beat")
        if "ev demand" in text:
            self._boost_row(out, 0.04 + 1 * 0.005, "anchor_bull:ev demand")
        if "inventory days low" in text:
            self._boost_row(out, 0.04 + 2 * 0.005, "anchor_bull:inventory days low")
        if "incentive cut" in text:
            self._boost_row(out, 0.04 + 3 * 0.005, "anchor_bull:incentive cut")
        if out.get("industry_pipeline", {}).get("score_delta", 0) > 0.05:
            self._boost_row(out, 0.01, "pipeline_tailwind")
        return out

    def enhance_score(self, symbol, score, p_up, *, row=None):
        s, p = super().enhance_score(symbol, score, p_up, row=row)
        if row and float(row.get("industry_z_20") or row.get("industry_sympathy_score") or 0) > 0.3:
            s += 0.006
        return s, p


ANCHOR = AutoManufacturersAnchor()
