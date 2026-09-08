"""
Oil & Gas E&P industry anchor — Amplified oil beta; EIA inventory weekly.

Primary anchor: EOG
Smoke tickers: EOG, PXD, DVN, FANG, MRO, OVV
ETF proxy: XOP
"""

from __future__ import annotations

from typing import Any

from analytics.industries.anchors._base import IndustryAnchor


class OilGasEpAnchor(IndustryAnchor):
    INDUSTRY_ID = 'oil_gas_ep'
    INDUSTRY_NAME = 'Oil & Gas E&P'
    ETF_PROXY = 'XOP'
    ANCHOR_TICKER = 'EOG'
    SMOKE_TICKERS = (
        'EOG',
        'PXD',
        'DVN',
        'FANG',
        'MRO',
        'OVV'
    )
    HISTORICAL_START = "2023-06-01"
    HISTORICAL_END = "2024-06-30"
    COMOVEMENT_MODE = 'commodity'
    RATE_SENSITIVITY = 0.1
    EXPANSION_BETA = 0.9

    NEWS_BULL_PHRASES = (
        'production beat',
        'hedge gain',
        'rig count',
        'permit',
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
        if "production beat" in text:
            self._boost_row(out, 0.04 + 0 * 0.005, "anchor_bull:production beat")
        if "hedge gain" in text:
            self._boost_row(out, 0.04 + 1 * 0.005, "anchor_bull:hedge gain")
        if "rig count" in text:
            self._boost_row(out, 0.04 + 2 * 0.005, "anchor_bull:rig count")
        if "permit" in text:
            self._boost_row(out, 0.04 + 3 * 0.005, "anchor_bull:permit")
        if out.get("industry_pipeline", {}).get("score_delta", 0) > 0.05:
            self._boost_row(out, 0.01, "pipeline_tailwind")
        return out

    def enhance_score(self, symbol, score, p_up, *, row=None):
        s, p = super().enhance_score(symbol, score, p_up, row=row)
        if row and float(row.get("industry_z_20") or row.get("industry_sympathy_score") or 0) > 0.3:
            s += 0.006
        return s, p


ANCHOR = OilGasEpAnchor()
