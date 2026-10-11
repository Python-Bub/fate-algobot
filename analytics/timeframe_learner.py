"""Four horizons, trained one bar at a time from local closes.

Horizons are 1, 5, 20, and 60 sessions. A weight is updated only once that
horizon's future close has already printed. A buy needs three of the four
to agree. Nothing here reads the network.
"""

from __future__ import annotations

import math

import numpy as np

from analytics.trade_kernel import move_sizes

HORIZONS = (1, 5, 20, 60)


def _feat(closes: np.ndarray, t: int) -> np.ndarray | None:
    """Bias, four lookbacks, and 20-day volatility. Indexes ``<= t`` only."""
    if t < 60 or t >= len(closes) or closes[t] <= 0:
        return None
    out = [1.0]
    for k in (1, 5, 20, 60):
        prev = float(closes[t - k])
        if prev <= 0:
            return None
        out.append(float(np.clip(closes[t] / prev - 1.0, -0.5, 0.5)))
    window = closes[t - 19 : t + 1]
    prev = window[:-1]
    good = (prev > 0) & (window[1:] > 0)
    if not np.any(good):
        return None
    rets = window[1:][good] / prev[good] - 1.0
    out.append(float(np.clip(rets.std() if rets.size else 0.0, 0.0, 0.2)))
    return np.asarray(out, dtype=float)


def horizon_votes(closes: list[float], *, lr: float = 0.12) -> list[list[float] | None]:
    """One four-probability row per bar. A row does not use later closes."""
    c = np.asarray(closes, dtype=float)
    n = int(c.size)
    out: list[list[float] | None] = [None] * n
    weights = {h: np.zeros(6, dtype=float) for h in HORIZONS}
    for t in range(n):
        for h in HORIZONS:
            src = t - h
            x = _feat(c, src)
            if x is None or c[t] <= 0 or c[src] <= 0:
                continue
            y = 1.0 if c[t] > c[src] else 0.0
            w = weights[h]
            z = float(np.clip(x @ w, -20.0, 20.0))
            p = 1.0 / (1.0 + math.exp(-z))
            w -= lr * (p - y) * x
        if t < 80:
            continue
        x = _feat(c, t)
        if x is None:
            continue
        votes = []
        for h in HORIZONS:
            z = float(np.clip(x @ weights[h], -20.0, 20.0))
            votes.append(1.0 / (1.0 + math.exp(-z)))
        out[t] = votes
    return out


def latest_timeframes(closes: list[float]) -> dict | None:
    """The newest trained vote. ``agree`` is how many horizons are at least 0.55."""
    last = None
    for votes in horizon_votes(closes):
        if votes is not None:
            last = votes
    if last is None:
        return None
    up = [p for p in last if p >= 0.55]
    return {
        "p_1": last[0],
        "p_5": last[1],
        "p_20": last[2],
        "p_60": last[3],
        "agree": len(up),
        "p_up": (sum(up) / len(up)) if up else (sum(last) / len(last)),
    }


def timeframe_signals(
    closes: list[float],
    *,
    agree: int = 3,
    floor: float = 0.55,
    lr: float = 0.12,
) -> list[tuple[float, float, float] | None]:
    """Walk-forward probabilities. Bar ``t`` does not see closes after ``t``."""
    n = len(closes)
    out: list[tuple[float, float, float] | None] = [None] * n
    for t, votes in enumerate(horizon_votes(closes, lr=lr)):
        if votes is None:
            continue
        sizes = move_sizes(closes, t)
        if sizes is None:
            continue
        up = [p for p in votes if p >= floor]
        if len(up) < agree:
            continue
        out[t] = (sum(up) / len(up), float(sizes[0]), float(sizes[1]))
    return out
