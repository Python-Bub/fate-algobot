"""
Biotechnology industry anchor — R&D burn vs cash runway; binary trial outcomes; low SPY correlation.

Primary anchor: AMGN
Smoke tickers: AMGN, GILD, VRTX, REGN, BIIB, MRNA
ETF proxy: IBB
"""

from __future__ import annotations

from typing import Any

from analytics.industries.anchors._base import IndustryAnchor


class BiotechAnchor(IndustryAnchor):
    INDUSTRY_ID = 'biotech'
    INDUSTRY_NAME = 'Biotechnology'
    ETF_PROXY = 'IBB'
    ANCHOR_TICKER = 'AMGN'
    SMOKE_TICKERS = (
        'AMGN',
        'GILD',
        'VRTX',
        'REGN',
        'BIIB',
        'MRNA'
    )
    HISTORICAL_START = "2023-06-01"
    HISTORICAL_END = "2024-06-30"
    COMOVEMENT_MODE = 'event_driven'
    RATE_SENSITIVITY = -0.1
    EXPANSION_BETA = 0.3

    NEWS_BULL_PHRASES = (
        'phase 3 success',
        'fda approval',
        'breakthrough therapy',
        'trial met primary',
        'orphan drug',
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
        if "phase 3 success" in text:
            self._boost_row(out, 0.04 + 0 * 0.005, "anchor_bull:phase 3 success")
        if "fda approval" in text:
            self._boost_row(out, 0.04 + 1 * 0.005, "anchor_bull:fda approval")
        if "breakthrough therapy" in text:
            self._boost_row(out, 0.04 + 2 * 0.005, "anchor_bull:breakthrough therapy")
        if "trial met primary" in text:
            self._boost_row(out, 0.04 + 3 * 0.005, "anchor_bull:trial met primary")
        if out.get("industry_pipeline", {}).get("score_delta", 0) > 0.05:
            self._boost_row(out, 0.01, "pipeline_tailwind")
        return out

    def enhance_score(self, symbol, score, p_up, *, row=None):
        s, p = super().enhance_score(symbol, score, p_up, row=row)
        if row and float(row.get("industry_z_20") or row.get("industry_sympathy_score") or 0) > 0.3:
            s += 0.006
        return s, p


ANCHOR = BiotechAnchor()
