"""
Hypermarkets & Discount industry anchor — Counter-cyclical; gas prices affect wallet share.

Primary anchor: WMT
Smoke tickers: WMT, COST, TGT, DG, DLTR, BJ
ETF proxy: XRT
"""

from __future__ import annotations

from typing import Any

from analytics.industries.anchors._base import IndustryAnchor


class HypermarketsDiscountAnchor(IndustryAnchor):
    INDUSTRY_ID = 'hypermarkets_discount'
    INDUSTRY_NAME = 'Hypermarkets & Discount'
    ETF_PROXY = 'XRT'
    ANCHOR_TICKER = 'WMT'
    SMOKE_TICKERS = (
        'WMT',
        'COST',
        'TGT',
        'DG',
        'DLTR',
        'BJ'
    )
    HISTORICAL_START = "2023-06-01"
    HISTORICAL_END = "2024-06-30"
    COMOVEMENT_MODE = 'defensive'
    RATE_SENSITIVITY = 0.0
    EXPANSION_BETA = 0.3

    NEWS_BULL_PHRASES = (
        'traffic up',
        'market share gain',
        'inventory turn',
        'gas savings',
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
        if "traffic up" in text:
            self._boost_row(out, 0.04 + 0 * 0.005, "anchor_bull:traffic up")
        if "market share gain" in text:
            self._boost_row(out, 0.04 + 1 * 0.005, "anchor_bull:market share gain")
        if "inventory turn" in text:
            self._boost_row(out, 0.04 + 2 * 0.005, "anchor_bull:inventory turn")
        if "gas savings" in text:
            self._boost_row(out, 0.04 + 3 * 0.005, "anchor_bull:gas savings")
        if out.get("industry_pipeline", {}).get("score_delta", 0) > 0.05:
            self._boost_row(out, 0.01, "pipeline_tailwind")
        return out

    def enhance_score(self, symbol, score, p_up, *, row=None):
        s, p = super().enhance_score(symbol, score, p_up, row=row)
        if row and float(row.get("industry_z_20") or row.get("industry_sympathy_score") or 0) > 0.3:
            s += 0.006
        return s, p


ANCHOR = HypermarketsDiscountAnchor()
