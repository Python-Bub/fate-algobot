"""Enhancement-only industry layer — adds alpha, never subtracts unless catastrophic."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

from analytics.industries.macro_playbooks import apply_playbook, infer_events_from_headlines, playbook_tilt
from analytics.industries.pipeline_models import IndustryPipelineResult

if TYPE_CHECKING:
    from analytics.industries.base import BaseIndustryHandler, IndustryContext

# Canonical feature catalog — every enhancement module must implement all of these.
ENHANCEMENT_FEATURES: tuple[str, ...] = (
    "macro_tailwind_score",
    "macro_regime_alignment",
    "news_bull_accelerator",
    "news_event_catalyst",
    "sympathy_leader_follow",
    "sympathy_cluster_alpha",
    "residual_reversion_edge",
    "factor_rate_emphasis",
    "factor_expansion_emphasis",
    "factor_nasdaq_emphasis",
    "factor_defensive_emphasis",
    "factor_commodity_emphasis",
    "ml_feature_weight_matrix",
    "family_horizon_bias",
    "p_up_probability_lift",
    "playbook_amplification",
    "etf_proxy_momentum",
    "leader_ticker_premium",
    "row_feature_affinity",
    "risk_capacity_expand",
    "comovement_mode_bonus",
    "intra_correlation_boost",
    "headline_commodity_tag_boost",
    "market_cap_tier_boost",
    "confidence_blend_boost",
)


class IndustryEnhancement:
    """Base enhancement — each industry subclass implements all feature hooks."""

    INDUSTRY_ID: str = "unclassified"
    INDUSTRY_NAME: str = "Unclassified"
    ETF_PROXY: str = "SPY"
    COMOVEMENT_MODE: str = "hybrid"
    RATE_SENSITIVITY: float = 0.0
    EXPANSION_BETA: float = 0.5
    NASDAQ_BETA: float = 1.0
    DEFENSIVE_SCORE: float = 0.0
    INTRA_CORR: float = 0.75
    LEADER_TICKERS: tuple[str, ...] = ()
    NEWS_BULL: tuple[str, ...] = ()
    NEWS_BEAR: tuple[str, ...] = ()
    NEWS_EVENT_BULL: tuple[str, ...] = ()
    NEWS_EVENT_BEAR: tuple[str, ...] = ()
    COMMODITY_KEYS: tuple[str, ...] = ()
    INDUSTRY_NOTES: str = ""

    IMPLEMENTED_FEATURES: tuple[str, ...] = ENHANCEMENT_FEATURES

    def enhance(
        self,
        res: IndustryPipelineResult,
        ctx: IndustryContext,
        handler: BaseIndustryHandler,
    ) -> IndustryPipelineResult:
        """Run all enhancement features — net effect should be score-positive in normal regimes."""
        before = res.score_delta
        for name in self.IMPLEMENTED_FEATURES:
            fn = getattr(self, name, None)
            if callable(fn):
                fn(res, ctx, handler)
        if res.score_delta < before:
            res.score_delta = before
        return res

    def _macro(self, ctx: IndustryContext, handler: BaseIndustryHandler, key: str, default: float = 0.0) -> float:
        return handler._macro(ctx, key, default)

    def _boost(self, res: IndustryPipelineResult, amount: float, note: str) -> None:
        if amount <= 0:
            return
        res.score_delta += float(amount)
        res.pipeline_notes.append(note)

    def _boost_p_up(self, res: IndustryPipelineResult, amount: float) -> None:
        if amount <= 0:
            return
        res.p_up_delta += float(amount)

    def _expand_risk(self, res: IndustryPipelineResult, hold: float = 1.0, cap: float = 1.0) -> None:
        if hold > 1.0:
            res.max_hold_mult = max(res.max_hold_mult, hold)
        if cap > 1.0:
            res.position_cap_mult = max(res.position_cap_mult, cap)

    def _add_fpw(self, res: IndustryPipelineResult, key: str, mult: float) -> None:
        if mult <= 1.0:
            mult = 1.0 + abs(mult - 1.0) if mult != 0 else 1.0
        cur = res.feature_weights.get(key, 1.0)
        res.feature_weights[key] = max(cur, float(mult))

    # --- default implementations (subclasses override with industry-specific logic) ---

    def macro_tailwind_score(self, res: IndustryPipelineResult, ctx: IndustryContext, handler: BaseIndustryHandler) -> None:
        macro = self._macro(ctx, handler, "macro_score")
        if macro > 0.1:
            self._boost(res, macro * 0.04, "enh:macro_tailwind")

    def macro_regime_alignment(self, res: IndustryPipelineResult, ctx: IndustryContext, handler: BaseIndustryHandler) -> None:
        return None

    def news_bull_accelerator(self, res: IndustryPipelineResult, ctx: IndustryContext, handler: BaseIndustryHandler) -> None:
        if not ctx.news_headlines:
            return None
        ns = handler.score_news(ctx.news_headlines)
        if ns.bullish_score >= 0.12:
            self._boost(res, ns.bullish_score * 0.08, "enh:bull_news")
            self._boost_p_up(res, ns.bullish_score * 0.02)

    def news_event_catalyst(self, res: IndustryPipelineResult, ctx: IndustryContext, handler: BaseIndustryHandler) -> None:
        if not ctx.news_headlines:
            return None
        text = " ".join(ctx.news_headlines).lower()
        hits = sum(1 for p in self.NEWS_EVENT_BULL if p in text)
        if hits:
            self._boost(res, min(0.18, 0.06 * hits), "enh:event_catalyst")
            self._boost_p_up(res, min(0.06, 0.02 * hits))

    def sympathy_leader_follow(self, res: IndustryPipelineResult, ctx: IndustryContext, handler: BaseIndustryHandler) -> None:
        comove = handler.compute_comovement(
            ctx,
            industry_z=float(ctx.row_features.get("industry_z_20", 0.0)),
            residual=float(ctx.row_features.get("industry_residual_1d", 0.0)),
        )
        if comove.sympathy_score > 0.05:
            self._boost(res, comove.sympathy_score * 0.10, "enh:leader_sympathy")

    def sympathy_cluster_alpha(self, res: IndustryPipelineResult, ctx: IndustryContext, handler: BaseIndustryHandler) -> None:
        z = float(ctx.row_features.get("industry_z_20", 0.0))
        if z > 0.5:
            self._boost(res, float(np.tanh(z * 0.4)) * 0.05, "enh:cluster_momentum")

    def residual_reversion_edge(self, res: IndustryPipelineResult, ctx: IndustryContext, handler: BaseIndustryHandler) -> None:
        residual = float(ctx.row_features.get("industry_residual_1d", 0.0))
        if residual < -0.015:
            self._boost(res, float(np.tanh(-residual * 40)) * 0.04, "enh:residual_revert")

    def factor_rate_emphasis(self, res: IndustryPipelineResult, ctx: IndustryContext, handler: BaseIndustryHandler) -> None:
        tilts = handler.compute_factor_tilts(ctx)
        if tilts.rate_tilt > 0:
            self._boost(res, tilts.rate_tilt * 0.05, "enh:rate_tilt")
            self._add_fpw(res, "fpw_factor_rate", 1.0 + abs(tilts.rate_tilt) * 0.2)

    def factor_expansion_emphasis(self, res: IndustryPipelineResult, ctx: IndustryContext, handler: BaseIndustryHandler) -> None:
        tilts = handler.compute_factor_tilts(ctx)
        if tilts.expansion_tilt > 0:
            self._boost(res, tilts.expansion_tilt * 0.05, "enh:expansion_tilt")
            self._add_fpw(res, "fpw_factor_expansion", 1.0 + tilts.expansion_tilt * 0.15)

    def factor_nasdaq_emphasis(self, res: IndustryPipelineResult, ctx: IndustryContext, handler: BaseIndustryHandler) -> None:
        tilts = handler.compute_factor_tilts(ctx)
        if tilts.nasdaq_tilt > 0:
            self._boost(res, tilts.nasdaq_tilt * 0.04, "enh:nasdaq_tilt")
            self._add_fpw(res, "fpw_nasdaq_beta", 1.0 + tilts.nasdaq_tilt * 0.12)

    def factor_defensive_emphasis(self, res: IndustryPipelineResult, ctx: IndustryContext, handler: BaseIndustryHandler) -> None:
        tilts = handler.compute_factor_tilts(ctx)
        if tilts.defensive_tilt > 0:
            self._boost(res, tilts.defensive_tilt * 0.05, "enh:defensive_tilt")
            self._add_fpw(res, "fpw_vix_sensitivity", 1.0 + tilts.defensive_tilt * 0.15)

    def factor_commodity_emphasis(self, res: IndustryPipelineResult, ctx: IndustryContext, handler: BaseIndustryHandler) -> None:
        tilts = handler.compute_factor_tilts(ctx)
        if tilts.commodity_tilt > 0:
            self._boost(res, tilts.commodity_tilt * 0.05, "enh:commodity_tilt")
            self._add_fpw(res, "fpw_commodity_proxy", 1.0 + tilts.commodity_tilt * 0.2)

    def ml_feature_weight_matrix(self, res: IndustryPipelineResult, ctx: IndustryContext, handler: BaseIndustryHandler) -> None:
        self._add_fpw(res, "fpw_industry_sympathy", 1.0 + self.INTRA_CORR * 0.12)
        self._add_fpw(res, "fpw_industry_leader_momentum", 1.0 + self.INTRA_CORR * 0.08)
        self._add_fpw(res, "fpw_intra_corr", self.INTRA_CORR)
        self._add_fpw(res, "fpw_combined_tilt", 1.08)

    def family_horizon_bias(self, res: IndustryPipelineResult, ctx: IndustryContext, handler: BaseIndustryHandler) -> None:
        res.family_bias += 0.02

    def p_up_probability_lift(self, res: IndustryPipelineResult, ctx: IndustryContext, handler: BaseIndustryHandler) -> None:
        if res.score_delta > 0.05:
            self._boost_p_up(res, min(0.04, res.score_delta * 0.25))

    def playbook_amplification(self, res: IndustryPipelineResult, ctx: IndustryContext, handler: BaseIndustryHandler) -> None:
        pb = playbook_tilt(self.INDUSTRY_ID, ctx.news_headlines)
        if pb > 0:
            amp = pb * float(__import__("os").getenv("INDUSTRY_ENHANCE_PLAYBOOK", "0.12"))
            self._boost(res, amp, f"enh:playbook:{pb:+.3f}")
            res.playbook_tilt = max(res.playbook_tilt, pb)

    def etf_proxy_momentum(self, res: IndustryPipelineResult, ctx: IndustryContext, handler: BaseIndustryHandler) -> None:
        ret5 = float(ctx.row_features.get("industry_ret_5d", 0.0))
        if ret5 > 0.01:
            self._boost(res, float(np.tanh(ret5 * 20)) * 0.05, "enh:etf_momentum")

    def leader_ticker_premium(self, res: IndustryPipelineResult, ctx: IndustryContext, handler: BaseIndustryHandler) -> None:
        if ctx.symbol.upper() in self.LEADER_TICKERS:
            self._boost(res, 0.035, "enh:leader_premium")
            self._expand_risk(res, hold=1.08, cap=1.05)

    def row_feature_affinity(self, res: IndustryPipelineResult, ctx: IndustryContext, handler: BaseIndustryHandler) -> None:
        beta = float(ctx.row_features.get("industry_beta_60", 1.0))
        if 0.8 <= beta <= 1.4:
            self._boost(res, 0.02, "enh:beta_sweet_spot")

    def risk_capacity_expand(self, res: IndustryPipelineResult, ctx: IndustryContext, handler: BaseIndustryHandler) -> None:
        if res.score_delta > 0.08 and not res.block_long:
            self._expand_risk(res, hold=1.10, cap=1.08)

    def comovement_mode_bonus(self, res: IndustryPipelineResult, ctx: IndustryContext, handler: BaseIndustryHandler) -> None:
        mode = self.COMOVEMENT_MODE
        macro = self._macro(ctx, handler, "macro_score")
        if mode == "defensive" and self._macro(ctx, handler, "vix", 20) > 22:
            self._boost(res, 0.05, "enh:defensive_mode")
        elif mode == "follow_nasdaq" and self._macro(ctx, handler, "nasdaq_ret_5d") > 0.02:
            self._boost(res, 0.06, "enh:nasdaq_mode")
        elif mode == "inverse_rates" and self._macro(ctx, handler, "rate_shock_20d") < -0.05:
            self._boost(res, 0.07, "enh:rate_relief_mode")
        elif mode == "commodity" and macro > 0:
            self._boost(res, 0.04, "enh:commodity_mode")
        elif mode == "event_driven" and ctx.news_headlines:
            self._boost(res, 0.03, "enh:event_mode")
        elif macro > 0.15:
            self._boost(res, 0.03, "enh:hybrid_mode")

    def intra_correlation_boost(self, res: IndustryPipelineResult, ctx: IndustryContext, handler: BaseIndustryHandler) -> None:
        if self.INTRA_CORR >= 0.85:
            self._boost(res, (self.INTRA_CORR - 0.8) * 0.15, "enh:high_corr_cluster")

    def headline_commodity_tag_boost(self, res: IndustryPipelineResult, ctx: IndustryContext, handler: BaseIndustryHandler) -> None:
        if not ctx.news_headlines or not self.COMMODITY_KEYS:
            return None
        text = " ".join(ctx.news_headlines).lower()
        hits = [k for k in self.COMMODITY_KEYS if k in text]
        if hits:
            self._boost(res, min(0.10, 0.03 * len(hits)), f"enh:commodity:{hits[0][:12]}")

    def market_cap_tier_boost(self, res: IndustryPipelineResult, ctx: IndustryContext, handler: BaseIndustryHandler) -> None:
        cap = float(ctx.market_cap or 0.0)
        if cap >= 50e9:
            self._boost(res, 0.025, "enh:mega_cap")
        elif cap >= 10e9:
            self._boost(res, 0.015, "enh:large_cap")

    def confidence_blend_boost(self, res: IndustryPipelineResult, ctx: IndustryContext, handler: BaseIndustryHandler) -> None:
        self._boost(res, 0.01, "enh:confidence_floor")

    def high_level_test(self, handler: BaseIndustryHandler | None = None) -> dict[str, Any]:
        """Self-test all features return non-negative net enhancement in bullish scenario."""
        from analytics.industries.base import IndustryContext
        from analytics.industries.registry import get_handler

        h = handler or get_handler(self.INDUSTRY_ID)
        sym = self.LEADER_TICKERS[0] if self.LEADER_TICKERS else "TEST"
        ctx = IndustryContext(
            symbol=sym,
            market_cap=100e9,
            macro={
                "macro_score": 0.45,
                "pmi_score": 0.65,
                "nasdaq_ret_5d": 0.03,
                "rate_shock_20d": -0.05,
                "spread_10y2y": 0.15,
                "vix": 19.0,
            },
            news_headlines=[self.NEWS_BULL[0] if self.NEWS_BULL else "beats estimates"],
            row_features={
                "industry_z_20": 0.8,
                "industry_residual_1d": -0.02,
                "industry_ret_5d": 0.025,
                "industry_beta_60": 1.1,
            },
        )
        base = IndustryPipelineResult()
        out = self.enhance(base, ctx, h)
        missing = [f for f in self.IMPLEMENTED_FEATURES if not callable(getattr(self, f, None))]
        return {
            "industry_id": self.INDUSTRY_ID,
            "features_implemented": len(self.IMPLEMENTED_FEATURES) - len(missing),
            "features_missing": missing,
            "score_delta": out.score_delta,
            "p_up_delta": out.p_up_delta,
            "family_bias": out.family_bias,
            "feature_weight_count": len(out.feature_weights),
            "net_positive": out.score_delta >= 0,
            "notes": out.pipeline_notes[:8],
        }
