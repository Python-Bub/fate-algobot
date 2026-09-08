"""Semiconductor Equipment specialized pipeline — Multi-year boom/bust; moves on fab capex headlines."""

from __future__ import annotations

import numpy as np

from analytics.industries.specialized.base import SpecializedLogic


class SemiEquipmentSpecialized(SpecializedLogic):
    INDUSTRY_ID = 'semi_equipment'
    INDUSTRY_NAME = 'Semiconductor Equipment'
    ETF_PROXY = 'SMH'
    COMOVEMENT_MODE = 'follow_nasdaq'
    RATE_SENSITIVITY = 0.0
    EXPANSION_BETA = 1.3
    NASDAQ_BETA = 1.4
    DEFENSIVE_SCORE = 0.0
    INTRA_CORR = 0.92

    LEADER_TICKERS = (
        'ASML', 'LRCX', 'AMAT', 'KLAC', 'TER', 'ONTO'
    )

    def apply_macro_gates(self, ctx, handler, res):
        ndx = self._macro(ctx, handler, "nasdaq_ret_5d")
        pmi = self._macro(ctx, handler, "pmi_score")
        if ndx < -0.035:
            res.warn_long = True
            res.score_delta -= 0.06 * 1.40
            res.macro_gates.append("ndx_drawdown")
        elif ndx > 0.025:
            res.score_delta += 0.05 * 1.40
            res.p_up_delta += 0.02 * 1.40
        if pmi > 0.5:
            res.score_delta += 1.30 * pmi * 0.04
        return None

    def apply_news_gates(self, ctx, handler, res):
        if not ctx.news_headlines:
            return None
        ns = handler.score_news(ctx.news_headlines)
        text = " ".join(ctx.news_headlines).lower()
        if ns.bearish_score >= 0.32 and ("fab pause" in text or "capex cut" in text or "order cancel" in text):
            res.warn_long = True
            res.score_delta -= 0.05
        if ns.bullish_score >= 0.25 and ("fab build" in text or "capex raise" in text or "chips act" in text or "order backlog" in text):
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
        leaders = ('ASML', 'LRCX', 'AMAT',)
        if sym in leaders:
            score += 0.025
        if comove.short_sympathy:
            score -= 0.04
        return float(score)

    def feature_weights(self, ctx, handler):
        base = super().feature_weights(ctx, handler)
        base.update({
            "fpw_nasdaq_beta": 1.0 + 1.40 * 0.12, "fpw_industry_leader_momentum": 1.25,
            "fpw_intra_corr": 0.92,
        })
        tilts = handler.compute_factor_tilts(ctx)
        base["fpw_combined_tilt"] = 1.0 + abs(tilts.combined) * 0.08
        return base

    def family_bias(self, ctx, handler):
        ndx = self._macro(ctx, handler, "nasdaq_ret_5d")
        bias = super().family_bias(ctx, handler)
        bias += float(np.tanh(ndx * 8.0)) * 1.30 * 0.08
        return float(np.clip(bias, -0.25, 0.25))

    def risk_adjust(self, ctx, handler, res):
        super().risk_adjust(ctx, handler, res)
        return None


LOGIC = SemiEquipmentSpecialized()
