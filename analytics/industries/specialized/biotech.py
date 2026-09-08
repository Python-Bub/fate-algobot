"""Biotechnology specialized pipeline — R&D burn vs cash runway; binary trial outcomes; low SPY correlation."""

from __future__ import annotations

import numpy as np

from analytics.industries.specialized.base import SpecializedLogic


class BiotechSpecialized(SpecializedLogic):
    INDUSTRY_ID = 'biotech'
    INDUSTRY_NAME = 'Biotechnology'
    ETF_PROXY = 'IBB'
    COMOVEMENT_MODE = 'event_driven'
    RATE_SENSITIVITY = -0.1
    EXPANSION_BETA = 0.3
    NASDAQ_BETA = 1.1
    DEFENSIVE_SCORE = 0.0
    INTRA_CORR = 0.88

    LEADER_TICKERS = (
        'AMGN', 'GILD', 'VRTX', 'REGN', 'BIIB', 'MRNA'
    )

    def apply_macro_gates(self, ctx, handler, res):
        vix = self._macro(ctx, handler, "vix", 20.0)
        ndx = self._macro(ctx, handler, "nasdaq_ret_5d")
        if vix > 30:
            res.score_delta -= 0.02
            res.pipeline_notes.append("event_vix_elevated")
        if ndx < -0.04:
            res.warn_long = True
            res.score_delta -= 0.04 * 1.10
        return None

    def apply_news_gates(self, ctx, handler, res):
        if not ctx.news_headlines:
            return None
        ns = handler.score_news(ctx.news_headlines)
        text = " ".join(ctx.news_headlines).lower()
        if ns.bearish_score >= 0.20 and ("clinical hold" in text or "trial halted" in text or "failed endpoint" in text or "clinical hold" in text or "trial failure" in text or "fda rejection" in text or "safety concern" in text):
            res.block_long = True
            res.block_reason = "biotech: adverse event headline"
            res.pipeline_notes.append("event_bear_block")
        if ns.bullish_score >= 0.18 and ("fda approves" in text or "topline positive" in text or "accelerated approval" in text or "phase 3 success" in text or "fda approval" in text or "breakthrough therapy" in text or "trial met primary" in text):
            res.score_delta += 0.14
            res.p_up_delta += 0.05
            res.pipeline_notes.append("event_bull_boost")
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
        leaders = ('AMGN', 'GILD', 'VRTX',)
        if sym in leaders:
            score += 0.025
        if comove.short_sympathy:
            score -= 0.04
        return float(score)

    def feature_weights(self, ctx, handler):
        base = super().feature_weights(ctx, handler)
        base.update({
            "fpw_news_sent": 1.35, "fpw_industry_sympathy": 0.65,
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
        if res.block_long:
            res.max_hold_mult = min(res.max_hold_mult, 0.5)
            res.position_cap_mult = min(res.position_cap_mult, 0.6)
        elif res.warn_long:
            res.max_hold_mult = min(res.max_hold_mult, 0.65)
        return None


LOGIC = BiotechSpecialized()
