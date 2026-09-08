"""
Independent Power Producers industry anchor — Spark/dark spread; grid constraints.

Primary anchor: VST
Smoke tickers: VST, NRG, CEG, AES, CWEN
ETF proxy: XLU
"""

from __future__ import annotations

from typing import Any

from analytics.industries.anchors._base import IndustryAnchor


class IndependentPowerProducersAnchor(IndustryAnchor):
    INDUSTRY_ID = 'independent_power_producers'
    INDUSTRY_NAME = 'Independent Power Producers'
    ETF_PROXY = 'XLU'
    ANCHOR_TICKER = 'VST'
    SMOKE_TICKERS = (
        'VST',
        'NRG',
        'CEG',
        'AES',
        'CWEN'
    )
    HISTORICAL_START = "2023-06-01"
    HISTORICAL_END = "2024-06-30"
    COMOVEMENT_MODE = 'commodity'
    RATE_SENSITIVITY = 0.0
    EXPANSION_BETA = 0.7

    NEWS_BULL_PHRASES = (
        'spark spread widen',
        'heat wave',
        'capacity tight',
        'data center power',
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
        if "spark spread widen" in text:
            self._boost_row(out, 0.04 + 0 * 0.005, "anchor_bull:spark spread widen")
        if "heat wave" in text:
            self._boost_row(out, 0.04 + 1 * 0.005, "anchor_bull:heat wave")
        if "capacity tight" in text:
            self._boost_row(out, 0.04 + 2 * 0.005, "anchor_bull:capacity tight")
        if "data center power" in text:
            self._boost_row(out, 0.04 + 3 * 0.005, "anchor_bull:data center power")
        if out.get("industry_pipeline", {}).get("score_delta", 0) > 0.05:
            self._boost_row(out, 0.01, "pipeline_tailwind")
        return out

    def enhance_score(self, symbol, score, p_up, *, row=None):
        s, p = super().enhance_score(symbol, score, p_up, row=row)
        if row and float(row.get("industry_z_20") or row.get("industry_sympathy_score") or 0) > 0.3:
            s += 0.006
        return s, p


ANCHOR = IndependentPowerProducersAnchor()
