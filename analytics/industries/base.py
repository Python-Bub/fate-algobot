"""Base types and abstract industry handler — every bucket implements specialized logic."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np


class ComovementMode(str, Enum):
    FOLLOW_MARKET = "follow_market"
    INVERSE_RATES = "inverse_rates"
    FOLLOW_NASDAQ = "follow_nasdaq"
    EVENT_DRIVEN = "event_driven"
    HYBRID = "hybrid"
    DEFENSIVE = "defensive"
    COMMODITY = "commodity"


@dataclass
class IndustryContext:
    symbol: str
    sector: str = ""
    yahoo_industry: str = ""
    market_cap: float = 0.0
    macro: dict[str, float] = field(default_factory=dict)
    news_headlines: list[str] = field(default_factory=list)
    row_features: dict[str, float] = field(default_factory=dict)
    parent_symbol: str = ""
    is_spinoff: bool = False
    is_ipo: bool = False
    company_name: str = ""


@dataclass
class ClassificationResult:
    industry_id: str
    industry_name: str
    confidence: float
    etf_proxy: str
    comovement_mode: str
    reasons: list[str] = field(default_factory=list)
    secondary_industry: str = ""


@dataclass
class FactorTiltResult:
    rate_tilt: float = 0.0
    expansion_tilt: float = 0.0
    nasdaq_tilt: float = 0.0
    defensive_tilt: float = 0.0
    commodity_tilt: float = 0.0
    news_tilt: float = 0.0
    combined: float = 0.0
    notes: list[str] = field(default_factory=list)


@dataclass
class NewsScoreResult:
    bullish_score: float = 0.0
    bearish_score: float = 0.0
    net: float = 0.0
    matched_bull: list[str] = field(default_factory=list)
    matched_bear: list[str] = field(default_factory=list)
    event_tags: list[str] = field(default_factory=list)


@dataclass
class ComovementSignal:
    sympathy_score: float = 0.0
    leader_momentum: float = 0.0
    short_sympathy: bool = False
    cluster_pull: float = 0.0
    residual_z: float = 0.0
    mode: str = ""


class BaseIndustryHandler(ABC):
    INDUSTRY_ID: str = "unclassified"
    INDUSTRY_NAME: str = "Unclassified"
    ETF_PROXY: str = "SPY"
    COMOVEMENT_MODE: ComovementMode = ComovementMode.HYBRID

    # Sensitivities in [-1.5, 1.5] scale
    RATE_SENSITIVITY: float = 0.0
    EXPANSION_BETA: float = 0.5
    NASDAQ_BETA: float = 1.0
    SPY_BETA: float = 0.8
    DEFENSIVE_SCORE: float = 0.0
    INTRA_CORR_PRIOR: float = 0.75

    YAHOO_PATTERNS: tuple[str, ...] = ()
    TICKER_HINTS: frozenset[str] = frozenset()
    LEADER_TICKERS: tuple[str, ...] = ()
    SPINOFF_INHERIT: bool = True

    NEWS_BULL: tuple[str, ...] = ()
    NEWS_BEAR: tuple[str, ...] = ()
    NEWS_EVENT_BULL: tuple[str, ...] = ()
    NEWS_EVENT_BEAR: tuple[str, ...] = ()
    COMMODITY_KEYS: tuple[str, ...] = ()

    _WORD = re.compile(r"[a-z0-9]+")

    def yahoo_match_score(self, sector: str, industry: str, company_name: str = "") -> tuple[float, str]:
        blob = f"{sector} {industry} {company_name}".lower()
        best, pat = 0.0, ""
        for p in self.YAHOO_PATTERNS:
            if p in blob and len(p) > len(pat):
                best = 0.55 + min(0.4, len(p) / 40.0)
                pat = p
        return best, pat

    def ticker_hint_score(self, symbol: str) -> float:
        return 0.95 if symbol.upper() in self.TICKER_HINTS else 0.0

    def classify(self, ctx: IndustryContext) -> ClassificationResult | None:
        sym = ctx.symbol.strip().upper()
        score = self.ticker_hint_score(sym)
        reasons: list[str] = []
        if score > 0:
            reasons.append("ticker_hint")
        yscore, pat = self.yahoo_match_score(ctx.sector, ctx.yahoo_industry, ctx.company_name)
        if yscore > score:
            score = yscore
            reasons.append(f"yahoo:{pat}")
        if score < 0.45:
            refined = self.refine_classification(ctx)
            if refined:
                return refined
            return None
        return ClassificationResult(
            industry_id=self.INDUSTRY_ID,
            industry_name=self.INDUSTRY_NAME,
            confidence=min(0.99, score),
            etf_proxy=self.ETF_PROXY,
            comovement_mode=self.COMOVEMENT_MODE.value,
            reasons=reasons,
        )

    def refine_classification(self, ctx: IndustryContext) -> ClassificationResult | None:
        return None

    def inherit_from_parent(self, parent_id: str) -> bool:
        if not self.SPINOFF_INHERIT:
            return False
        return parent_id == self.INDUSTRY_ID

    @abstractmethod
    def compute_factor_tilts(self, ctx: IndustryContext) -> FactorTiltResult:
        ...

    def score_news(self, headlines: list[str]) -> NewsScoreResult:
        text = " ".join(headlines).lower()
        tokens = set(self._WORD.findall(text))
        bull_hits: list[str] = []
        bear_hits: list[str] = []
        events: list[str] = []
        for phrase in self.NEWS_BULL:
            if phrase in text:
                bull_hits.append(phrase)
        for phrase in self.NEWS_BEAR:
            if phrase in text:
                bear_hits.append(phrase)
        for phrase in self.NEWS_EVENT_BULL:
            if phrase in text:
                bull_hits.append(phrase)
                events.append(f"bull:{phrase[:24]}")
        for phrase in self.NEWS_EVENT_BEAR:
            if phrase in text:
                bear_hits.append(phrase)
                events.append(f"bear:{phrase[:24]}")
        for key in self.COMMODITY_KEYS:
            if key in tokens or key in text:
                events.append(f"commodity:{key}")
        b = min(1.0, 0.12 * len(bull_hits))
        r = min(1.0, 0.14 * len(bear_hits))
        return NewsScoreResult(
            bullish_score=b,
            bearish_score=r,
            net=b - r,
            matched_bull=bull_hits[:8],
            matched_bear=bear_hits[:8],
            event_tags=events[:12],
        )

    def news_factor_tilt(self, ctx: IndustryContext) -> float:
        if not ctx.news_headlines:
            return 0.0
        ns = self.score_news(ctx.news_headlines)
        return float(np.tanh(ns.net * 2.2))

    def _macro(self, ctx: IndustryContext, key: str, default: float = 0.0) -> float:
        return float(ctx.macro.get(key, default) or default)

    def _base_rate_tilt(self, ctx: IndustryContext) -> float:
        spread = self._macro(ctx, "spread_10y2y")
        shock = self._macro(ctx, "rate_shock_20d")
        if self.COMOVEMENT_MODE == ComovementMode.INVERSE_RATES or abs(self.RATE_SENSITIVITY) > 0.3:
            return self.RATE_SENSITIVITY * float(np.tanh(spread * 0.35 + shock * 2.2))
        return self.RATE_SENSITIVITY * float(np.tanh(spread * 0.25)) * 0.5

    def _base_expansion_tilt(self, ctx: IndustryContext) -> float:
        pmi = self._macro(ctx, "pmi_score")
        weight = 1.0 if self.EXPANSION_BETA > 0.8 else 0.35
        return self.EXPANSION_BETA * pmi * weight

    def _base_nasdaq_tilt(self, ctx: IndustryContext) -> float:
        ndx = self._macro(ctx, "nasdaq_ret_5d")
        if self.COMOVEMENT_MODE in (ComovementMode.FOLLOW_NASDAQ, ComovementMode.EVENT_DRIVEN):
            return self.NASDAQ_BETA * float(np.tanh(ndx * 7.0))
        if self.COMOVEMENT_MODE == ComovementMode.HYBRID:
            return self.NASDAQ_BETA * ndx * 0.45
        return self.NASDAQ_BETA * ndx * 0.2

    def _base_defensive_tilt(self, ctx: IndustryContext) -> float:
        vix = self._macro(ctx, "vix", 20.0)
        macro = self._macro(ctx, "macro_score")
        if self.DEFENSIVE_SCORE <= 0:
            return 0.0
        stress = float(np.tanh((vix - 22.0) / 12.0))
        return self.DEFENSIVE_SCORE * (stress - float(np.tanh(macro)))

    def compute_comovement(
        self,
        ctx: IndustryContext,
        *,
        leader_moves: dict[str, float] | None = None,
        industry_z: float = 0.0,
        residual: float = 0.0,
    ) -> ComovementSignal:
        leaders = leader_moves or {}
        if not leaders and self.LEADER_TICKERS:
            leaders = {k: 0.0 for k in self.LEADER_TICKERS[:3]}
        vals = [v for v in leaders.values() if v != 0.0]
        avg = float(np.mean(vals)) if vals else 0.0
        prior = self.INTRA_CORR_PRIOR
        sympathy = float(np.tanh(avg * 12.0) * prior)
        if self.COMOVEMENT_MODE == ComovementMode.EVENT_DRIVEN:
            sympathy *= 0.35
        if self.COMOVEMENT_MODE == ComovementMode.INVERSE_RATES:
            sympathy *= 0.6
        short = avg < -0.025 and industry_z > 1.0 and sympathy < -0.15
        cluster = -float(np.tanh(industry_z * 0.7)) * 0.15 if abs(industry_z) > 1.5 else 0.0
        return ComovementSignal(
            sympathy_score=sympathy,
            leader_momentum=avg,
            short_sympathy=short,
            cluster_pull=cluster,
            residual_z=industry_z,
            mode=self.COMOVEMENT_MODE.value,
        )

    def rank_score_delta(
        self,
        ctx: IndustryContext,
        factors: FactorTiltResult,
        comove: ComovementSignal,
        news_tilt: float,
    ) -> float:
        import os

        w_sym = float(os.getenv("RANK_W_INDUSTRY_SYMPATHY", "0.14"))
        w_fac = float(os.getenv("RANK_W_INDUSTRY_FACTOR", "0.10"))
        w_news = float(os.getenv("RANK_W_INDUSTRY_NEWS", "0.12"))
        w_rev = float(os.getenv("RANK_W_INDUSTRY_REVERSION", "0.06"))
        reversion = -0.12 * float(np.tanh(comove.residual_z * 0.75))
        return (
            w_sym * comove.sympathy_score
            + w_fac * factors.combined
            + w_news * news_tilt
            + w_rev * reversion
            + comove.cluster_pull
        )

    def feature_overrides(self, ctx: IndustryContext) -> dict[str, float]:
        return {}

    def to_meta_dict(self) -> dict[str, Any]:
        return {
            "industry_id": self.INDUSTRY_ID,
            "name": self.INDUSTRY_NAME,
            "etf_proxy": self.ETF_PROXY,
            "comovement_mode": self.COMOVEMENT_MODE.value,
            "rate_sensitivity": self.RATE_SENSITIVITY,
            "expansion_beta": self.EXPANSION_BETA,
            "nasdaq_beta": self.NASDAQ_BETA,
            "defensive_score": self.DEFENSIVE_SCORE,
            "intra_corr_prior": self.INTRA_CORR_PRIOR,
            "leader_tickers": list(self.LEADER_TICKERS),
        }
