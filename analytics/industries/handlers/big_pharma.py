"""Big Pharma — Patent cliff timeline; Medicare pricing; low-beta defensive."""

from __future__ import annotations

import numpy as np

from analytics.industries.base import (
    BaseIndustryHandler,
    ComovementMode,
    FactorTiltResult,
    IndustryContext,
    ClassificationResult,
)


class BigPharmaHandler(BaseIndustryHandler):
    INDUSTRY_ID = 'big_pharma'
    INDUSTRY_NAME = 'Big Pharma'
    ETF_PROXY = 'XPH'
    COMOVEMENT_MODE = ComovementMode.DEFENSIVE
    RATE_SENSITIVITY = 0.0
    EXPANSION_BETA = 0.2
    NASDAQ_BETA = 0.6
    DEFENSIVE_SCORE = 0.55
    INTRA_CORR_PRIOR = 0.72

    YAHOO_PATTERNS = (
        'drug manufacturers',
'pharmaceutical',
'big pharma',
'big-pharma',
'big pharma industry'
    )
    TICKER_HINTS = frozenset({
        'LLY', 'JNJ', 'MRK', 'PFE', 'ABBV', 'NVS', 'AZN', 'BMY', 'GSK', 'SNY', 'TAK'
    })
    LEADER_TICKERS = (
        'LLY',
'JNJ',
'MRK',
'PFE',
'ABBV',
'NVS',
'AZN',
'BMY'
    )

    NEWS_BULL = (
        'beats estimates',
'raises guidance',
'patent win',
'formulary inclusion',
'blockbuster'
    )
    NEWS_BEAR = (
        'patent cliff',
'generic entry',
'medicare negotiation',
'fda warning letter',
'recall'
    )
    NEWS_EVENT_BULL = (
        'fda approval',
'label expansion'
    )
    NEWS_EVENT_BEAR = (
        'patent expiry',
'price cap',
'generic launch'
    )
    COMMODITY_KEYS = (
        'prescription',
'formulary',
'patent'
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


HANDLER = BigPharmaHandler()
