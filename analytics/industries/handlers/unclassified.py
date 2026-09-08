"""Fallback handler for symbols that do not match any of the 50 buckets."""

from __future__ import annotations

from analytics.industries.base import (
    BaseIndustryHandler,
    ComovementMode,
    FactorTiltResult,
    IndustryContext,
)


class UnclassifiedHandler(BaseIndustryHandler):
    INDUSTRY_ID = "unclassified"
    INDUSTRY_NAME = "Unclassified"
    ETF_PROXY = "SPY"
    COMOVEMENT_MODE = ComovementMode.HYBRID
    RATE_SENSITIVITY = 0.0
    EXPANSION_BETA = 0.5
    NASDAQ_BETA = 1.0
    DEFENSIVE_SCORE = 0.0
    INTRA_CORR_PRIOR = 0.5

    def compute_factor_tilts(self, ctx: IndustryContext) -> FactorTiltResult:
        rate = self._base_rate_tilt(ctx)
        exp = self._base_expansion_tilt(ctx)
        ndx = self._base_nasdaq_tilt(ctx)
        combined = rate + exp * 0.4 + ndx * 0.35
        return FactorTiltResult(
            rate_tilt=rate,
            expansion_tilt=exp,
            nasdaq_tilt=ndx,
            combined=combined,
        )


HANDLER = UnclassifiedHandler()
