"""
Integrated Oil & Gas industry anchor — Lockstep with WTI/Brent futures.

Primary anchor: XOM
Smoke tickers: XOM, CVX, SHEL, TTE, BP, COP
ETF proxy: XLE
"""

from __future__ import annotations

from typing import Any

from analytics.industries.anchors._base import IndustryAnchor


class IntegratedOilGasAnchor(IndustryAnchor):
    INDUSTRY_ID = 'integrated_oil_gas'
    INDUSTRY_NAME = 'Integrated Oil & Gas'
    ETF_PROXY = 'XLE'
    ANCHOR_TICKER = 'XOM'
    SMOKE_TICKERS = (
        'XOM',
        'CVX',
        'SHEL',
        'TTE',
        'BP',
        'COP'
    )
    HISTORICAL_START = "2023-06-01"
    HISTORICAL_END = "2024-06-30"
    COMOVEMENT_MODE = 'commodity'
    RATE_SENSITIVITY = 0.2
    EXPANSION_BETA = 0.6

    NEWS_BULL_PHRASES = (
        'opec cut',
        'crude rally',
        'refining margin',
        'buyback',
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
        if "opec cut" in text:
            self._boost_row(out, 0.04 + 0 * 0.005, "anchor_bull:opec cut")
        if "crude rally" in text:
            self._boost_row(out, 0.04 + 1 * 0.005, "anchor_bull:crude rally")
        if "refining margin" in text:
            self._boost_row(out, 0.04 + 2 * 0.005, "anchor_bull:refining margin")
        if "buyback" in text:
            self._boost_row(out, 0.04 + 3 * 0.005, "anchor_bull:buyback")
        if out.get("industry_pipeline", {}).get("score_delta", 0) > 0.05:
            self._boost_row(out, 0.01, "pipeline_tailwind")
        return out

    def enhance_score(self, symbol, score, p_up, *, row=None):
        s, p = super().enhance_score(symbol, score, p_up, row=row)
        if row and float(row.get("industry_z_20") or row.get("industry_sympathy_score") or 0) > 0.3:
            s += 0.006
        return s, p


ANCHOR = IntegratedOilGasAnchor()
