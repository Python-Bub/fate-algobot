"""
Big Pharma industry anchor — Patent cliff timeline; Medicare pricing; low-beta defensive.

Primary anchor: LLY
Smoke tickers: LLY, JNJ, MRK, PFE, ABBV, NVS
ETF proxy: XPH
"""

from __future__ import annotations

from typing import Any

from analytics.industries.anchors._base import IndustryAnchor


class BigPharmaAnchor(IndustryAnchor):
    INDUSTRY_ID = 'big_pharma'
    INDUSTRY_NAME = 'Big Pharma'
    ETF_PROXY = 'XPH'
    ANCHOR_TICKER = 'LLY'
    SMOKE_TICKERS = (
        'LLY',
        'JNJ',
        'MRK',
        'PFE',
        'ABBV',
        'NVS'
    )
    HISTORICAL_START = "2023-06-01"
    HISTORICAL_END = "2024-06-30"
    COMOVEMENT_MODE = 'defensive'
    RATE_SENSITIVITY = 0.0
    EXPANSION_BETA = 0.2

    NEWS_BULL_PHRASES = (
        'beats estimates',
        'raises guidance',
        'patent win',
        'formulary inclusion',
        'blockbuster',
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
        if "beats estimates" in text:
            self._boost_row(out, 0.04 + 0 * 0.005, "anchor_bull:beats estimates")
        if "raises guidance" in text:
            self._boost_row(out, 0.04 + 1 * 0.005, "anchor_bull:raises guidance")
        if "patent win" in text:
            self._boost_row(out, 0.04 + 2 * 0.005, "anchor_bull:patent win")
        if "formulary inclusion" in text:
            self._boost_row(out, 0.04 + 3 * 0.005, "anchor_bull:formulary inclusion")
        if out.get("industry_pipeline", {}).get("score_delta", 0) > 0.05:
            self._boost_row(out, 0.01, "pipeline_tailwind")
        return out

    def enhance_score(self, symbol, score, p_up, *, row=None):
        s, p = super().enhance_score(symbol, score, p_up, row=row)
        if row and float(row.get("industry_z_20") or row.get("industry_sympathy_score") or 0) > 0.3:
            s += 0.006
        return s, p


ANCHOR = BigPharmaAnchor()
