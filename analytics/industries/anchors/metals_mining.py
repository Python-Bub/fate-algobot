"""
Metals & Mining industry anchor — Daily metal price moves dominate.

Primary anchor: FCX
Smoke tickers: FCX, NEM, GOLD, RIO, BHP, VALE
ETF proxy: XME
"""

from __future__ import annotations

from typing import Any

from analytics.industries.anchors._base import IndustryAnchor


class MetalsMiningAnchor(IndustryAnchor):
    INDUSTRY_ID = 'metals_mining'
    INDUSTRY_NAME = 'Metals & Mining'
    ETF_PROXY = 'XME'
    ANCHOR_TICKER = 'FCX'
    SMOKE_TICKERS = (
        'FCX',
        'NEM',
        'GOLD',
        'RIO',
        'BHP',
        'VALE'
    )
    HISTORICAL_START = "2023-06-01"
    HISTORICAL_END = "2024-06-30"
    COMOVEMENT_MODE = 'commodity'
    RATE_SENSITIVITY = 0.0
    EXPANSION_BETA = 1.1

    NEWS_BULL_PHRASES = (
        'copper squeeze',
        'china stimulus',
        'gold safe haven',
        'lme draw',
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
        if "copper squeeze" in text:
            self._boost_row(out, 0.04 + 0 * 0.005, "anchor_bull:copper squeeze")
        if "china stimulus" in text:
            self._boost_row(out, 0.04 + 1 * 0.005, "anchor_bull:china stimulus")
        if "gold safe haven" in text:
            self._boost_row(out, 0.04 + 2 * 0.005, "anchor_bull:gold safe haven")
        if "lme draw" in text:
            self._boost_row(out, 0.04 + 3 * 0.005, "anchor_bull:lme draw")
        if out.get("industry_pipeline", {}).get("score_delta", 0) > 0.05:
            self._boost_row(out, 0.01, "pipeline_tailwind")
        return out

    def enhance_score(self, symbol, score, p_up, *, row=None):
        s, p = super().enhance_score(symbol, score, p_up, row=row)
        if row and float(row.get("industry_z_20") or row.get("industry_sympathy_score") or 0) > 0.3:
            s += 0.006
        return s, p


ANCHOR = MetalsMiningAnchor()
