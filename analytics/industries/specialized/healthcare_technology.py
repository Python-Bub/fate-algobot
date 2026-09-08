"""Healthcare Technology specialized pipeline — LTV/CAC; privacy regulation hits entire group."""

from __future__ import annotations

import numpy as np

from analytics.industries.specialized.base import SpecializedLogic


class HealthcareTechnologySpecialized(SpecializedLogic):
    INDUSTRY_ID = 'healthcare_technology'
    INDUSTRY_NAME = 'Healthcare Technology'
    ETF_PROXY = 'XLV'
    COMOVEMENT_MODE = 'follow_nasdaq'
    RATE_SENSITIVITY = 0.2
    EXPANSION_BETA = 0.9
    NASDAQ_BETA = 1.2
    DEFENSIVE_SCORE = 0.05
    INTRA_CORR = 0.8

    LEADER_TICKERS = (
        'VEEV', 'TDOC', 'HIMS', 'DOCS', 'CERN', 'MDRX'
    )

    def apply_macro_gates(self, ctx, handler, res):
        ndx = self._macro(ctx, handler, "nasdaq_ret_5d")
        pmi = self._macro(ctx, handler, "pmi_score")
        if ndx < -0.035:
            res.warn_long = True
            res.score_delta -= 0.06 * 1.20
            res.macro_gates.append("ndx_drawdown")
        elif ndx > 0.025:
            res.score_delta += 0.05 * 1.20
            res.p_up_delta += 0.02 * 1.20
        if pmi > 0.5:
            res.score_delta += 0.90 * pmi * 0.04
        return None

    def apply_news_gates(self, ctx, handler, res):
        if not ctx.news_headlines:
            return None
        ns = handler.score_news(ctx.news_headlines)
        text = " ".join(ctx.news_headlines).lower()
        if ns.bearish_score >= 0.32 and ("security breach" in text or "privacy fine" in text or "churn" in text or "telehealth cut" in text):
            res.warn_long = True
            res.score_delta -= 0.05
        if ns.bullish_score >= 0.25 and ("contract win" in text or "hospital go-live" in text or "saas growth" in text or "ARR beat" in text):
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
        leaders = ('VEEV', 'TDOC', 'HIMS',)
        if sym in leaders:
            score += 0.025
        if comove.short_sympathy:
            score -= 0.04
        return float(score)

    def feature_weights(self, ctx, handler):
        base = super().feature_weights(ctx, handler)
        base.update({
            "fpw_nasdaq_beta": 1.0 + 1.20 * 0.12, "fpw_industry_leader_momentum": 1.25,
            "fpw_intra_corr": 0.80,
        })
        tilts = handler.compute_factor_tilts(ctx)
        base["fpw_combined_tilt"] = 1.0 + abs(tilts.combined) * 0.08
        return base

    def family_bias(self, ctx, handler):
        ndx = self._macro(ctx, handler, "nasdaq_ret_5d")
        bias = super().family_bias(ctx, handler)
        bias += float(np.tanh(ndx * 8.0)) * 0.90 * 0.08
        return float(np.clip(bias, -0.25, 0.25))

    def risk_adjust(self, ctx, handler, res):
        super().risk_adjust(ctx, handler, res)
        return None


LOGIC = HealthcareTechnologySpecialized()
