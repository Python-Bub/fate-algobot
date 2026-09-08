"""Micro-scalp / noise-harvest strategy math.

Buy near mid/bid with sane limits; exit at entry + tick-aware tiny edge.
Sub-tick fantasy targets (e.g. $0.00000000001) are impossible on Alpaca —
edge is always at least N ticks or N bps, whichever is larger.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from analytics.limit_pricing import (
    entry_limit_px,
    quote_is_sane,
    round_limit,
    spread_pct,
)


def tick_size(px: float) -> float:
    """Alpaca-style US equity tick (penny stocks use finer increments)."""
    p = float(px)
    if p >= 1.0:
        return 0.01
    if p >= 0.1:
        return 0.001
    return 0.0001


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(float(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class ScalpTarget:
    entry_px: float
    target_px: float
    stop_px: float
    edge_abs: float
    edge_bps: float
    tick: float


def min_edge_abs(entry_px: float) -> float:
    """Smallest absolute edge that can print on Alpaca (tick-aware).

    MICRO_SCALP_TARGET_ABS / MICRO_SCALP_TARGET_BPS set the *desired* edge;
    both are floored to MICRO_SCALP_MIN_TICKS * tick (default 1 tick).
    """
    entry = float(entry_px)
    if entry <= 0:
        return 0.0
    tick = tick_size(entry)
    min_ticks = max(1, _env_int("MICRO_SCALP_MIN_TICKS", 1))
    floor = tick * min_ticks
    abs_want = max(0.0, _env_float("MICRO_SCALP_TARGET_ABS", 0.0))
    bps_want = max(0.0, _env_float("MICRO_SCALP_TARGET_BPS", 1.0))
    from_bps = entry * (bps_want / 10_000.0)
    return max(floor, abs_want, from_bps)


def target_exit_px(entry_px: float, *, side: str = "buy") -> float:
    """Long: entry + edge. Short: entry - edge. Always tick-rounded."""
    entry = float(entry_px)
    edge = min_edge_abs(entry)
    side_l = side.lower()
    if side_l in ("sell", "short"):
        return round_limit(max(tick_size(entry), entry - edge))
    return round_limit(entry + edge)


def stop_px(entry_px: float, *, side: str = "buy") -> float:
    """Hard stop absolute/bps (tick-floored)."""
    entry = float(entry_px)
    tick = tick_size(entry)
    stop_abs = max(0.0, _env_float("MICRO_SCALP_STOP_ABS", 0.0))
    stop_bps = max(0.0, _env_float("MICRO_SCALP_STOP_BPS", 8.0))
    dist = max(tick, stop_abs, entry * (stop_bps / 10_000.0))
    side_l = side.lower()
    if side_l in ("sell", "short"):
        return round_limit(entry + dist)
    return round_limit(max(tick, entry - dist))


def build_scalp_plan(entry_px: float, *, side: str = "buy") -> ScalpTarget | None:
    entry = float(entry_px)
    if entry <= 0:
        return None
    tgt = target_exit_px(entry, side=side)
    stp = stop_px(entry, side=side)
    edge = abs(tgt - entry)
    if edge <= 0:
        return None
    return ScalpTarget(
        entry_px=round_limit(entry),
        target_px=tgt,
        stop_px=stp,
        edge_abs=edge,
        edge_bps=(edge / entry) * 10_000.0,
        tick=tick_size(entry),
    )


def quote_allows_entry(bid: float, ask: float, *, max_spread: float | None = None) -> bool:
    """Reject AGL-style fantasy NBBOs before any order."""
    if max_spread is None:
        max_spread = _env_float(
            "MICRO_SCALP_MAX_SPREAD_PCT",
            _env_float("ALPACA_MAX_ENTRY_SPREAD_PCT", _env_float("ALPACA_MAX_QUOTE_SPREAD_PCT", 0.015)),
        )
    return quote_is_sane(bid, ask, max_spread=max_spread)


def compute_entry_limit(bid: float, ask: float, *, aggressive: bool | None = None) -> float | None:
    """Passive buy near bid/mid by default — aggressive cross is opt-in.

    Paying ask+slip for a 4bps target is a guaranteed bleed; default passive.
    """
    if not quote_allows_entry(bid, ask):
        return None
    if aggressive is None:
        aggressive = os.getenv(
            "MICRO_SCALP_AGGRESSIVE_ENTRY",
            "false",
        ).lower() in (
            "1",
            "true",
            "yes",
        )
    return entry_limit_px("buy", bid, ask, aggressive=aggressive)


def edge_clears_spread(bid: float, ask: float, entry_px: float | None = None) -> tuple[bool, str]:
    """Skip when target edge cannot clear live half-spread × multiplier.

    Round-trip cost ≈ full spread; require MICRO_SCALP_TARGET_BPS to beat it.
    """
    if not (bid > 0 and ask > 0 and ask >= bid):
        return False, "bad_quote"
    mid = 0.5 * (bid + ask)
    entry = float(entry_px) if entry_px and entry_px > 0 else mid
    plan = build_scalp_plan(entry, side="buy")
    if plan is None:
        return False, "no_plan"
    spread_bps = ((ask - bid) / mid) * 10_000.0 if mid > 0 else 1e9
    # Need edge to clear full round-trip (spread) × mult (fees/adverse buffer).
    mult = max(1.0, _env_float("MICRO_SCALP_REQUIRE_EDGE_MULT", 1.25))
    need = spread_bps * mult
    if plan.edge_bps + 1e-9 < need:
        return False, f"edge<{need:.1f}bps_vs_spread={spread_bps:.1f}"
    return True, "ok"


def hit_target(side: str, entry_px: float, bid: float, ask: float) -> bool:
    """True when NBBO allows a profitable exit at/above target."""
    plan = build_scalp_plan(entry_px, side=side)
    if plan is None:
        return False
    side_l = side.lower()
    if side_l == "buy":
        return bid > 0 and bid >= plan.target_px
    return ask > 0 and ask <= plan.target_px


def hit_stop(side: str, entry_px: float, bid: float, ask: float) -> bool:
    """True when a *sane* bid prints through the planned stop.

    Fantasy/wide bids (TSLA 332 vs 336) must not trigger a dump below cost.
    """
    if not quote_allows_entry(bid, ask):
        return False
    plan = build_scalp_plan(entry_px, side=side)
    if plan is None:
        return False
    side_l = side.lower()
    if side_l == "buy":
        return bid > 0 and bid <= plan.stop_px
    return ask > 0 and ask >= plan.stop_px


def default_universe() -> list[str]:
    raw = os.getenv(
        "MICRO_SCALP_UNIVERSE",
        "AAPL,MSFT,NVDA,AMD,META,AMZN,GOOGL,TSLA,AVGO,SBUX,COST,JNJ",
    )
    syms = [t.strip().upper() for t in raw.split(",") if t.strip()]
    ban_raw = os.getenv(
        "FORTRESS_BAN_INDEX_ETFS",
        "SPY,QQQ,IWM,DIA,VOO,VTI,SOXX,XLK,XLF,XLE",
    )
    banned = {s.strip().upper() for s in ban_raw.split(",") if s.strip()}
    if os.getenv("FORTRESS_BAN_INDEX_BUYS", "true").lower() in ("1", "true", "yes"):
        syms = [s for s in syms if s not in banned]
    return syms


@dataclass(frozen=True)
class ScalpCaps:
    max_open: int
    max_notional: float
    max_trades_day: int
    per_trade_notional: float
    poll_sec: float
    entry_timeout_ms: int
    max_hold_ms: int
    cooldown_ms: int
    extended: bool
    pdt_aware: bool
    pdt_max_day_trades: int
    pdt_min_equity: float


def load_caps() -> ScalpCaps:
    return ScalpCaps(
        max_open=max(1, _env_int("MICRO_SCALP_MAX_OPEN", 4)),
        max_notional=max(100.0, _env_float("MICRO_SCALP_MAX_NOTIONAL", 2_500.0)),
        max_trades_day=max(1, _env_int("MICRO_SCALP_MAX_TRADES_DAY", 400)),
        per_trade_notional=max(50.0, _env_float("MICRO_SCALP_NOTIONAL", 1500.0)),
        poll_sec=max(0.25, _env_float("MICRO_SCALP_POLL_SEC", 1.0)),
        entry_timeout_ms=max(0, _env_int("MICRO_SCALP_ENTRY_TIMEOUT_MS", 0)),
        max_hold_ms=max(500, _env_int("MICRO_SCALP_MAX_HOLD_MS", 30_000)),
        cooldown_ms=max(0, _env_int("MICRO_SCALP_COOLDOWN_MS", 2500)),
        extended=os.getenv("MICRO_SCALP_EXTENDED", "false").lower() in ("1", "true", "yes"),
        pdt_aware=os.getenv("MICRO_SCALP_PDT_AWARE", "false").lower() in ("1", "true", "yes"),
        pdt_max_day_trades=max(1, _env_int("MICRO_SCALP_PDT_MAX_DAY_TRADES", 3)),
        pdt_min_equity=max(0.0, _env_float("MICRO_SCALP_PDT_MIN_EQUITY", 25_000.0)),
    )


def can_attempt(
    *,
    open_scalps: int,
    open_notional: float,
    trades_today: int,
    equity: float,
    daytrade_count: int,
    caps: ScalpCaps | None = None,
) -> tuple[bool, str]:
    """Pre-trade gate for attempt rate + PDT-aware paper settings."""
    c = caps or load_caps()
    if open_scalps >= c.max_open:
        return False, "max_open"
    if open_notional >= c.max_notional:
        return False, "max_notional"
    if trades_today >= c.max_trades_day:
        return False, "max_trades_day"
    if c.pdt_aware and equity > 0 and equity < c.pdt_min_equity:
        # Paper-first: still respect classic 3-day-trade caution when under $25k.
        if daytrade_count >= c.pdt_max_day_trades:
            return False, "pdt_day_trade_cap"
    return True, "ok"


def spread_reject_reason(bid: float, ask: float) -> str | None:
    if not (bid > 0 and ask > 0 and ask >= bid):
        return "bad_quote"
    max_sp = _env_float(
        "MICRO_SCALP_MAX_SPREAD_PCT",
        _env_float("ALPACA_MAX_ENTRY_SPREAD_PCT", 0.015),
    )
    if spread_pct(bid, ask) > max_sp:
        return "wide_spread"
    return None
