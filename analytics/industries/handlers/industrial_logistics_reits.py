"""Industrial & Logistics REITs — Rent reversion; e-commerce % of retail."""

from __future__ import annotations

import numpy as np

from analytics.industries.base import (
    BaseIndustryHandler,
    ComovementMode,
    FactorTiltResult,
    IndustryContext,
    ClassificationResult,
)


class IndustrialLogisticsReitsHandler(BaseIndustryHandler):
    INDUSTRY_ID = 'industrial_logistics_reits'
    INDUSTRY_NAME = 'Industrial & Logistics REITs'
    ETF_PROXY = 'IYR'
    COMOVEMENT_MODE = ComovementMode.HYBRID
    RATE_SENSITIVITY = -0.55
    EXPANSION_BETA = 0.7
    NASDAQ_BETA = 0.6
    DEFENSIVE_SCORE = 0.1
    INTRA_CORR_PRIOR = 0.87

    YAHOO_PATTERNS = (
        'industrial reit',
'reit—industrial',
'warehouse',
'logistics reit',
'self storage',
'industrial logistics reits',
'industrial-logistics-reits',
'industrial & logistics reits',
'industrial & logistics reits industry'
    )
    TICKER_HINTS = frozenset({
        'PLD', 'EXR', 'PSA', 'REXR', 'FR', 'STAG', 'EGP', 'TRNO', 'COLD'
    })
    LEADER_TICKERS = (
        'PLD',
'EXR',
'PSA',
'REXR',
'FR',
'STAG',
'EGP'
    )

    NEWS_BULL = (
        'rent reversion',
'e-commerce demand',
'supply chain',
'development yield'
    )
    NEWS_BEAR = (
        'amazon slowdown',
'oversupply',
'cap rate expansion'
    )
    NEWS_EVENT_BULL = (
        'record leasing',
'rent spread'
    )
    NEWS_EVENT_BEAR = (
        'warehouse glut',
'demand softening'
    )
    COMMODITY_KEYS = (
        'warehouse',
'fulfillment',
'storage'
    )

    def refine_classification(self, ctx: IndustryContext) -> ClassificationResult | None:
        blob = f"{ctx.sector} {ctx.yahoo_industry}".lower()
        sym = ctx.symbol.upper()
        if sym in self.TICKER_HINTS:
            return ClassificationResult(
                industry_id=self.INDUSTRY_ID,
                industry_name=self.INDUSTRY_NAME,
                confidence=0.96,
                etf_proxy=self.ETF_PROXY,
                comovement_mode=self.COMOVEMENT_MODE.value,
                reasons=["ticker_hint_refine"],
            )
        for pat in self.YAHOO_PATTERNS:
            if pat in blob:
                return ClassificationResult(
                    industry_id=self.INDUSTRY_ID,
                    industry_name=self.INDUSTRY_NAME,
                    confidence=0.72,
                    etf_proxy=self.ETF_PROXY,
                    comovement_mode=self.COMOVEMENT_MODE.value,
                    reasons=[f"refine:{pat[:32]}"],
                )
        return None

    def compute_factor_tilts(self, ctx: IndustryContext) -> FactorTiltResult:
        rate = self._base_rate_tilt(ctx)
        exp = self._base_expansion_tilt(ctx)
        ndx = self._base_nasdaq_tilt(ctx)
        defensive = self._base_defensive_tilt(ctx)
        news = self.news_factor_tilt(ctx)
        commodity = self._commodity_tilt(ctx)
        notes: list[str] = []

        if self.COMOVEMENT_MODE == ComovementMode.INVERSE_RATES:
            shock = self._macro(ctx, "rate_shock_20d")
            if shock > 0.15:
                rate -= 0.08
                notes.append("rates_up_headwind")
            elif shock < -0.1:
                rate += 0.06
                notes.append("rates_down_tailwind")

        if self.COMOVEMENT_MODE == ComovementMode.EVENT_DRIVEN:
            ndx *= 0.35
            exp *= 0.4
            notes.append("event_driven_low_beta")

        if self.COMOVEMENT_MODE == ComovementMode.DEFENSIVE:
            vix = self._macro(ctx, "vix", 20.0)
            if vix > 24:
                defensive += 0.12
                notes.append("flight_to_defensive")

        if self.COMOVEMENT_MODE == ComovementMode.COMMODITY:
            commodity += self._commodity_tilt(ctx)
            notes.append("commodity_linked")

        combined = rate + exp * 0.55 + ndx * 0.35 + defensive + news * 0.45 + commodity * 0.35
        return FactorTiltResult(
            rate_tilt=float(rate),
            expansion_tilt=float(exp),
            nasdaq_tilt=float(ndx),
            defensive_tilt=float(defensive),
            commodity_tilt=float(commodity),
            news_tilt=float(news),
            combined=float(combined),
            notes=notes,
        )

    def _commodity_tilt(self, ctx: IndustryContext) -> float:
        if not ctx.news_headlines:
            return 0.0
        ns = self.score_news(ctx.news_headlines)
        tagged = [t for t in ns.event_tags if t.startswith("commodity:")]
        if not tagged:
            return 0.0
        direction = ns.net
        return float(np.tanh(direction * 1.8))

    def feature_overrides(self, ctx: IndustryContext) -> dict[str, float]:
        tilts = self.compute_factor_tilts(ctx)
        return {
            "factor_rate_tilt": tilts.rate_tilt,
            "factor_expansion_tilt": tilts.expansion_tilt,
            "industry_sympathy_score": tilts.combined * 0.25,
        }


HANDLER = IndustrialLogisticsReitsHandler()
