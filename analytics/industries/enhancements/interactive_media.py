"""
Interactive Media — comprehensive industry enhancement module.

Industry notes: ARPU/DAU; digital ad budget cycle.

ALL SPECIALIZED FEATURES IMPLEMENTED (25):
     1. macro_tailwind_score
     2. macro_regime_alignment
     3. news_bull_accelerator
     4. news_event_catalyst
     5. sympathy_leader_follow
     6. sympathy_cluster_alpha
     7. residual_reversion_edge
     8. factor_rate_emphasis
     9. factor_expansion_emphasis
    10. factor_nasdaq_emphasis
    11. factor_defensive_emphasis
    12. factor_commodity_emphasis
    13. ml_feature_weight_matrix
    14. family_horizon_bias
    15. p_up_probability_lift
    16. playbook_amplification
    17. etf_proxy_momentum
    18. leader_ticker_premium
    19. row_feature_affinity
    20. risk_capacity_expand
    21. comovement_mode_bonus
    22. intra_correlation_boost
    23. headline_commodity_tag_boost
    24. market_cap_tier_boost
    25. confidence_blend_boost

Philosophy: enhancement-only — boosts scores, p_up, family bias, ML weights;
expands risk capacity on strength. Never reduces score except via super() guard.
"""

from __future__ import annotations

import numpy as np

from analytics.industries.enhancements._base import IndustryEnhancement, ENHANCEMENT_FEATURES


class InteractiveMediaEnhancement(IndustryEnhancement):
    INDUSTRY_ID = 'interactive_media'
    INDUSTRY_NAME = 'Interactive Media'
    ETF_PROXY = 'XLC'
    COMOVEMENT_MODE = 'follow_nasdaq'
    RATE_SENSITIVITY = 0.15
    EXPANSION_BETA = 1.0
    NASDAQ_BETA = 1.4
    DEFENSIVE_SCORE = 0.0
    INTRA_CORR = 0.86
    INDUSTRY_NOTES = 'ARPU/DAU; digital ad budget cycle.'

    LEADER_TICKERS = (
        'META',
        'GOOGL',
        'GOOG',
        'SNAP',
        'PINS',
        'RDDT'
    )
    NEWS_BULL = (
        'ad spend',
        'dau growth',
        'reels monetization',
        'ai search'
    )
    NEWS_EVENT_BULL = (
        'ad beat',
        'engagement record'
    )
    COMMODITY_KEYS = (
        'advertising',
        'pixel',
        'dau'
    )

    IMPLEMENTED_FEATURES = ENHANCEMENT_FEATURES

    def macro_tailwind_score(self, res, ctx, handler):
        ndx = self._macro(ctx, handler, "nasdaq_ret_5d")
        if ndx > 0:
            self._boost(res, ndx * 1.40 * 0.18, "enh:ndx_tailwind")
    def macro_regime_alignment(self, res, ctx, handler):
        ndx = self._macro(ctx, handler, "nasdaq_ret_5d")
        pmi = self._macro(ctx, handler, "pmi_score")
        if ndx > 0.015:
            self._boost(res, ndx * 1.40 * 0.15, "enh:nasdaq_regime")
        if pmi > 0.45:
            self._boost(res, pmi * 1.00 * 0.06, "enh:pmi_regime")
    def news_bull_accelerator(self, res, ctx, handler):
        if not ctx.news_headlines:
            return None
        text = " ".join(ctx.news_headlines).lower()
        ns = handler.score_news(ctx.news_headlines)
        if ns.bullish_score >= 0.08 or ("ad spend" in text or "dau growth" in text or "reels monetization" in text or "ai search" in text):
            boost = max(ns.bullish_score, 0.15) * 0.12
            self._boost(res, boost, "enh:interactive_media_bull_lexicon")
            self._boost_p_up(res, boost * 0.3)
            res.family_bias += 0.03
    def news_event_catalyst(self, res, ctx, handler):
        if not ctx.news_headlines:
            return None
        text = " ".join(ctx.news_headlines).lower()
        if "ad beat" in text or "engagement record" in text:
            self._boost(res, 0.16, "enh:sector_event_bull")
            self._boost_p_up(res, 0.05)
            self._expand_risk(res, hold=1.12, cap=1.06)
    def sympathy_leader_follow(self, res, ctx, handler):
        comove = handler.compute_comovement(
            ctx,
            industry_z=float(ctx.row_features.get("industry_z_20", 0.0)),
            residual=float(ctx.row_features.get("industry_residual_1d", 0.0)),
        )
        if comove.sympathy_score > 0:
            self._boost(res, comove.sympathy_score * 0.86 * 0.12, "enh:sympathy_follow")
        if comove.leader_momentum > 0.01:
            self._boost(res, comove.leader_momentum * 1.00 * 0.15, "enh:leader_momentum")
    def residual_reversion_edge(self, res, ctx, handler):
        residual = float(ctx.row_features.get("industry_residual_1d", 0.0))
        if residual < -0.01:
            self._boost(res, float(__import__('numpy').tanh(-residual * 35)) * 0.86 * 0.05, "enh:mean_revert")
    def family_horizon_bias(self, res, ctx, handler):
        ndx = self._macro(ctx, handler, "nasdaq_ret_5d")
        res.family_bias += 0.03
        res.family_bias += float(__import__("numpy").tanh(ndx * 6)) * 1.00 * 0.06
    def ml_feature_weight_matrix(self, res, ctx, handler):
        super().ml_feature_weight_matrix(res, ctx, handler)
        self._add_fpw(res, "fpw_interactive_media_alpha", 1.12)
        self._add_fpw(res, "fpw_intra_corr", 0.86)
        self._add_fpw(res, "fpw_nasdaq_beta", 1.0 + 1.40 * 0.15)
        self._add_fpw(res, "fpw_industry_leader_momentum", 1.35)
    def playbook_amplification(self, res, ctx, handler):
        from analytics.industries.macro_playbooks import apply_playbook, infer_events_from_headlines
        events = infer_events_from_headlines(ctx.news_headlines or [], self.INDUSTRY_ID)
        for ev in events:
            hit = apply_playbook(self.INDUSTRY_ID, ev)
            if hit.get('applied') and float(hit.get('combined_delta') or 0) > 0:
                self._boost(res, float(hit['combined_delta']) * 0.15, f"enh:playbook:{ev}")
        super().playbook_amplification(res, ctx, handler)
    def comovement_mode_bonus(self, res, ctx, handler):
        super().comovement_mode_bonus(res, ctx, handler)
        if self.COMOVEMENT_MODE == 'follow_nasdaq':
            self._boost(res, 0.025, "enh:mode_identity:interactive_media")
    def factor_expansion_emphasis(self, res, ctx, handler):
        tilts = handler.compute_factor_tilts(ctx)
        if tilts.expansion_tilt > 0:
            self._boost(res, tilts.expansion_tilt * 1.00 * 0.07, "enh:expansion_factor")
            self._add_fpw(res, "fpw_factor_expansion", 1.0 + 1.00 * 0.18)
    def factor_nasdaq_emphasis(self, res, ctx, handler):
        tilts = handler.compute_factor_tilts(ctx)
        if tilts.nasdaq_tilt > 0:
            self._boost(res, tilts.nasdaq_tilt * 1.40 * 0.06, "enh:nasdaq_factor")
    def industry_alpha_suite(self, res, ctx, handler):
        """Apply Interactive Media-specific alpha signals from notes: ARPU/DAU; digital ad budget cycle.."""
        sym = ctx.symbol.upper()
        leaders = ('META', 'GOOGL', 'GOOG', 'SNAP', 'PINS', 'RDDT')
        bull_phrases = ('ad spend', 'dau growth', 'reels monetization', 'ai search')
        commodity_keys = ('advertising', 'pixel', 'dau')
        tilts = handler.compute_factor_tilts(ctx)
        if tilts.combined > 0:
            self._boost(res, float(__import__("numpy").tanh(tilts.combined)) * 0.06, "enh:combined_tilt")
        if sym in leaders:
            self._boost(res, 0.04, "enh:sector_leader")
            self._add_fpw(res, "fpw_leader_alpha", 1.20)
        if ctx.news_headlines:
            text = ' '.join(ctx.news_headlines).lower()
            bull_hits = sum(1 for p in bull_phrases if p in text)
            if bull_hits:
                self._boost(res, min(0.20, bull_hits * 0.05), "enh:interactive_media_phrase_hits")
            comm_hits = sum(1 for k in commodity_keys if k in text)
            if comm_hits:
                self._boost(res, min(0.12, comm_hits * 0.04), "enh:interactive_media_commodity_news")
        ndx = self._macro(ctx, handler, "nasdaq_ret_5d")
        if ndx > 0.01:
            self._boost(res, ndx * 1.40 * 0.20, "enh:interactive_media_ndx_alpha")
            self._add_fpw(res, "fpw_growth_beta", 1.22)
        ret1 = float(ctx.row_features.get("industry_ret_1d", 0.0))
        if ret1 > 0.005:
            self._boost(res, float(__import__("numpy").tanh(ret1 * 30)) * 0.04, "enh:industry_momentum_1d")
        z = float(ctx.row_features.get("industry_z_20", 0.0))
        if 0.3 < z < 2.5:
            self._boost(res, z * 0.02, "enh:industry_z_sweet")
        if res.score_delta > 0.06:
            self._expand_risk(res, hold=1.05, cap=1.04)
    def enhance(self, res, ctx, handler):
        out = super().enhance(res, ctx, handler)
        before = out.score_delta
        self.industry_alpha_suite(out, ctx, handler)
        if out.score_delta < before:
            out.score_delta = before
        return out


ENHANCEMENT = InteractiveMediaEnhancement()
