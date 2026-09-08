"""Packaged Foods specialized pipeline — Food commodity inputs; GLP-1 headwind theme."""

from __future__ import annotations

import numpy as np

from analytics.industries.specialized.base import SpecializedLogic


class PackagedFoodsSpecialized(SpecializedLogic):
    INDUSTRY_ID = 'packaged_foods'
    INDUSTRY_NAME = 'Packaged Foods'
    ETF_PROXY = 'XLP'
    COMOVEMENT_MODE = 'defensive'
    RATE_SENSITIVITY = 0.0
    EXPANSION_BETA = 0.1
    NASDAQ_BETA = 0.35
    DEFENSIVE_SCORE = 0.8
    INTRA_CORR = 0.77

    LEADER_TICKERS = (
        'KO', 'PEP', 'GIS', 'K', 'HSY', 'MDLZ', 'KHC'
    )

    def apply_macro_gates(self, ctx, handler, res):
        vix = self._macro(ctx, handler, "vix", 20.0)
        macro = self._macro(ctx, handler, "macro_score")
        pmi = self._macro(ctx, handler, "pmi_score")
        if vix > 22:
            boost = 0.80 * float(np.tanh((vix - 22) / 10))
            res.score_delta += boost * 0.08
            res.family_bias += boost * 0.06
            res.macro_gates.append("defensive_vix_bid")
        if pmi > 0.6 and vix < 18:
            res.score_delta -= 0.03 * 0.80
            res.pipeline_notes.append("defensive_late_cycle_penalty")
        if macro < -0.35:
            res.score_delta += 0.04 * 0.80
        return None

    def apply_news_gates(self, ctx, handler, res):
        if not ctx.news_headlines:
            return None
        ns = handler.score_news(ctx.news_headlines)
        text = " ".join(ctx.news_headlines).lower()
        if ns.bearish_score >= 0.32 and ("glut" in text or "grain cost" in text or "trade down private label" in text or "obesity drug" in text):
            res.warn_long = True
            res.score_delta -= 0.05
        if ns.bullish_score >= 0.25 and ("pricing" in text or "volume return" in text or "snacking trend" in text or "distribution gain" in text):
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
        leaders = ('KO', 'PEP', 'GIS',)
        if sym in leaders:
            score += 0.025
        if comove.short_sympathy:
            score -= 0.04
        return float(score)

    def feature_weights(self, ctx, handler):
        base = super().feature_weights(ctx, handler)
        base.update({
            "fpw_vix_sensitivity": 1.30, "fpw_industry_sympathy": 0.80,
            "fpw_intra_corr": 0.77,
        })
        tilts = handler.compute_factor_tilts(ctx)
        base["fpw_combined_tilt"] = 1.0 + abs(tilts.combined) * 0.08
        return base

    def family_bias(self, ctx, handler):
        vix = self._macro(ctx, handler, "vix", 20.0)
        bias = super().family_bias(ctx, handler)
        if vix > 24:
            bias += 0.80 * 0.12
        return float(np.clip(bias, -0.25, 0.25))

    def risk_adjust(self, ctx, handler, res):
        super().risk_adjust(ctx, handler, res)
        return None


LOGIC = PackagedFoodsSpecialized()
