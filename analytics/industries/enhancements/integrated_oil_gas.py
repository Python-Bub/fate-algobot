"""
Integrated Oil & Gas — comprehensive industry enhancement module.

Industry notes: Lockstep with WTI/Brent futures.

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


class IntegratedOilGasEnhancement(IndustryEnhancement):
    INDUSTRY_ID = 'integrated_oil_gas'
    INDUSTRY_NAME = 'Integrated Oil & Gas'
    ETF_PROXY = 'XLE'
    COMOVEMENT_MODE = 'commodity'
    RATE_SENSITIVITY = 0.2
    EXPANSION_BETA = 0.6
    NASDAQ_BETA = 0.7
    DEFENSIVE_SCORE = 0.1
    INTRA_CORR = 0.93
    INDUSTRY_NOTES = 'Lockstep with WTI/Brent futures.'

    LEADER_TICKERS = (
        'XOM',
        'CVX',
        'SHEL',
        'TTE',
        'BP',
        'COP'
    )
    NEWS_BULL = (
        'opec cut',
        'crude rally',
        'refining margin',
        'buyback'
    )
    NEWS_EVENT_BULL = (
        'opec+',
        'supply cut'
    )
    COMMODITY_KEYS = (
        'wti',
        'brent',
        'crude',
        'opec'
    )

    IMPLEMENTED_FEATURES = ENHANCEMENT_FEATURES

    def macro_tailwind_score(self, res, ctx, handler):
        pmi = self._macro(ctx, handler, "pmi_score")
        if pmi > 0.3:
            self._boost(res, pmi * 0.60 * 0.10, "enh:commodity_tailwind")
    def macro_regime_alignment(self, res, ctx, handler):
        pmi = self._macro(ctx, handler, "pmi_score")
        macro = self._macro(ctx, handler, "macro_score")
        if pmi > 0.35:
            self._boost(res, pmi * 0.60 * 0.08, "enh:commodity_demand_regime")
        if macro > 0.2:
            self._boost(res, macro * 0.05, "enh:commodity_macro")
    def news_bull_accelerator(self, res, ctx, handler):
        if not ctx.news_headlines:
            return None
        text = " ".join(ctx.news_headlines).lower()
        ns = handler.score_news(ctx.news_headlines)
        if ns.bullish_score >= 0.08 or ("opec cut" in text or "crude rally" in text or "refining margin" in text or "buyback" in text):
            boost = max(ns.bullish_score, 0.15) * 0.12
            self._boost(res, boost, "enh:integrated_oil_gas_bull_lexicon")
            self._boost_p_up(res, boost * 0.3)
            res.family_bias += 0.03
    def news_event_catalyst(self, res, ctx, handler):
        if not ctx.news_headlines:
            return None
        text = " ".join(ctx.news_headlines).lower()
        if "opec+" in text or "supply cut" in text:
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
            self._boost(res, comove.sympathy_score * 0.93 * 0.12, "enh:sympathy_follow")
        if comove.leader_momentum > 0.01:
            self._boost(res, comove.leader_momentum * 0.60 * 0.15, "enh:leader_momentum")
    def residual_reversion_edge(self, res, ctx, handler):
        residual = float(ctx.row_features.get("industry_residual_1d", 0.0))
        if residual < -0.01:
            self._boost(res, float(__import__('numpy').tanh(-residual * 35)) * 0.93 * 0.05, "enh:mean_revert")
    def family_horizon_bias(self, res, ctx, handler):
        res.family_bias += 0.04
        tilts = handler.compute_factor_tilts(ctx)
        if tilts.combined > 0:
            res.family_bias += float(__import__('numpy').tanh(tilts.combined)) * 0.04
    def ml_feature_weight_matrix(self, res, ctx, handler):
        super().ml_feature_weight_matrix(res, ctx, handler)
        self._add_fpw(res, "fpw_integrated_oil_gas_alpha", 1.12)
        self._add_fpw(res, "fpw_intra_corr", 0.93)
        self._add_fpw(res, "fpw_commodity_proxy", 1.50)
        self._add_fpw(res, "fpw_factor_expansion", 1.25)
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
        if self.COMOVEMENT_MODE == 'commodity':
            self._boost(res, 0.025, "enh:mode_identity:integrated_oil_gas")
    def factor_expansion_emphasis(self, res, ctx, handler):
        tilts = handler.compute_factor_tilts(ctx)
        if tilts.expansion_tilt > 0:
            self._boost(res, tilts.expansion_tilt * 0.60 * 0.07, "enh:expansion_factor")
            self._add_fpw(res, "fpw_factor_expansion", 1.0 + 0.60 * 0.18)
    def factor_commodity_emphasis(self, res, ctx, handler):
        tilts = handler.compute_factor_tilts(ctx)
        if tilts.commodity_tilt > 0:
            self._boost(res, tilts.commodity_tilt * 0.60 * 0.10, "enh:commodity_factor")
    def industry_alpha_suite(self, res, ctx, handler):
        """Apply Integrated Oil & Gas-specific alpha signals from notes: Lockstep with WTI/Brent futures.."""
        sym = ctx.symbol.upper()
        leaders = ('XOM', 'CVX', 'SHEL', 'TTE', 'BP', 'COP')
        bull_phrases = ('opec cut', 'crude rally', 'refining margin', 'buyback')
        commodity_keys = ('wti', 'brent', 'crude', 'opec')
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
                self._boost(res, min(0.20, bull_hits * 0.05), "enh:integrated_oil_gas_phrase_hits")
            comm_hits = sum(1 for k in commodity_keys if k in text)
            if comm_hits:
                self._boost(res, min(0.12, comm_hits * 0.04), "enh:integrated_oil_gas_commodity_news")
        pmi = self._macro(ctx, handler, "pmi_score")
        if pmi > 0.35:
            self._boost(res, pmi * 0.60 * 0.12, "enh:integrated_oil_gas_commodity_cycle")
            self._add_fpw(res, "fpw_cycle_beta", 1.24)
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


ENHANCEMENT = IntegratedOilGasEnhancement()
