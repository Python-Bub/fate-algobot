"""
Renewable Energy industry anchor — Rate-sensitive upfront capex; policy driven.

Primary anchor: ENPH
Smoke tickers: ENPH, SEDG, FSLR, NEE, RUN, PLUG
ETF proxy: ICLN
"""

from __future__ import annotations

from typing import Any

from analytics.industries.anchors._base import IndustryAnchor


class RenewableEnergyAnchor(IndustryAnchor):
    INDUSTRY_ID = 'renewable_energy'
    INDUSTRY_NAME = 'Renewable Energy'
    ETF_PROXY = 'ICLN'
    ANCHOR_TICKER = 'ENPH'
    SMOKE_TICKERS = (
        'ENPH',
        'SEDG',
        'FSLR',
        'NEE',
        'RUN',
        'PLUG'
    )
    HISTORICAL_START = "2023-06-01"
    HISTORICAL_END = "2024-06-30"
    COMOVEMENT_MODE = 'inverse_rates'
    RATE_SENSITIVITY = -0.5
    EXPANSION_BETA = 0.7

    NEWS_BULL_PHRASES = (
        'ira credit',
        'solar demand',
        'lcoe decline',
        'policy support',
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
        if "ira credit" in text:
            self._boost_row(out, 0.04 + 0 * 0.005, "anchor_bull:ira credit")
        if "solar demand" in text:
            self._boost_row(out, 0.04 + 1 * 0.005, "anchor_bull:solar demand")
        if "lcoe decline" in text:
            self._boost_row(out, 0.04 + 2 * 0.005, "anchor_bull:lcoe decline")
        if "policy support" in text:
            self._boost_row(out, 0.04 + 3 * 0.005, "anchor_bull:policy support")
        if out.get("industry_pipeline", {}).get("score_delta", 0) > 0.05:
            self._boost_row(out, 0.01, "pipeline_tailwind")
        return out

    def enhance_score(self, symbol, score, p_up, *, row=None):
        s, p = super().enhance_score(symbol, score, p_up, row=row)
        if row and float(row.get("industry_z_20") or row.get("industry_sympathy_score") or 0) > 0.3:
            s += 0.006
        return s, p


ANCHOR = RenewableEnergyAnchor()
