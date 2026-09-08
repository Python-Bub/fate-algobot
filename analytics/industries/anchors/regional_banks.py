"""
Regional Banks industry anchor — Systemic cluster risk on one failure.

Primary anchor: PNC
Smoke tickers: PNC, USB, TFC, FITB, RF, KEY
ETF proxy: KRE
"""

from __future__ import annotations

from typing import Any

from analytics.industries.anchors._base import IndustryAnchor


class RegionalBanksAnchor(IndustryAnchor):
    INDUSTRY_ID = 'regional_banks'
    INDUSTRY_NAME = 'Regional Banks'
    ETF_PROXY = 'KRE'
    ANCHOR_TICKER = 'PNC'
    SMOKE_TICKERS = (
        'PNC',
        'USB',
        'TFC',
        'FITB',
        'RF',
        'KEY'
    )
    HISTORICAL_START = "2023-06-01"
    HISTORICAL_END = "2024-06-30"
    COMOVEMENT_MODE = 'hybrid'
    RATE_SENSITIVITY = 0.5
    EXPANSION_BETA = 0.7

    NEWS_BULL_PHRASES = (
        'deposit stable',
        'cre manageable',
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
        if "deposit stable" in text:
            self._boost_row(out, 0.04 + 0 * 0.005, "anchor_bull:deposit stable")
        if "cre manageable" in text:
            self._boost_row(out, 0.04 + 1 * 0.005, "anchor_bull:cre manageable")
        if "buyback" in text:
            self._boost_row(out, 0.04 + 2 * 0.005, "anchor_bull:buyback")
        if out.get("industry_pipeline", {}).get("score_delta", 0) > 0.05:
            self._boost_row(out, 0.01, "pipeline_tailwind")
        return out

    def enhance_score(self, symbol, score, p_up, *, row=None):
        s, p = super().enhance_score(symbol, score, p_up, row=row)
        if row and float(row.get("industry_z_20") or row.get("industry_sympathy_score") or 0) > 0.3:
            s += 0.006
        return s, p


ANCHOR = RegionalBanksAnchor()
