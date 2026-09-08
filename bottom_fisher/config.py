"""Environment-driven config for bottom-fisher scanner."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _b(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes")


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default


def _i(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def bottom_fisher_enabled() -> bool:
    return _b("USE_BOTTOM_FISHER", True)


def bottom_fisher_paper_boost_enabled() -> bool:
    return _b("BOTTOM_FISHER_PAPER_BOOST", True)


@dataclass(frozen=True)
class BottomFisherConfig:
    """Tunable thresholds — override via env."""

    bottom_percentile: float = 0.50
    min_price_usd: float = 3.0
    max_price_usd: float = 500.0
    min_daily_volume_usd: float = 500_000.0
    max_scan_symbols: int = 400
    max_ai_review: int = 24
    min_recovery_score: float = 0.42
    min_news_catalyst: float = 0.15
    require_model: bool = True
    use_ai_review: bool = True
    use_news_radar: bool = True
    news_lookback_hours: int = 72
    rank_weight_recovery: float = 0.45
    rank_weight_news: float = 0.25
    rank_weight_ai: float = 0.30
    paper_score_weight: float = 0.55
    store_path: str = "data/bottom_fisher/latest_scan.json"

    @classmethod
    def from_env(cls) -> "BottomFisherConfig":
        return cls(
            bottom_percentile=_f("BOTTOM_FISHER_PERCENTILE", 0.50),
            min_price_usd=_f("BOTTOM_FISHER_MIN_PRICE", 3.0),
            max_price_usd=_f("BOTTOM_FISHER_MAX_PRICE", 500.0),
            min_daily_volume_usd=_f("BOTTOM_FISHER_MIN_DOLLAR_VOL", 500_000.0),
            max_scan_symbols=_i("BOTTOM_FISHER_MAX_SCAN", 400),
            max_ai_review=_i("BOTTOM_FISHER_MAX_AI_REVIEW", 24),
            min_recovery_score=_f("BOTTOM_FISHER_MIN_RECOVERY", 0.42),
            min_news_catalyst=_f("BOTTOM_FISHER_MIN_NEWS", 0.15),
            require_model=_b("BOTTOM_FISHER_REQUIRE_MODEL", True),
            use_ai_review=_b("BOTTOM_FISHER_USE_AI", True),
            use_news_radar=_b("BOTTOM_FISHER_USE_NEWS", True),
            news_lookback_hours=_i("BOTTOM_FISHER_NEWS_HOURS", 72),
            rank_weight_recovery=_f("BOTTOM_FISHER_W_RECOVERY", 0.45),
            rank_weight_news=_f("BOTTOM_FISHER_W_NEWS", 0.25),
            rank_weight_ai=_f("BOTTOM_FISHER_W_AI", 0.30),
            paper_score_weight=_f("RANK_W_BOTTOM_FISHER", 0.55),
            store_path=os.getenv("BOTTOM_FISHER_STORE", "data/bottom_fisher/latest_scan.json"),
        )
