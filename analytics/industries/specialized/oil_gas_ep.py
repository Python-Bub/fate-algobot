"""Oil & Gas E&P specialized pipeline — Amplified oil beta; EIA inventory weekly."""

from __future__ import annotations

import numpy as np

from analytics.industries.specialized.base import SpecializedLogic


class OilGasEpSpecialized(SpecializedLogic):
    INDUSTRY_ID = 'oil_gas_ep'
    INDUSTRY_NAME = 'Oil & Gas E&P'
    ETF_PROXY = 'XOP'
    COMOVEMENT_MODE = 'commodity'
    RATE_SENSITIVITY = 0.1
    EXPANSION_BETA = 0.9
    NASDAQ_BETA = 0.75
    DEFENSIVE_SCORE = 0.0
    INTRA_CORR = 0.94

    LEADER_TICKERS = (
        'EOG', 'PXD', 'DVN', 'FANG', 'MRO', 'OVV', 'APA'
    )

    def apply_macro_gates(self, ctx, handler, res):
        pmi = self._macro(ctx, handler, "pmi_score")
        macro = self._macro(ctx, handler, "macro_score")
        if pmi > 0.45:
            res.score_delta += 0.90 * pmi * 0.05
            res.macro_gates.append("commodity_demand")
        if macro < -0.4:
            res.warn_long = True
            res.score_delta -= 0.05
        text = " ".join(ctx.news_headlines).lower()
        for key in ('natural gas', 'wti', 'rig',):
            if key in text:
                res.pipeline_notes.append(f"commodity_tag:{key}")
        return None

    def apply_news_gates(self, ctx, handler, res):
        if not ctx.news_headlines:
            return None
        ns = handler.score_news(ctx.news_headlines)
        text = " ".join(ctx.news_headlines).lower()
        if ns.bearish_score >= 0.35 and ("gas glut" in text or "basis blowout" in text or "decline curve" in text):
            res.warn_long = True
            res.score_delta -= 0.06
            res.pipeline_notes.append("sector_bear_warn")
        if ns.bullish_score >= 0.28 and ("production beat" in text or "hedge gain" in text or "rig count" in text or "permit" in text):
            res.score_delta += 0.07
            res.p_up_delta += 0.02
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
        leaders = ('EOG', 'PXD', 'DVN',)
        if sym in leaders:
            score += 0.025
        if comove.short_sympathy:
            score -= 0.04
        return float(score)

    def feature_weights(self, ctx, handler):
        base = super().feature_weights(ctx, handler)
        base.update({
            "fpw_factor_expansion": 1.20, "fpw_commodity_proxy": 1.40,
            "fpw_intra_corr": 0.94,
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


LOGIC = OilGasEpSpecialized()
