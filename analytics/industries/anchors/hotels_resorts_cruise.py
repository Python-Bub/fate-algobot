"""
Hotels & Cruise industry anchor — RevPAR; airline passenger volumes.

Primary anchor: MAR
Smoke tickers: MAR, HLT, H, CCL, RCL, NCLH
ETF proxy: XLY
"""

from __future__ import annotations

from typing import Any

from analytics.industries.anchors._base import IndustryAnchor


class HotelsResortsCruiseAnchor(IndustryAnchor):
    INDUSTRY_ID = 'hotels_resorts_cruise'
    INDUSTRY_NAME = 'Hotels & Cruise'
    ETF_PROXY = 'XLY'
    ANCHOR_TICKER = 'MAR'
    SMOKE_TICKERS = (
        'MAR',
        'HLT',
        'H',
        'CCL',
        'RCL',
        'NCLH'
    )
    HISTORICAL_START = "2023-06-01"
    HISTORICAL_END = "2024-06-30"
    COMOVEMENT_MODE = 'hybrid'
    RATE_SENSITIVITY = 0.0
    EXPANSION_BETA = 0.9

    NEWS_BULL_PHRASES = (
        'revpar up',
        'booking strong',
        'load factor',
        'business travel',
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
        if "revpar up" in text:
            self._boost_row(out, 0.04 + 0 * 0.005, "anchor_bull:revpar up")
        if "booking strong" in text:
            self._boost_row(out, 0.04 + 1 * 0.005, "anchor_bull:booking strong")
        if "load factor" in text:
            self._boost_row(out, 0.04 + 2 * 0.005, "anchor_bull:load factor")
        if "business travel" in text:
            self._boost_row(out, 0.04 + 3 * 0.005, "anchor_bull:business travel")
        if out.get("industry_pipeline", {}).get("score_delta", 0) > 0.05:
            self._boost_row(out, 0.01, "pipeline_tailwind")
        return out

    def enhance_score(self, symbol, score, p_up, *, row=None):
        s, p = super().enhance_score(symbol, score, p_up, row=row)
        if row and float(row.get("industry_z_20") or row.get("industry_sympathy_score") or 0) > 0.3:
            s += 0.006
        return s, p


ANCHOR = HotelsResortsCruiseAnchor()
