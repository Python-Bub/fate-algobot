"""
Household Products industry anchor — Volume vs price mix; recession resilient.

Primary anchor: PG
Smoke tickers: PG, CL, KMB, CHD, CLX, EL
ETF proxy: XLP
"""

from __future__ import annotations

from typing import Any

from analytics.industries.anchors._base import IndustryAnchor


class HouseholdPersonalProductsAnchor(IndustryAnchor):
    INDUSTRY_ID = 'household_personal_products'
    INDUSTRY_NAME = 'Household Products'
    ETF_PROXY = 'XLP'
    ANCHOR_TICKER = 'PG'
    SMOKE_TICKERS = (
        'PG',
        'CL',
        'KMB',
        'CHD',
        'CLX',
        'EL'
    )
    HISTORICAL_START = "2023-06-01"
    HISTORICAL_END = "2024-06-30"
    COMOVEMENT_MODE = 'defensive'
    RATE_SENSITIVITY = 0.0
    EXPANSION_BETA = 0.1

    NEWS_BULL_PHRASES = (
        'pricing power',
        'volume stable',
        'premium mix',
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
        if "pricing power" in text:
            self._boost_row(out, 0.04 + 0 * 0.005, "anchor_bull:pricing power")
        if "volume stable" in text:
            self._boost_row(out, 0.04 + 1 * 0.005, "anchor_bull:volume stable")
        if "premium mix" in text:
            self._boost_row(out, 0.04 + 2 * 0.005, "anchor_bull:premium mix")
        if out.get("industry_pipeline", {}).get("score_delta", 0) > 0.05:
            self._boost_row(out, 0.01, "pipeline_tailwind")
        return out

    def enhance_score(self, symbol, score, p_up, *, row=None):
        s, p = super().enhance_score(symbol, score, p_up, row=row)
        if row and float(row.get("industry_z_20") or row.get("industry_sympathy_score") or 0) > 0.3:
            s += 0.006
        return s, p


ANCHOR = HouseholdPersonalProductsAnchor()
