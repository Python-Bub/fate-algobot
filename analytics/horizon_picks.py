"""Per-timeframe conviction picks — each horizon stands alone.

A 1d head does not need a 5d/20d/HFT head to agree. Rank that sleeve's own
probability by |confidence| (a 0.82 down beats a 0.61 up) and take the top
couple. Long-only sleeves skip shorts; sleeves that allow shorts take them.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from typing import Any


def horizon_independent() -> bool:
    return os.getenv("HORIZON_INDEPENDENT", "true").lower() in ("1", "true", "yes")


def horizon_top_k(default: int | None = None) -> int:
    if default is None:
        default = int(os.getenv("HORIZON_TOP_K", "3") or 3)
    return max(1, int(os.getenv("HORIZON_TOP_K", str(default)) or default))


def directional_conviction(p: float) -> float:
    """|2p-1| in [0, 1] — equally treats a sure fall and a sure rise."""
    x = float(p)
    if x != x:  # NaN
        return 0.0
    x = min(1.0, max(0.0, x))
    return abs(x - 0.5) * 2.0


def side_from_p(p: float, *, mid: float = 0.5) -> str:
    return "long" if float(p) >= float(mid) else "short"


def sleeve_model_prefix(hold_days: int) -> str:
    """Map a sleeve hold window onto the trained head (not a fused blend)."""
    d = int(hold_days)
    if d <= 1:
        return "p_daily"
    if d <= 7:
        return "p_short"
    if d <= 42:
        return "p_long"
    return "p_xlong"


def sleeve_native_probability(
    hold_days: int,
    *,
    p_daily: float | None = None,
    p_short: float | None = None,
    p_long: float | None = None,
    p_xlong: float | None = None,
    fused: float | None = None,
) -> float | None:
    """Probability for *this* hold only. Missing head falls back toward fused last."""
    prefix = sleeve_model_prefix(hold_days)
    table: dict[str, float | None] = {
        "p_daily": p_daily,
        "p_short": p_short,
        "p_long": p_long,
        "p_xlong": p_xlong,
    }
    order = {
        "p_daily": ("p_daily", "p_short", "fused"),
        "p_short": ("p_short", "p_daily", "fused"),
        "p_long": ("p_long", "p_xlong", "fused"),
        "p_xlong": ("p_xlong", "p_long", "fused"),
    }[prefix]
    for key in order:
        if key == "fused":
            if fused is not None:
                return float(fused)
            continue
        val = table.get(key)
        if val is not None:
            return float(val)
    return float(fused) if fused is not None else None


def pick_top_conviction(
    rows: Sequence[Mapping[str, Any]],
    *,
    p_get: Callable[[Mapping[str, Any]], float | None] | None = None,
    p_key: str = "p_up",
    k: int | None = None,
    allow_short: bool = False,
    min_p_long: float = 0.55,
    min_p_short: float = 0.55,
    ticker_key: str = "ticker",
) -> list[dict[str, Any]]:
    """Top-K names for one timeframe, ranked by conviction of that timeframe's call.

    High-confidence downs outrank weak ups when ``allow_short`` is true.
    """
    n = max(1, int(k)) if k is not None else horizon_top_k()
    scored: list[tuple[float, str, Mapping[str, Any]]] = []
    for row in rows:
        if p_get is not None:
            p = p_get(row)
        else:
            raw = row.get(p_key)
            p = float(raw) if raw is not None else None
        if p is None:
            continue
        side = side_from_p(p)
        conv = directional_conviction(p)
        if side == "long":
            if float(p) < float(min_p_long):
                continue
        else:
            if not allow_short:
                continue
            if (1.0 - float(p)) < float(min_p_short):
                continue
        scored.append((conv, side, row))
    scored.sort(key=lambda item: (-item[0], item[2].get(ticker_key) or ""))
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for conv, side, row in scored:
        t = str(row.get(ticker_key) or "").upper()
        if not t or t in seen:
            continue
        seen.add(t)
        item = dict(row)
        item["conviction"] = float(conv)
        item["horizon_side"] = side
        out.append(item)
        if len(out) >= n:
            break
    return out
