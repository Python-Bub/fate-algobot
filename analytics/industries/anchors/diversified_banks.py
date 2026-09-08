"""
Diversified Banks industry anchor — NIM vs Fed path; stress tests move group.

Primary anchor: JPM
Smoke tickers: JPM, BAC, WFC, C, MS, GS
ETF proxy: KBE
"""

from __future__ import annotations

from typing import Any

from analytics.industries.anchors._base import IndustryAnchor


class DiversifiedBanksAnchor(IndustryAnchor):
    INDUSTRY_ID = 'diversified_banks'
    INDUSTRY_NAME = 'Diversified Banks'
    ETF_PROXY = 'KBE'
    ANCHOR_TICKER = 'JPM'
    SMOKE_TICKERS = (
        'JPM',
        'BAC',
        'WFC',
        'C',
        'MS',
        'GS'
    )
    HISTORICAL_START = "2023-06-01"
    HISTORICAL_END = "2024-06-30"
    COMOVEMENT_MODE = 'hybrid'
    RATE_SENSITIVITY = 0.4
    EXPANSION_BETA = 0.8

    NEWS_BULL_PHRASES = (
        'nim expansion',
        'net interest income',
        'stress test pass',
        'loan growth',
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
        if "nim expansion" in text:
            self._boost_row(out, 0.04 + 0 * 0.005, "anchor_bull:nim expansion")
        if "net interest income" in text:
            self._boost_row(out, 0.04 + 1 * 0.005, "anchor_bull:net interest income")
        if "stress test pass" in text:
            self._boost_row(out, 0.04 + 2 * 0.005, "anchor_bull:stress test pass")
        if "loan growth" in text:
            self._boost_row(out, 0.04 + 3 * 0.005, "anchor_bull:loan growth")
        if out.get("industry_pipeline", {}).get("score_delta", 0) > 0.05:
            self._boost_row(out, 0.01, "pipeline_tailwind")
        return out

    def enhance_score(self, symbol, score, p_up, *, row=None):
        s, p = super().enhance_score(symbol, score, p_up, row=row)
        if row and float(row.get("industry_z_20") or row.get("industry_sympathy_score") or 0) > 0.3:
            s += 0.006
        return s, p


ANCHOR = DiversifiedBanksAnchor()
