"""
Per-sleeve pick weightage — explicit 100% tables (book + live signals).

Sleeves: hft | day_trade | fortress | weekly | longterm

Rules:
  - Each sleeve active % sums to 100.
  - MATH-FIRST: model/structure/HF/value/exec ≫ news/Cramer/social/morning narrative.
  - HFT = microstructure only. Zero Cramer/Buffett/DCA/macro essays.
  - Index ETF buys allowed under controlled % + single-name cap + NO_REBUY.
  - Narrative factors stay in the table (not deleted) but tiny % — no emotions in size.

Env: FATE_SLEEVE / PAPER_SIM_SLEEVE / HOLD_DAYS_DEFAULT.
"""

from __future__ import annotations

import os
from typing import Any, Literal

Sleeve = Literal["hft", "day_trade", "fortress", "weekly", "longterm"]
SLEEVES: tuple[Sleeve, ...] = ("hft", "day_trade", "fortress", "weekly", "longterm")

# --- Percent tables (positive rows must sum to 100) ---

HFT_PCT: dict[str, float] = {
    # Kolm/Turiel/Westray OFI + tape; EasyQuant-style momentum overlay. News stays 0.
    "obi": 32.0,
    "tape": 22.0,
    "micro_momentum": 15.0,
    "micro_price": 12.0,
    "spread_liquidity": 8.0,
    "pair_micro": 3.0,
    "stat_arb_micro": 2.0,
    "jp_candle_micro": 2.0,
    "chart_patterns": 3.0,
    "index_etf": 1.0,
    "news_micro": 0.0,  # math-first: no news in HFT size
    "cramer_daily": 0.0,
    "power_people": 0.0,
    "value": 0.0,
    "book": 0.0,
    "macro_cycle": 0.0,
    "inflation_deflation": 0.0,
    "dca_buy_hold": 0.0,
    "buffett_graham": 0.0,
    "derivatives_context": 0.0,
    "alt_context": 0.0,
    "event_calendar": 0.0,  # public clocks are not microstructure
    "event_learn": 0.0,  # learned print-gap model is not microstructure
    "event_ingenuity": 0.0,  # peer cascade / 8-K / Form 4 is not microstructure
    "proven_online": 0.0,  # Hedge/momentum/trend fuse is not microstructure
    "water_datacenter": 0.0,
    "space_infra": 0.0,
}

DAY_TRADE_PCT: dict[str, float] = {
    "candlestick_jp_rl": 13.0,
    "vwap": 11.0,
    "momentum": 11.0,
    "pullback": 8.0,
    "orb": 9.0,
    "trend": 9.0,
    "breakout": 8.0,
    "mean_reversion": 4.0,
    "gap": 5.0,
    "fvg_flag": 4.0,
    "range_fade": 3.0,
    "ml_p_up": 3.0,
    "event_driven": 2.0,
    "index_etf": 2.0,
    # Narrative ≤ 3% total
    "news_impulse": 1.0,
    "morning_club": 1.0,
    "cramer_daily": 1.0,
    "social": 0.0,
    "power_people": 0.0,
    "obi": 0.0,
    "value": 0.0,
    "book": 0.0,
    "buffett_graham": 0.0,
    "dca_buy_hold": 0.0,
    "macro_cycle": 0.0,
    "derivatives_context": 1.0,
    "event_calendar": 1.0,
    "event_learn": 1.0,
    "event_ingenuity": 1.0,
    "proven_online": 1.0,
    "water_datacenter": 0.0,
    "space_infra": 0.0,
}

FORTRESS_PCT: dict[str, float] = {
    # --- MATH — model/exec dominate; earnings_stick full mass when horizon-aligned ---
    "model_edge": 13.0,
    "exec_conf": 11.0,
    "pred_force": 2.0,
    "earnings_stick": 6.0,  # dte≤1 on fortress (was 2% — catalyst starved)
    "structure": 5.0,
    "value_dcf": 5.0,
    "hf_momentum": 6.0,
    "hf_stat_arb": 3.0,
    "hf_trend": 5.0,
    "bottom_fisher": 2.0,
    "hidden_anomaly": 2.0,
    "cross_company": 3.0,
    "garp_quality": 3.0,
    "hf_value": 2.0,
    "hf_quality": 2.0,
    "hf_mean_rev": 2.0,
    "hmm_regime": 2.0,
    "graham_netnet": 2.0,
    "jp_candle": 1.0,
    "fund": 1.0,
    "top100": 1.0,
    "industry_ai": 1.0,
    "unique_big_brain": 1.0,
    "book_composite": 1.0,
    "compounder_quality": 1.0,
    "event_driven": 1.0,
    "institutional": 1.0,
    "macro_cycle": 1.0,
    "hf_etf_disloc": 1.0,
    "index_etf": 1.0,
    # --- NARRATIVE / soft (≤3%, not deleted) ---
    "news_factor": 1.0,
    "cramer_daily": 1.0,
    "morning_club": 1.0,
    "social": 0.5,
    "power_people": 0.5,
    "cramer_post_market": 0.0,
    "succession": 0.0,
    "transcript": 0.0,
    "obi": 0.0,
    "dca_buy_hold": 0.0,
    "derivatives_context": 1.0,
    "alt_context": 0.0,
    "hf_liquidity_mm": 0.0,
    "event_calendar": 1.0,
    "event_learn": 1.0,
    "event_ingenuity": 1.0,
    "proven_online": 2.0,
    "water_datacenter": 2.0,
    "space_infra": 0.0,
}

WEEKLY_PCT: dict[str, float] = {
    "model_edge_5d": 11.0,
    "exec_conf": 8.0,
    "value_dcf": 7.0,
    "structure": 5.0,
    "garp_quality": 5.0,
    "hf_momentum": 6.0,
    "hf_trend": 5.0,
    "hf_stat_arb": 3.0,
    "bottom_fisher": 2.0,
    "cross_company": 4.0,
    "hidden_anomaly": 2.0,
    "hmm_regime": 3.0,
    "book_composite": 3.0,
    "buffett_graham": 3.0,
    "macro_cycle": 3.0,
    "industry_ai": 3.0,
    "fund": 2.0,
    "inflation_deflation": 2.0,
    "interest_rate_cycle": 2.0,
    "dividend_income": 2.0,
    "unique_big_brain": 2.0,
    "index_etf": 1.0,
    "hf_quality": 2.0,
    "hf_etf_disloc": 1.0,
    "dca_buy_hold": 1.0,
    "event_driven": 1.0,
    # Narrative ≤ 4%
    "news_factor": 1.0,
    "cramer_daily": 1.0,
    "morning_club": 1.0,
    "social": 0.5,
    "power_people": 0.5,
    "transcript": 0.0,
    "derivatives_context": 1.0,
    "alt_context": 0.0,
    "obi": 0.0,
    "hf_liquidity_mm": 0.0,
    "event_calendar": 1.0,
    "event_learn": 1.0,
    "event_ingenuity": 1.0,
    "proven_online": 1.0,
    "water_datacenter": 2.0,
    "space_infra": 0.0,
}

LONGTERM_PCT: dict[str, float] = {
    "model_edge_20d": 9.0,
    "value_dcf": 10.0,
    "buffett_graham": 8.0,
    "book_composite": 7.0,
    "garp_quality": 5.0,
    "macro_top_down_bottom_up": 5.0,
    "dca_buy_hold": 3.0,
    "fund": 4.0,
    "inflation_deflation": 4.0,
    "interest_rate_cycle": 4.0,
    "dividend_income": 4.0,
    "cross_company": 3.0,
    "industry_ai": 3.0,
    "compounder_quality": 3.0,
    "structure": 3.0,
    "hidden_anomaly": 2.0,
    "hf_quality_value": 2.0,
    "exec_conf": 1.0,
    "index_etf": 4.0,
    "bottom_fisher": 2.0,
    "reit_infra_context": 1.0,
    "turnaround_special": 1.0,
    "currency_commodity": 1.0,
    # Narrative ≤ 3%
    "news_long_horizon": 1.0,
    "cramer_daily": 1.0,
    "social_morning": 0.5,
    "power_people": 0.5,
    "alt_context": 0.0,
    "derivatives_context": 1.0,
    "obi": 0.0,
    "tape": 0.0,
    "spread_liquidity": 0.0,
    "pred_force": 0.0,
    "hf_liquidity_mm": 0.0,
    "hf_momentum": 0.0,
    "event_calendar": 1.0,
    "event_learn": 1.0,
    "event_ingenuity": 1.0,
    "proven_online": 1.0,
    "water_datacenter": 2.0,
    "space_infra": 1.0,
}

_TABLES: dict[Sleeve, dict[str, float]] = {
    "hft": HFT_PCT,
    "day_trade": DAY_TRADE_PCT,
    "fortress": FORTRESS_PCT,
    "weekly": WEEKLY_PCT,
    "longterm": LONGTERM_PCT,
}

# factor → (env_key, raw_default) pushed by apply_sleeve_env
_ENV_RAW: dict[Sleeve, dict[str, tuple[str, float]]] = {
    "hft": {
        "obi": ("HFT_W_OBI_PROB", 0.32),
        "tape": ("HFT_W_TAPE_PROB", 0.22),
        "micro_momentum": ("HFT_W_MOMENTUM_PROB", 0.15),
        "micro_price": ("HFT_W_MICRO_PRICE_PROB", 0.12),
        "spread_liquidity": ("HFT_W_SPREAD_PROB", 0.08),
        "pair_micro": ("HFT_W_PAIR_PROB", 0.03),
        "news_micro": ("HFT_W_NEWS_PROB", 0.0),
        "jp_candle_micro": ("HFT_W_JP_CANDLE_PROB", 0.02),
        "chart_patterns": ("HFT_W_CHART_PROB", 0.03),
        "stat_arb_micro": ("HFT_W_STAT_ARB_MICRO", 0.02),
        "index_etf": ("HFT_W_INDEX_ETF", 0.01),
    },
    "day_trade": {
        "candlestick_jp_rl": ("DAY_TRADE_CANDLE_W", 0.32),
        "morning_club": ("DAY_TRADE_MORNING_CLUB_W", 0.04),
        "cramer_daily": ("DAY_TRADE_CRAMER_W", 0.04),
        "news_impulse": ("DAY_TRADE_NEWS_W", 0.04),
        "event_driven": ("DAY_TRADE_EVENT_W", 0.08),
        "index_etf": ("DAY_TRADE_INDEX_ETF_W", 0.06),
        "social": ("DAY_TRADE_SOCIAL_W", 0.0),
        "event_calendar": ("RANK_W_EVENT_CALENDAR", 0.10),
        "event_learn": ("RANK_W_EVENT_LEARN", 0.10),
        "event_ingenuity": ("RANK_W_EVENT_INGENUITY", 0.12),
        "proven_online": ("RANK_W_PROVEN_ONLINE", 0.28),
    },
    "fortress": {
        "model_edge": ("FORTRESS_W_EDGE", 0.85),
        "exec_conf": ("FORTRESS_W_EXEC", 0.38),
        "news_factor": ("FORTRESS_NEWS_RANK_W", 0.04),
        "cramer_daily": ("FORTRESS_CRAMER_BLEND", 0.05),
        "cramer_post_market": ("FORTRESS_CRAMER_POST_BLEND", 0.0),
        "succession": ("FORTRESS_SUCCESSION_BLEND", 0.0),
        "social": ("FORTRESS_SOCIAL_BLEND", 0.08),
        "morning_club": ("FORTRESS_MORNING_CLUB_BLEND", 0.05),
        "power_people": ("FORTRESS_POWER_PEOPLE_BLEND", 0.08),
        "algo_memory": ("FORTRESS_ALGO_MEMORY_BLEND", 0.04),
        "institutional": ("FORTRESS_INSTITUTIONAL_BLEND", 0.20),
        "pred_force": ("PRED_FORCE_SCORE_BOOST", 0.24),
        "earnings_stick": ("EARNINGS_STICK_SCORE_BOOST", 0.28),
        "bottom_fisher": ("RANK_W_BOTTOM_FISHER", 0.15),
        "value_dcf": ("RANK_W_VALUE", 0.18),
        "graham_netnet": ("RANK_W_GRAHAM", 0.08),
        "structure": ("RANK_W_STRUCTURE", 0.16),
        "book_composite": ("RANK_W_BOOK", 0.08),
        "garp_quality": ("BOOK_W_GROWTH", 0.28),
        "unique_big_brain": ("RANK_W_UNIQUE", 0.06),
        "hidden_anomaly": ("RANK_W_HIDDEN_ANOMALY", 0.08),
        "cross_company": ("RANK_W_CROSS_COMPANY", 0.12),
        "industry_ai": ("RANK_W_INDUSTRY_PIPELINE", 0.06),
        "hmm_regime": ("RANK_W_HMM_REGIME", 0.10),
        "fund": ("RANK_W_FUND", 0.10),
        "transcript": ("RANK_W_TRANSCRIPT_FACTOR", 0.0),
        "macro_cycle": ("RANK_W_MACRO", 0.06),
        "index_etf": ("RANK_W_INDEX_ETF", 0.06),
        "hf_momentum": ("HF_W_MOMENTUM", 0.18),
        "hf_stat_arb": ("HF_W_STAT_ARB", 0.11),
        "hf_trend": ("HF_W_TREND", 0.16),
        "hf_value": ("HF_W_VALUE", 0.07),
        "hf_quality": ("HF_W_QUALITY", 0.07),
        "hf_mean_rev": ("HF_W_MEAN_REV", 0.07),
        "hf_etf_disloc": ("HF_W_ETF_DISLOC", 0.04),
        "hf_liquidity_mm": ("HF_W_LIQUIDITY_MM", 0.0),
        "top100": ("FORTRESS_TOP100_RANK_BONUS", 0.03),
        "event_driven": ("RANK_W_EVENT", 0.06),
        "jp_candle": ("RANK_W_JP_CANDLE", 0.04),
        "derivatives_context": ("RANK_W_DERIV_CONTEXT", 0.08),
        "event_calendar": ("RANK_W_EVENT_CALENDAR", 0.10),
        "event_learn": ("RANK_W_EVENT_LEARN", 0.10),
        "event_ingenuity": ("RANK_W_EVENT_INGENUITY", 0.12),
        "proven_online": ("RANK_W_PROVEN_ONLINE", 0.28),
        "water_datacenter": ("RANK_W_WATER_DATACENTER", 0.12),
    },
    "weekly": {
        "news_factor": ("RANK_W_NEWS_FACTOR", 0.05),
        "cramer_daily": ("RANK_W_CRAMER", 0.05),
        "cramer_daily_1d": ("RANK_W_CRAMER_1D", 0.02),
        "value_dcf": ("RANK_W_VALUE", 0.18),
        "buffett_graham": ("RANK_W_GRAHAM", 0.10),
        "book_composite": ("RANK_W_BOOK", 0.14),
        "garp_quality": ("BOOK_W_GROWTH", 0.26),
        "dividend_income": ("BOOK_W_INCOME", 0.14),
        "macro_cycle": ("RANK_W_MACRO", 0.12),
        "bottom_fisher": ("RANK_W_BOTTOM_FISHER", 0.20),
        "structure": ("RANK_W_STRUCTURE", 0.14),
        "industry_ai": ("RANK_W_INDUSTRY_PIPELINE", 0.10),
        "cross_company": ("RANK_W_CROSS_COMPANY", 0.12),
        "social": ("RANK_W_SOCIAL", 0.04),
        "hidden_anomaly": ("RANK_W_HIDDEN_ANOMALY", 0.12),
        "unique_big_brain": ("RANK_W_UNIQUE", 0.06),
        "hmm_regime": ("RANK_W_HMM_REGIME", 0.12),
        "inflation_deflation": ("RANK_W_INFLATION", 0.08),
        "interest_rate_cycle": ("RANK_W_RATE_CYCLE", 0.08),
        "dca_buy_hold": ("RANK_W_BUY_HOLD", 0.06),
        "index_etf": ("RANK_W_INDEX_ETF", 0.08),
        "fund": ("RANK_W_FUND", 0.12),
        "transcript": ("RANK_W_TRANSCRIPT_FACTOR", 0.0),
        "hf_etf_disloc": ("HF_W_ETF_DISLOC", 0.04),
        "hf_liquidity_mm": ("HF_W_LIQUIDITY_MM", 0.0),
        "derivatives_context": ("RANK_W_DERIV_CONTEXT", 0.08),
        "alt_context": ("RANK_W_ALT_CONTEXT", 0.0),
        "event_driven": ("RANK_W_EVENT", 0.06),
        "power_people": ("RANK_W_POWER_PEOPLE", 0.04),
        "algo_memory": ("RANK_W_ALGO_MEMORY", 0.03),
        "event_calendar": ("RANK_W_EVENT_CALENDAR", 0.10),
        "event_learn": ("RANK_W_EVENT_LEARN", 0.10),
        "event_ingenuity": ("RANK_W_EVENT_INGENUITY", 0.12),
        "proven_online": ("RANK_W_PROVEN_ONLINE", 0.28),
        "water_datacenter": ("RANK_W_WATER_DATACENTER", 0.10),
    },
    "longterm": {
        "news_long_horizon": ("RANK_W_NEWS_FACTOR", 0.05),
        "cramer_daily": ("RANK_W_CRAMER", 0.05),
        "power_people": ("RANK_W_POWER_PEOPLE", 0.04),
        "algo_memory": ("RANK_W_ALGO_MEMORY", 0.03),
        "value_dcf": ("RANK_W_VALUE", 0.24),
        "buffett_graham": ("RANK_W_GRAHAM", 0.16),
        "book_composite": ("RANK_W_BOOK", 0.22),
        "garp_quality": ("BOOK_W_GROWTH", 0.28),
        "dividend_income": ("BOOK_W_INCOME", 0.20),
        "macro_top_down_bottom_up": ("RANK_W_MACRO", 0.16),
        "inflation_deflation": ("RANK_W_INFLATION", 0.12),
        "interest_rate_cycle": ("RANK_W_RATE_CYCLE", 0.12),
        "dca_buy_hold": ("RANK_W_BUY_HOLD", 0.14),
        "index_etf": ("RANK_W_INDEX_ETF", 0.10),
        "fund": ("RANK_W_FUND", 0.18),
        "industry_ai": ("RANK_W_INDUSTRY_PIPELINE", 0.10),
        "cross_company": ("RANK_W_CROSS_COMPANY", 0.12),
        "compounder_quality": ("RANK_W_COMPOUNDER", 0.10),
        "reit_infra_context": ("RANK_W_REIT", 0.05),
        "bottom_fisher": ("RANK_W_BOTTOM_FISHER", 0.12),
        "structure": ("RANK_W_STRUCTURE", 0.10),
        "hidden_anomaly": ("RANK_W_HIDDEN_ANOMALY", 0.08),
        "alt_context": ("RANK_W_ALT_CONTEXT", 0.0),
        "derivatives_context": ("RANK_W_DERIV_CONTEXT", 0.10),
        "currency_commodity": ("RANK_W_FX_COMMOD", 0.04),
        "turnaround_special": ("RANK_W_TURNAROUND", 0.04),
        "hf_etf_disloc": ("HF_W_ETF_DISLOC", 0.02),
        "hf_liquidity_mm": ("HF_W_LIQUIDITY_MM", 0.0),
        "event_calendar": ("RANK_W_EVENT_CALENDAR", 0.10),
        "event_learn": ("RANK_W_EVENT_LEARN", 0.10),
        "event_ingenuity": ("RANK_W_EVENT_INGENUITY", 0.12),
        "proven_online": ("RANK_W_PROVEN_ONLINE", 0.28),
        "water_datacenter": ("RANK_W_WATER_DATACENTER", 0.12),
        "space_infra": ("RANK_W_SPACE_INFRA", 0.06),
    },
}

_HFT_MUST_BE_ZERO: frozenset[str] = frozenset(
    {
        "cramer_daily",
        "value",
        "book",
        "macro_cycle",
        "inflation_deflation",
        "dca_buy_hold",
        "buffett_graham",
        "derivatives_context",
        "alt_context",
        "value_dcf",
        "book_composite",
        "event_calendar",
        "event_learn",
        "event_ingenuity",
        "proven_online",
        "alt_drivers",
        "water_datacenter",
        "space_infra",
    }
)

_LT_MUST_BE_ZERO: frozenset[str] = frozenset(
    {"obi", "tape", "spread_liquidity", "micro_price", "micro_momentum", "hf_liquidity_mm"}
)


def resolve_sleeve(explicit: str | None = None) -> Sleeve:
    raw = (explicit or os.getenv("FATE_SLEEVE") or os.getenv("PAPER_SIM_SLEEVE") or "").strip().lower()
    if raw in _TABLES:
        return raw  # type: ignore[return-value]
    if raw in ("swing", "intraday", "fortress_live"):
        return "fortress"
    if raw in ("obi", "micro", "hft_obi"):
        return "hft"
    try:
        hold = float(os.getenv("HOLD_DAYS_DEFAULT", "0") or 0)
    except ValueError:
        hold = 0.0
    if hold >= 20:
        return "longterm"
    if hold >= 5:
        return "weekly"
    return "fortress"


def pct_table(sleeve: Sleeve | str | None = None) -> dict[str, float]:
    s = resolve_sleeve(sleeve if isinstance(sleeve, str) else None) if sleeve is None else resolve_sleeve(str(sleeve))
    return dict(_TABLES[s])


def active_pct(sleeve: Sleeve | str | None = None, *, include_zeros: bool = False) -> dict[str, float]:
    t = pct_table(sleeve)
    if include_zeros:
        return t
    return {k: v for k, v in t.items() if v > 0}


def pct_sum(sleeve: Sleeve | str) -> float:
    return float(sum(v for v in pct_table(sleeve).values() if v > 0))


def assert_tables_valid() -> None:
    for s in SLEEVES:
        total = pct_sum(s)
        if abs(total - 100.0) > 0.01:
            raise AssertionError(f"sleeve {s} active % sum={total}, want 100")
    for k in _HFT_MUST_BE_ZERO:
        if HFT_PCT.get(k, 0.0) != 0.0:
            raise AssertionError(f"HFT bleed: {k}={HFT_PCT.get(k)}")
    for k in _LT_MUST_BE_ZERO:
        if LONGTERM_PCT.get(k, 0.0) != 0.0:
            raise AssertionError(f"LT bleed: {k}={LONGTERM_PCT.get(k)}")


def no_cross_bleed() -> dict[str, Any]:
    assert_tables_valid()
    hft_pos = {k for k, v in HFT_PCT.items() if v > 0}
    lt_pos = {k for k, v in LONGTERM_PCT.items() if v > 0}
    # Allow only index_etf as shared positive theme (different meaning per sleeve)
    overlap = (hft_pos & lt_pos) - {"index_etf"}
    return {
        "ok": len(overlap) == 0,
        "hft_positive": sorted(hft_pos),
        "longterm_positive": sorted(lt_pos),
        "forbidden_overlap": sorted(overlap),
        "hft_cramer": HFT_PCT.get("cramer_daily", 0.0),
        "lt_obi": LONGTERM_PCT.get("obi", 0.0),
        "index_etf_allowed": {
            s: float(_TABLES[s].get("index_etf", 0.0)) for s in SLEEVES
        },
    }


def apply_sleeve_env(sleeve: Sleeve | str | None = None, *, force: bool = False) -> dict[str, str]:
    """Push this sleeve's raw env knobs. Liquidity_mm stays 0 off HFT; ETF disloc allowed when table > 0.

    MATH_FIRST_WEIGHTS=true (default) force-overwrites narrative/math knobs so stale
    .env Cramer/news megablends cannot dominate the live score.
    """
    s = resolve_sleeve(str(sleeve) if sleeve else None)
    applied: dict[str, str] = {}
    math_first = os.getenv("MATH_FIRST_WEIGHTS", "true").lower() in ("1", "true", "yes")
    force_keys = force or math_first
    raw_map = _ENV_RAW.get(s, {})
    for _factor, (env_key, raw_val) in raw_map.items():
        if not force_keys and os.getenv(env_key) is not None:
            continue
        os.environ[env_key] = str(raw_val)
        applied[env_key] = str(raw_val)
    # Liquidity MM never ranks non-HFT
    if s != "hft":
        os.environ["HF_W_LIQUIDITY_MM"] = "0.0"
        os.environ["HF_LOCK_LIQUIDITY_MM_ZERO"] = "true"
        applied["HF_W_LIQUIDITY_MM"] = "0.0"
    # ETF disloc: unlock when sleeve table gives it weight
    etf_pct = float(_TABLES[s].get("index_etf", 0.0) + _TABLES[s].get("hf_etf_disloc", 0.0))
    if etf_pct > 0:
        os.environ["HF_LOCK_ETF_DISLOC_ZERO"] = "false"
        os.environ["FORTRESS_BAN_INDEX_BUYS"] = "false"
        if s == "hft":
            os.environ["HFT_BAN_INDEX_BUYS"] = "false"
        applied["HF_LOCK_ETF_DISLOC_ZERO"] = "false"
    else:
        os.environ["HF_W_ETF_DISLOC"] = "0.0"
        os.environ["HF_LOCK_ETF_DISLOC_ZERO"] = "true"
        applied["HF_W_ETF_DISLOC"] = "0.0"
    # Caps / anti-spam always on
    os.environ.setdefault("FORTRESS_MAX_SINGLE_FRAC", "0.10")
    os.environ.setdefault(
        "FORTRESS_NO_REBUY_SYMBOLS",
        "SPY,QQQ,IWM,DIA,VOO,VTI,SOXX,XLK,XLF,XLE",
    )
    os.environ["FATE_SLEEVE"] = s
    os.environ["MATH_FIRST_WEIGHTS"] = "true"
    applied["FATE_SLEEVE"] = s
    applied["MATH_FIRST_WEIGHTS"] = "true"
    # Table % is the source of truth for narrative caps (Cramer is 1%, not 70%).
    table = _TABLES.get(s) or {}
    cramer_pct = float(table.get("cramer_daily", 0.0) or 0.0)
    cap = min(0.15, max(0.0, cramer_pct / 100.0 * 5.0))
    for k in (
        "RANK_W_CRAMER",
        "RANK_W_CRAMER_1D",
        "FORTRESS_CRAMER_BLEND",
        "DAY_TRADE_CRAMER_W",
        "RANK_W_POWER_PEOPLE",
        "FORTRESS_POWER_PEOPLE_BLEND",
    ):
        raw = os.environ.get(k)
        if raw is None:
            continue
        try:
            if float(raw) > cap + 1e-12:
                os.environ[k] = f"{cap:.12g}"
                applied[k] = os.environ[k]
        except ValueError:
            pass
    os.environ["RANK_W_CRAMER_STRONG_BUY_SHARE"] = f"{min(0.10, cap + 0.03):.12g}"
    os.environ["RANK_W_CRAMER_STRONG_BUY_BUMP"] = f"{min(0.06, cap):.12g}"
    os.environ.setdefault("CONFIDENCE_GATE_MODE", "dual")
    return applied


def fortress_weight(name: str, default: float) -> float:
    key_by_factor = {k: v[0] for k, v in _ENV_RAW["fortress"].items()}
    env_map = {v[0]: v[1] for v in _ENV_RAW["fortress"].values()}
    env_key = key_by_factor.get(name)
    if env_key:
        try:
            return float(os.getenv(env_key, str(env_map.get(env_key, default))))
        except ValueError:
            return default
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def markdown_table(sleeve: Sleeve | str) -> str:
    s = resolve_sleeve(str(sleeve))
    rows = sorted(active_pct(s).items(), key=lambda kv: -kv[1])
    lines = [
        f"### {s} (sums to {pct_sum(s):.0f}%)",
        "",
        "| Factor | % |",
        "|--------|--:|",
    ]
    for k, v in rows:
        lines.append(f"| `{k}` | **{v:.0f}** |")
    zeros = sorted(k for k, v in pct_table(s).items() if v == 0)
    if zeros:
        lines.append("")
        lines.append(f"Locked **0%**: {', '.join(f'`{z}`' for z in zeros)}")
    return "\n".join(lines)


def coverage_vs_book() -> dict[str, Any]:
    """Named book/strategy themes present as positive factors somewhere."""
    book_themes = {
        "value_dcf",
        "buffett_graham",
        "graham_netnet",
        "garp_quality",
        "compounder_quality",
        "dividend_income",
        "book_composite",
        "macro_cycle",
        "macro_top_down_bottom_up",
        "inflation_deflation",
        "interest_rate_cycle",
        "currency_commodity",
        "dca_buy_hold",
        "index_etf",
        "alt_context",
        "derivatives_context",
        "cramer_daily",
        "event_driven",
        "event_calendar",
        "event_learn",
        "event_ingenuity",
        "proven_online",
        "stat_arb_micro",
        "hf_stat_arb",
        "turnaround_special",
        "reit_infra_context",
    }
    by_sleeve = {}
    for s in SLEEVES:
        pos = {k for k, v in _TABLES[s].items() if v > 0}
        by_sleeve[s] = sorted(pos & book_themes)
    all_pos = set().union(*(set(v) for v in by_sleeve.values()))
    return {
        "book_themes_total": len(book_themes),
        "book_themes_weighted": len(all_pos & book_themes),
        "missing_themes": sorted(book_themes - all_pos),
        "by_sleeve": by_sleeve,
    }


__all__ = [
    "SLEEVES",
    "HFT_PCT",
    "DAY_TRADE_PCT",
    "FORTRESS_PCT",
    "WEEKLY_PCT",
    "LONGTERM_PCT",
    "resolve_sleeve",
    "pct_table",
    "active_pct",
    "pct_sum",
    "assert_tables_valid",
    "no_cross_bleed",
    "apply_sleeve_env",
    "fortress_weight",
    "markdown_table",
    "coverage_vs_book",
]
