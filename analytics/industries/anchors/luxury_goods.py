"""
Luxury Goods industry anchor — HNW wealth; travel retail flows.

Primary anchor: LVMUY
Smoke tickers: LVMUY, TPR, RL, CPRI, RACE, BIRK
ETF proxy: XLY
"""

from __future__ import annotations

from typing import Any

from analytics.industries.anchors._base import IndustryAnchor


class LuxuryGoodsAnchor(IndustryAnchor):
    INDUSTRY_ID = 'luxury_goods'
    INDUSTRY_NAME = 'Luxury Goods'
    ETF_PROXY = 'XLY'
    ANCHOR_TICKER = 'LVMUY'
    SMOKE_TICKERS = (
        'LVMUY',
        'TPR',
        'RL',
        'CPRI',
        'RACE',
        'BIRK'
    )
    HISTORICAL_START = "2023-06-01"
    HISTORICAL_END = "2024-06-30"
    COMOVEMENT_MODE = 'hybrid'
    RATE_SENSITIVITY = 0.0
    EXPANSION_BETA = 0.6

    NEWS_BULL_PHRASES = (
        'china reopen',
        'pricing power',
        'tourist spend',
        'hnw growth',
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
        if "china reopen" in text:
            self._boost_row(out, 0.04 + 0 * 0.005, "anchor_bull:china reopen")
        if "pricing power" in text:
            self._boost_row(out, 0.04 + 1 * 0.005, "anchor_bull:pricing power")
        if "tourist spend" in text:
            self._boost_row(out, 0.04 + 2 * 0.005, "anchor_bull:tourist spend")
        if "hnw growth" in text:
            self._boost_row(out, 0.04 + 3 * 0.005, "anchor_bull:hnw growth")
        if out.get("industry_pipeline", {}).get("score_delta", 0) > 0.05:
            self._boost_row(out, 0.01, "pipeline_tailwind")
        return out

    def enhance_score(self, symbol, score, p_up, *, row=None):
        s, p = super().enhance_score(symbol, score, p_up, row=row)
        if row and float(row.get("industry_z_20") or row.get("industry_sympathy_score") or 0) > 0.3:
            s += 0.006
        return s, p


ANCHOR = LuxuryGoodsAnchor()
