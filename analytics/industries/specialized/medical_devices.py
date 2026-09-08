"""Medical Devices specialized pipeline — Gross margin >60%; elective surgery volume driver."""

from __future__ import annotations

import numpy as np

from analytics.industries.specialized.base import SpecializedLogic


class MedicalDevicesSpecialized(SpecializedLogic):
    INDUSTRY_ID = 'medical_devices'
    INDUSTRY_NAME = 'Medical Devices'
    ETF_PROXY = 'IHI'
    COMOVEMENT_MODE = 'hybrid'
    RATE_SENSITIVITY = 0.0
    EXPANSION_BETA = 0.5
    NASDAQ_BETA = 0.8
    DEFENSIVE_SCORE = 0.35
    INTRA_CORR = 0.78

    LEADER_TICKERS = (
        'MDT', 'ABT', 'ISRG', 'SYK', 'BSX', 'EW', 'ZBH'
    )

    def apply_macro_gates(self, ctx, handler, res):
        shock = self._macro(ctx, handler, "rate_shock_20d")
        pmi = self._macro(ctx, handler, "pmi_score")
        ndx = self._macro(ctx, handler, "nasdaq_ret_5d")
        if abs(0.00) > 0.25 and shock > 0.15:
            res.score_delta += shock * 0.00 * -0.12
            if shock > 0.22:
                res.warn_long = True
        if pmi > 0.4:
            res.score_delta += pmi * 0.50 * 0.05
        if ndx < -0.03:
            res.score_delta += ndx * 0.80 * 0.08
        return None

    def apply_news_gates(self, ctx, handler, res):
        if not ctx.news_headlines:
            return None
        ns = handler.score_news(ctx.news_headlines)
        text = " ".join(ctx.news_headlines).lower()
        if ns.bearish_score >= 0.32 and ("hospital budget cut" in text or "recall" in text or "reimbursement cut" in text or "elective delay" in text):
            res.warn_long = True
            res.score_delta -= 0.05
        if ns.bullish_score >= 0.25 and ("procedure volume" in text or "hospital capex" in text or "robotics adoption" in text or "guidance raise" in text):
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
        leaders = ('MDT', 'ABT', 'ISRG',)
        if sym in leaders:
            score += 0.025
        if comove.short_sympathy:
            score -= 0.04
        return float(score)

    def feature_weights(self, ctx, handler):
        base = super().feature_weights(ctx, handler)
        base.update({
            "fpw_factor_expansion": 1.0 + 0.50 * 0.10,
            "fpw_intra_corr": 0.78,
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


LOGIC = MedicalDevicesSpecialized()
