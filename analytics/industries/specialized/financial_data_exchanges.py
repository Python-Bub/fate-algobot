"""Financial Data & Exchanges specialized pipeline — ADV and VIX drive exchange revenues."""

from __future__ import annotations

import numpy as np

from analytics.industries.specialized.base import SpecializedLogic


class FinancialDataExchangesSpecialized(SpecializedLogic):
    INDUSTRY_ID = 'financial_data_exchanges'
    INDUSTRY_NAME = 'Financial Data & Exchanges'
    ETF_PROXY = 'XLF'
    COMOVEMENT_MODE = 'follow_market'
    RATE_SENSITIVITY = 0.3
    EXPANSION_BETA = 0.9
    NASDAQ_BETA = 1.0
    DEFENSIVE_SCORE = 0.15
    INTRA_CORR = 0.86

    LEADER_TICKERS = (
        'SPGI', 'ICE', 'CME', 'MCO', 'MSCI', 'NDAQ', 'COIN'
    )

    def apply_macro_gates(self, ctx, handler, res):
        macro = self._macro(ctx, handler, "macro_score")
        spread = self._macro(ctx, handler, "spread_10y2y")
        if macro > 0.25:
            res.score_delta += macro * 0.06 * 0.90
        if spread < -0.3:
            res.warn_long = True
            res.score_delta -= 0.04
        return None

    def apply_news_gates(self, ctx, handler, res):
        if not ctx.news_headlines:
            return None
        ns = handler.score_news(ctx.news_headlines)
        text = " ".join(ctx.news_headlines).lower()
        if ns.bearish_score >= 0.32 and ("volume drought" in text or "fee pressure" in text or "crypto winter" in text):
            res.warn_long = True
            res.score_delta -= 0.05
        if ns.bullish_score >= 0.25 and ("trading volume" in text or "vix elevated" in text or "aum growth" in text or "data subscription" in text):
            res.score_delta += 0.06
            res.p_up_delta += 0.015
        if ns.net > 0.15:
            res.family_bias += 0.04
        elif ns.net < -0.15:
            res.family_bias -= 0.06
        return None

    def pipeline_score(self, ctx, handler):
        score = super().pipeline_score(ctx, handler)
        comove = handler.compute_comovement(
            ctx,
            industry_z=float(ctx.row_features.get("industry_z_20", 0.0)),
            residual=float(ctx.row_features.get("industry_residual_1d", 0.0)),
        )
        score += comove.sympathy_score * 0.08
        sym = ctx.symbol.upper()
        leaders = ('SPGI', 'ICE', 'CME',)
        if sym in leaders:
            score += 0.025
        if comove.short_sympathy:
            score -= 0.04
        return float(score)

    def feature_weights(self, ctx, handler):
        base = super().feature_weights(ctx, handler)
        base.update({
            "fpw_factor_expansion": 1.0 + 0.90 * 0.10,
            "fpw_intra_corr": 0.86,
        })
        tilts = handler.compute_factor_tilts(ctx)
        base["fpw_combined_tilt"] = 1.0 + abs(tilts.combined) * 0.08
        return base

    def family_bias(self, ctx, handler):
        bias = super().family_bias(ctx, handler)
        tilts = handler.compute_factor_tilts(ctx)
        bias += float(np.tanh(tilts.combined)) * 0.05
        return float(np.clip(bias, -0.25, 0.25))

    def risk_adjust(self, ctx, handler, res):
        super().risk_adjust(ctx, handler, res)
        return None


LOGIC = FinancialDataExchangesSpecialized()
