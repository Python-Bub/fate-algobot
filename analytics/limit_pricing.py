"""Bid/ask-anchored limit prices — buy low, sell high (mirrors hft/order-pricing.ts).

Paper Alpaca NBBOs can be absurdly wide (e.g. AGL bid 101 / ask 172). Piercing
those quotes creates instant fake losses. Spread sanity is mandatory for both
entry and exit.
"""

from __future__ import annotations

import os


def round_limit(px: float) -> float:
    p = float(px)
    if p <= 0:
        return p
    if p >= 1.0:
        return round(p, 2)
    if p >= 0.1:
        return round(p, 3)
    return round(p, 4)


def _tick(px: float) -> float:
    return 0.01 if px >= 1.0 else 0.001 if px >= 0.1 else 0.0001


def spread_pct(bid: float, ask: float) -> float:
    if not (bid > 0 and ask > 0):
        return 1.0
    mid = (bid + ask) / 2.0
    if mid <= 0:
        return 1.0
    return (ask - bid) / mid


def quote_is_sane(bid: float, ask: float, *, max_spread: float | None = None) -> bool:
    if not (bid > 0 and ask > 0 and ask >= bid):
        return False
    if max_spread is None:
        max_spread = float(os.getenv("ALPACA_MAX_QUOTE_SPREAD_PCT", "0.015"))
    return spread_pct(bid, ask) <= max_spread


def entry_limit_px(side: str, bid: float, ask: float, *, aggressive: bool | None = None) -> float | None:
    """Buy at bid side (below mid); sell/short at ask side (above mid).

    Returns None when the quote is too wide — caller must skip the order.
    Aggressive buys pierce a *sane* ask but are hard-capped near mid so paper
    fantasy asks cannot print 25%+ adverse fills.
    """
    if not (bid > 0 and ask > 0 and ask >= bid):
        return None
    max_entry_spread = float(os.getenv("ALPACA_MAX_ENTRY_SPREAD_PCT", os.getenv("ALPACA_MAX_QUOTE_SPREAD_PCT", "0.015")))
    if spread_pct(bid, ask) > max_entry_spread:
        return None
    mid = (bid + ask) / 2.0
    tick = _tick(mid)
    slip_bps = float(os.getenv("ALPACA_LIMIT_SLIP_BPS", "8")) / 10_000.0
    max_cross = float(os.getenv("ALPACA_MAX_ENTRY_CROSS_PCT", "0.004"))
    if aggressive is None:
        aggressive = os.getenv("ALPACA_AGGRESSIVE_ENTRY", "false").lower() in ("1", "true", "yes")
        # BUY_LOW wins: never chase the ask just because AGGRESSIVE_ENTRY is on.
        if os.getenv("ALPACA_BUY_LOW", "true").lower() in ("1", "true", "yes"):
            aggressive = False
    side_l = side.lower()
    if side_l == "buy":
        if aggressive:
            pierce = ask * (1.0 + slip_bps) + tick
            cap = mid * (1.0 + max_cross) + tick
            return round_limit(min(pierce, cap))
        bid_low = bid + tick
        mid_cap = mid - tick
        return round_limit(max(tick, min(bid_low + tick, mid_cap)))
    if aggressive:
        pierce = bid * (1.0 - slip_bps) - tick
        floor = mid * (1.0 - max_cross) - tick
        return round_limit(max(tick, max(pierce, floor)))
    ask_high = ask - tick
    mid_floor = mid + tick
    return round_limit(max(ask_high, mid_floor))


def _forced_sell_floor(entry_px: float, mid: float, max_force: float) -> float:
    """Stop-exit floor.

    If the name has already gapped more than `max_force` through the stop, floor
    vs live mid — not vs entry. WMT 2026-08-20: entry 114.93, mid 104.34, a
    2% entry floor (112.63) sat above the ask (109.71) and never filled.
    """
    mid_floor = mid * (1.0 - max_force) if mid > 0 else 0.0
    if entry_px <= 0 or mid <= 0:
        return mid_floor
    underwater = (entry_px - mid) / entry_px
    if underwater > max_force:
        return mid_floor
    return max(entry_px * (1.0 - max_force), mid_floor)


def exit_limit_px(
    flat_side: str,
    bid: float,
    ask: float,
    entry_px: float = 0.0,
    *,
    forced_loss: bool = False,
) -> float | None:
    """Sell high / cover low.

    Wide quotes: never dump at a fantasy bid. Use mid-anchored marketable prices
    so take-profits can still fill without realizing bogus 10%+ paper slippage.
    """
    if not (bid > 0 and ask > 0 and ask >= bid):
        return None
    mid = (bid + ask) / 2.0
    tick = _tick(mid)
    slip_bps = float(os.getenv("ALPACA_LIMIT_SLIP_BPS", "8")) / 10_000.0
    min_bps = float(os.getenv("ALPACA_MIN_EXIT_PROFIT_BPS", "3")) / 10_000.0
    max_spread = float(os.getenv("ALPACA_EXIT_MAX_SPREAD_PCT", "0.015"))
    wide = spread_pct(bid, ask) > max_spread
    # Default sell-high (ask-side). Forced/liquidation paths pass forced_loss=True.
    aggressive = os.getenv("ALPACA_AGGRESSIVE_EXIT", "false").lower() in ("1", "true", "yes")
    side_l = flat_side.lower()
    if side_l == "sell":
        min_px = entry_px * (1 + min_bps) if entry_px > 0 else 0.0
        if wide:
            # Anchor to mid, not the phantom bid. Still marketable vs mid.
            cross = mid * (1.0 - slip_bps) - tick
            if forced_loss:
                max_force = float(os.getenv("ALPACA_MAX_FORCE_EXIT_SLIP_PCT", "0.02"))
                floor = _forced_sell_floor(entry_px, mid, max_force)
                px = max(tick, floor, cross)
                # A limit above the live ask cannot fill (WMT 112.63 vs ask 109.71).
                if ask > 0:
                    px = min(px, ask)
                return round_limit(px)
            px = max(tick, cross)
            if min_px > 0:
                px = max(px, min_px)
            return round_limit(px)
        if forced_loss or aggressive:
            cross = bid * (1.0 - slip_bps) - tick
            if forced_loss:
                max_force = float(os.getenv("ALPACA_MAX_FORCE_EXIT_SLIP_PCT", "0.02"))
                floor = _forced_sell_floor(entry_px, mid, max_force)
                px = max(tick, floor, cross)
                if ask > 0:
                    px = min(px, ask)
                return round_limit(px)
            px = max(tick, cross)
            if min_px > 0:
                px = max(px, min_px)
            return round_limit(px)
        ask_px = ask - tick
        touch = max(ask_px, bid + tick)
        # Sell high: floor at entry+edge even if that sits above the ask.
        # Dumping at the ask when the name is red is how TSLA was sold below cost.
        if min_px > 0:
            return round_limit(max(touch, min_px))
        return round_limit(touch)
    max_px = entry_px * (1 - min_bps) if entry_px > 0 else float("inf")
    if wide:
        cross = mid * (1.0 + slip_bps) + tick
        if forced_loss:
            max_force = float(os.getenv("ALPACA_MAX_FORCE_EXIT_SLIP_PCT", "0.02"))
            ceil = ask * 10
            if entry_px > 0:
                ceil = entry_px * (1.0 + max_force)
            ceil = min(ceil, mid * (1.0 + max_force))
            return round_limit(min(ceil, cross))
        return round_limit(min(max_px, cross))
    if forced_loss or aggressive:
        cross = ask * (1.0 + slip_bps) + tick
        if forced_loss:
            return round_limit(cross)
        return round_limit(min(max_px, cross))
    bid_px = bid + tick
    return round_limit(min(max_px, bid_px))


def sell_limit_unfillable(limit_px: float, bid: float, ask: float) -> bool:
    """True when a resting sell cannot trade at the current NBBO."""
    try:
        lim = float(limit_px)
        bp = float(bid)
        ap = float(ask)
    except (TypeError, ValueError):
        return False
    if not (lim > 0 and bp > 0 and ap > 0 and ap >= bp):
        return False
    slack_bps = float(os.getenv("ALPACA_SELL_REPRICE_ABOVE_ASK_BPS", "8"))
    if quote_is_sane(bp, ap):
        return lim > ap * (1.0 + slack_bps / 10_000.0) + 1e-12
    if lim > ap + 1e-12:
        return True
    mid = (bp + ap) / 2.0
    max_above_mid_bps = float(os.getenv("ALPACA_SELL_REPRICE_WIDE_ABOVE_MID_BPS", "40"))
    return mid > 0 and lim > mid * (1.0 + max_above_mid_bps / 10_000.0) + 1e-12


def sell_limit_at_touch(limit_px: float, bid: float, ask: float) -> bool:
    """True when a resting sell is still at/near a fillable ask (or mid on a wide book)."""
    try:
        lim = float(limit_px)
        bp = float(bid)
        ap = float(ask)
    except (TypeError, ValueError):
        return False
    if not (lim > 0 and bp > 0 and ap > 0 and ap >= bp):
        return False
    slack_bps = float(os.getenv("ALPACA_SELL_REPRICE_ABOVE_ASK_BPS", "8"))
    below_bps = float(os.getenv("ALPACA_SELL_REPRICE_BELOW_ASK_BPS", "15"))
    if quote_is_sane(bp, ap):
        if lim > ap * (1.0 + slack_bps / 10_000.0) + 1e-12:
            return False
        return lim >= ap * (1.0 - below_bps / 10_000.0) - 1e-12
    mid = (bp + ap) / 2.0
    if not (mid > 0):
        return False
    max_away_bps = float(os.getenv("ALPACA_SELL_REPRICE_WIDE_AWAY_MID_BPS", "15"))
    return abs(lim - mid) / mid <= max_away_bps / 10_000.0


def buy_limit_unfillable(limit_px: float, bid: float, ask: float) -> bool:
    """True when a resting buy sits too far below the bid to lift."""
    try:
        lim = float(limit_px)
        bp = float(bid)
        ap = float(ask)
    except (TypeError, ValueError):
        return False
    if not (lim > 0 and bp > 0 and ap > 0 and ap >= bp):
        return False
    slack_bps = float(os.getenv("ALPACA_BUY_REPRICE_BELOW_BID_BPS", "25"))
    if quote_is_sane(bp, ap):
        return lim < bp * (1.0 - slack_bps / 10_000.0) - 1e-12
    mid = (bp + ap) / 2.0
    if lim > ap + 1e-12:
        return True
    max_below_mid_bps = float(os.getenv("ALPACA_BUY_REPRICE_WIDE_BELOW_MID_BPS", "80"))
    return mid > 0 and lim < mid * (1.0 - max_below_mid_bps / 10_000.0) - 1e-12


def working_sell_needs_reprice(
    limit_px: float,
    bid: float,
    ask: float,
    age_sec: float | None,
    *,
    max_age_sec: float = 120.0,
    min_unfillable_age_sec: float = 30.0,
    entry_px: float = 0.0,
) -> bool:
    """Cancel/replace when the ticket cannot fill — never to sell below cost."""
    if age_sec is None or age_sec < 0:
        return False
    cost = float(entry_px or 0)
    try:
        lim = float(limit_px)
    except (TypeError, ValueError):
        lim = 0.0
    # A sell already at/above cost is sell-high. Only chase the ask if the ask
    # itself is still >= cost (winner). Never pull a red ticket down through entry.
    if cost > 0 and lim + 1e-12 >= cost:
        if ask + 1e-12 >= cost and sell_limit_unfillable(lim, bid, ask) and age_sec >= min_unfillable_age_sec:
            return True
        return False
    # Fillable (or any) sell below cost is the TSLA dump — pull it up immediately.
    if cost > 0 and lim > 0 and lim + 1e-12 < cost:
        return True
    if sell_limit_unfillable(lim, bid, ask) and age_sec >= min_unfillable_age_sec:
        return True
    if age_sec >= max_age_sec and not sell_limit_at_touch(lim, bid, ask):
        return True
    return False


def sell_already_priced(limit_px: float, bid: float, ask: float, entry_px: float = 0.0) -> bool:
    """True when replacing now would rest at the same (or worse) price — don't storm."""
    try:
        lim = float(limit_px)
    except (TypeError, ValueError):
        return False
    if not (lim > 0 and bid > 0 and ask > 0):
        return False
    fresh = exit_limit_px("sell", bid, ask, entry_px, forced_loss=False)
    if fresh is None or fresh <= 0:
        return True
    tick = _tick(lim)
    # Same ticket ±1 tick or 5 bps — cancelling it just re-places the same limit.
    return abs(fresh - lim) <= max(tick, lim * 0.0005) + 1e-12
