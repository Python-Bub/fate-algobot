"""Electric & Gas Utilities specialized pipeline — Bond proxy; drops when yields rise."""

from __future__ import annotations

import numpy as np

from analytics.industries.specialized.base import SpecializedLogic


class ElectricGasUtilitiesSpecialized(SpecializedLogic):
    INDUSTRY_ID = 'electric_gas_utilities'
    INDUSTRY_NAME = 'Electric & Gas Utilities'
    ETF_PROXY = 'XLU'
    COMOVEMENT_MODE = 'inverse_rates'
    RATE_SENSITIVITY = -0.65
    EXPANSION_BETA = 0.2
    NASDAQ_BETA = 0.3
    DEFENSIVE_SCORE = 0.75
    INTRA_CORR = 0.88

    LEADER_TICKERS = (
        'NEE', 'DUK', 'SO', 'D', 'AEP', 'EXC', 'SRE'
    )

    def apply_macro_gates(self, ctx, handler, res):
        shock = self._macro(ctx, handler, "rate_shock_20d")
        spread = self._macro(ctx, handler, "spread_10y2y")
        vix = self._macro(ctx, handler, "vix", 20.0)
        rate_thr = 0.165
        if shock > rate_thr or spread < -0.35:
            res.block_long = True
            res.block_reason = "electric_gas_utilities: rising rates / inverted curve headwind"
            res.macro_gates.append("rate_headwind_block")
            res.pipeline_notes.append(f"rate_shock={shock:.2f}")
        elif shock < -0.08:
            boost = 0.65 * 0.09
            res.score_delta += boost
            res.p_up_delta += boost * 0.35
            res.macro_gates.append("rate_relief")
        if vix > 28 and shock > 0.05:
            res.warn_long = True
            res.score_delta -= 0.03
        return None

    def apply_news_gates(self, ctx, handler, res):
        if not ctx.news_headlines:
            return None
        ns = handler.score_news(ctx.news_headlines)
        text = " ".join(ctx.news_headlines).lower()
        if ns.bearish_score >= 0.35 and ("rate case loss" in text or "wildfire liability" in text or "yield competition" in text):
            res.warn_long = True
            res.score_delta -= 0.06
            res.pipeline_notes.append("sector_bear_warn")
        if ns.bullish_score >= 0.28 and ("allowed roe" in text or "rate case win" in text or "load growth" in text or "data center power" in text):
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
        leaders = ('NEE', 'DUK', 'SO',)
        if sym in leaders:
            score += 0.025
        if comove.short_sympathy:
            score -= 0.04
        return float(score)

    def feature_weights(self, ctx, handler):
        base = super().feature_weights(ctx, handler)
        base.update({
            "fpw_factor_rate": 1.0 + 0.65 * 0.35, "fpw_industry_beta": 1.15,
            "fpw_intra_corr": 0.88,
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
        shock = self._macro(ctx, handler, "rate_shock_20d")
        if shock > 0.18:
            res.max_hold_mult = min(res.max_hold_mult, 0.7)
        return None


LOGIC = ElectricGasUtilitiesSpecialized()
