"""Consumer Finance specialized pipeline — NCO rate; consumer credit delinquency."""

from __future__ import annotations

import numpy as np

from analytics.industries.specialized.base import SpecializedLogic


class ConsumerFinanceSpecialized(SpecializedLogic):
    INDUSTRY_ID = 'consumer_finance'
    INDUSTRY_NAME = 'Consumer Finance'
    ETF_PROXY = 'XLF'
    COMOVEMENT_MODE = 'hybrid'
    RATE_SENSITIVITY = 0.35
    EXPANSION_BETA = 0.8
    NASDAQ_BETA = 0.95
    DEFENSIVE_SCORE = 0.05
    INTRA_CORR = 0.84

    LEADER_TICKERS = (
        'V', 'MA', 'AXP', 'COF', 'SYF', 'ALLY', 'SOFI'
    )

    def apply_macro_gates(self, ctx, handler, res):
        shock = self._macro(ctx, handler, "rate_shock_20d")
        pmi = self._macro(ctx, handler, "pmi_score")
        ndx = self._macro(ctx, handler, "nasdaq_ret_5d")
        if abs(0.35) > 0.25 and shock > 0.15:
            res.score_delta += shock * 0.35 * -0.12
            if shock > 0.22:
                res.warn_long = True
        if pmi > 0.4:
            res.score_delta += pmi * 0.80 * 0.05
        if ndx < -0.03:
            res.score_delta += ndx * 0.95 * 0.08
        return None

    def apply_news_gates(self, ctx, handler, res):
        if not ctx.news_headlines:
            return None
        ns = handler.score_news(ctx.news_headlines)
        text = " ".join(ctx.news_headlines).lower()
        if ns.bearish_score >= 0.32 and ("charge-off rise" in text or "delinquency spike" in text or "rate cap" in text or "recession fear" in text):
            res.warn_long = True
            res.score_delta -= 0.05
        if ns.bullish_score >= 0.25 and ("spend growth" in text or "delinquency stable" in text or "loan growth" in text):
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
        leaders = ('V', 'MA', 'AXP',)
        if sym in leaders:
            score += 0.025
        if comove.short_sympathy:
            score -= 0.04
        return float(score)

    def feature_weights(self, ctx, handler):
        base = super().feature_weights(ctx, handler)
        base.update({
            "fpw_factor_expansion": 1.0 + 0.80 * 0.10,
            "fpw_intra_corr": 0.84,
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


LOGIC = ConsumerFinanceSpecialized()
