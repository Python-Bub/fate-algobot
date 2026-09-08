"""Interactive Media specialized pipeline — ARPU/DAU; digital ad budget cycle."""

from __future__ import annotations

import numpy as np

from analytics.industries.specialized.base import SpecializedLogic


class InteractiveMediaSpecialized(SpecializedLogic):
    INDUSTRY_ID = 'interactive_media'
    INDUSTRY_NAME = 'Interactive Media'
    ETF_PROXY = 'XLC'
    COMOVEMENT_MODE = 'follow_nasdaq'
    RATE_SENSITIVITY = 0.15
    EXPANSION_BETA = 1.0
    NASDAQ_BETA = 1.4
    DEFENSIVE_SCORE = 0.0
    INTRA_CORR = 0.86

    LEADER_TICKERS = (
        'META', 'GOOGL', 'GOOG', 'SNAP', 'PINS', 'RDDT'
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
            res.score_delta += 1.00 * pmi * 0.04
        return None

    def apply_news_gates(self, ctx, handler, res):
        if not ctx.news_headlines:
            return None
        ns = handler.score_news(ctx.news_headlines)
        text = " ".join(ctx.news_headlines).lower()
        if ns.bearish_score >= 0.32 and ("ad recession" in text or "att opt out" in text or "antitrust" in text or "tiktok competition" in text):
            res.warn_long = True
            res.score_delta -= 0.05
        if ns.bullish_score >= 0.25 and ("ad spend" in text or "dau growth" in text or "reels monetization" in text or "ai search" in text):
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
        leaders = ('META', 'GOOGL', 'GOOG',)
        if sym in leaders:
            score += 0.025
        if comove.short_sympathy:
            score -= 0.04
        return float(score)

    def feature_weights(self, ctx, handler):
        base = super().feature_weights(ctx, handler)
        base.update({
            "fpw_nasdaq_beta": 1.0 + 1.40 * 0.12, "fpw_industry_leader_momentum": 1.25,
            "fpw_intra_corr": 0.86,
        })
        tilts = handler.compute_factor_tilts(ctx)
        base["fpw_combined_tilt"] = 1.0 + abs(tilts.combined) * 0.08
        return base

    def family_bias(self, ctx, handler):
        ndx = self._macro(ctx, handler, "nasdaq_ret_5d")
        bias = super().family_bias(ctx, handler)
        bias += float(np.tanh(ndx * 8.0)) * 1.00 * 0.08
        return float(np.clip(bias, -0.25, 0.25))

    def risk_adjust(self, ctx, handler, res):
        super().risk_adjust(ctx, handler, res)
        return None


LOGIC = InteractiveMediaSpecialized()
