"""
Retail REITs industry anchor — Tenant occupancy cost ratio; anchor tenant risk.

Primary anchor: SPG
Smoke tickers: SPG, O, REG, FRT, KIM, BRX
ETF proxy: VNQ
"""

from __future__ import annotations

from typing import Any

from analytics.industries.anchors._base import IndustryAnchor


class RetailReitsAnchor(IndustryAnchor):
    INDUSTRY_ID = 'retail_reits'
    INDUSTRY_NAME = 'Retail REITs'
    ETF_PROXY = 'VNQ'
    ANCHOR_TICKER = 'SPG'
    SMOKE_TICKERS = (
        'SPG',
        'O',
        'REG',
        'FRT',
        'KIM',
        'BRX'
    )
    HISTORICAL_START = "2023-06-01"
    HISTORICAL_END = "2024-06-30"
    COMOVEMENT_MODE = 'inverse_rates'
    RATE_SENSITIVITY = -0.6
    EXPANSION_BETA = 0.4

    NEWS_BULL_PHRASES = (
        'foot traffic',
        'tenant sales',
        're-leasing spread',
        'occupancy cost ratio ok',
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
        if "foot traffic" in text:
            self._boost_row(out, 0.04 + 0 * 0.005, "anchor_bull:foot traffic")
        if "tenant sales" in text:
            self._boost_row(out, 0.04 + 1 * 0.005, "anchor_bull:tenant sales")
        if "re-leasing spread" in text:
            self._boost_row(out, 0.04 + 2 * 0.005, "anchor_bull:re-leasing spread")
        if "occupancy cost ratio ok" in text:
            self._boost_row(out, 0.04 + 3 * 0.005, "anchor_bull:occupancy cost ratio")
        if out.get("industry_pipeline", {}).get("score_delta", 0) > 0.05:
            self._boost_row(out, 0.01, "pipeline_tailwind")
        return out

    def enhance_score(self, symbol, score, p_up, *, row=None):
        s, p = super().enhance_score(symbol, score, p_up, row=row)
        if row and float(row.get("industry_z_20") or row.get("industry_sympathy_score") or 0) > 0.3:
            s += 0.006
        return s, p


ANCHOR = RetailReitsAnchor()
