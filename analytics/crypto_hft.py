"""Experimental crypto HFT helpers — tiny clips, no IEX, no cancel storm."""

from __future__ import annotations

import math
import os
from typing import Any

from analytics.crypto_math import CryptoScore, should_fire_hft


def experimental_enabled() -> bool:
    return os.getenv("CRYPTO_HFT_EXPERIMENTAL", "true").lower() in ("1", "true", "yes", "on")


def hft_symbols() -> list[str]:
    raw = os.getenv("CRYPTO_HFT_SYMBOLS", "BTC/USD,ETH/USD")
    out: list[str] = []
    seen: set[str] = set()
    for part in raw.split(","):
        s = part.strip().upper().replace("-", "/")
        if not s or s in seen:
            continue
        if "/" not in s:
            s = f"{s}/USD"
        seen.add(s)
        out.append(s)
    return out


def clip_usd() -> float:
    try:
        return max(25.0, float(os.getenv("CRYPTO_HFT_CLIP_USD", "80") or 80))
    except (TypeError, ValueError):
        return 80.0


def max_gross_usd() -> float:
    try:
        return max(clip_usd(), float(os.getenv("CRYPTO_HFT_MAX_GROSS_USD", "250") or 250))
    except (TypeError, ValueError):
        return 250.0


def max_open() -> int:
    try:
        return max(1, int(os.getenv("CRYPTO_HFT_MAX_OPEN", "1") or 1))
    except (TypeError, ValueError):
        return 1


def poll_sec() -> float:
    try:
        return max(1.5, float(os.getenv("CRYPTO_HFT_POLL_SEC", "3") or 3))
    except (TypeError, ValueError):
        return 3.0


def max_orders_per_min() -> int:
    try:
        return max(1, min(20, int(os.getenv("CRYPTO_HFT_MAX_ORDERS_PER_MIN", "6") or 6)))
    except (TypeError, ValueError):
        return 6


def spread_bps(bid: float, ask: float) -> float:
    if not (bid > 0 and ask > 0 and ask >= bid):
        return 9999.0
    mid = 0.5 * (bid + ask)
    if mid <= 0:
        return 9999.0
    return 10_000.0 * (ask - bid) / mid


def mid_slope(mids: list[float], n: int = 6) -> float:
    if len(mids) < 3:
        return 0.0
    w = [float(x) for x in mids[-n:] if float(x) > 0]
    if len(w) < 3:
        return 0.0
    return (w[-1] - w[0]) / w[0]


def qty_for_clip(px: float, notional: float) -> float:
    if px <= 0 or notional <= 0:
        return 0.0
    q = float(notional) / float(px)
    # BTC ~1e-6, ETH ~1e-5 — keep 8 dp like Alpaca qty strings.
    return float(math.floor(q * 1e8) / 1e8)


def skip_held(symbol: str, *, live_qty: float, our_qty: float, skip_if_held: bool = True) -> bool:
    """Do not add into a fortress crypto long. Only manage our tagged qty."""
    if not skip_if_held:
        return False
    extra = float(live_qty) - float(our_qty)
    return extra > max(1e-8, 0.05 * max(float(our_qty), 1e-8)) or (
        float(our_qty) <= 1e-12 and float(live_qty) > 1e-8
    )


def target_px(entry: float, *, bps: float) -> float:
    return float(entry) * (1.0 + float(bps) / 10_000.0)


def stop_px(entry: float, *, bps: float) -> float:
    return float(entry) * (1.0 - float(bps) / 10_000.0)


def decide_entry(
    cs: CryptoScore,
    *,
    bid: float,
    ask: float,
    mids: list[float],
    held_fortress: bool,
    open_count: int,
    gross_usd: float,
) -> dict[str, Any]:
    if held_fortress:
        return {"ok": False, "why": "fortress_held"}
    if open_count >= max_open():
        return {"ok": False, "why": "max_open"}
    if gross_usd >= max_gross_usd() - 1e-6:
        return {"ok": False, "why": "gross"}
    sp = spread_bps(bid, ask)
    slope = mid_slope(mids)
    try:
        max_sp = float(os.getenv("CRYPTO_HFT_MAX_SPREAD_BPS", "12") or 12)
        min_sc = float(os.getenv("CRYPTO_HFT_MIN_SCORE", "0.18") or 0.18)
        min_ex = float(os.getenv("CRYPTO_HFT_MIN_EXPLOSIVE", "0.28") or 0.28)
    except (TypeError, ValueError):
        max_sp, min_sc, min_ex = 12.0, 0.18, 0.28
    fire, why = should_fire_hft(
        cs,
        spread_bps=sp,
        mid_slope=slope,
        max_spread_bps=max_sp,
        min_score=min_sc,
        min_explosive=min_ex,
    )
    mid = 0.5 * (bid + ask)
    return {
        "ok": bool(fire),
        "why": why,
        "spread_bps": sp,
        "mid_slope": slope,
        "mid": mid,
        "qty": qty_for_clip(ask if ask > 0 else mid, clip_usd()),
        "limit_px": float(bid) if bid > 0 else mid,
    }
