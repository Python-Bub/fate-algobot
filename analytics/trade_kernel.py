"""From a close to a ticket. This is the book the live sleeves have to obey.

A long pays ``entry`` per share now and is worth ``price`` later.
Gain = (price - entry) / entry. A short is that number with the sign flipped.

A model that chooses the next bar may use today's close and every close
before it. Tomorrow's close is the label, and only after tomorrow has
printed. It is never a feature.
"""

from __future__ import annotations

import math


def gain_frac(entry: float, price: float, *, side: str = "LONG") -> float | None:
    """Fractional P&L. None when the prices are not a real fill."""
    if entry <= 0 or price <= 0:
        return None
    raw = (price - entry) / entry
    if str(side).upper() == "SHORT":
        return -raw
    return raw


def _sigmoid(z: float) -> float:
    z = max(-30.0, min(30.0, z))
    return 1.0 / (1.0 + math.exp(-z))


def feature_row(closes: list[float], t: int) -> list[float] | None:
    """Bias plus 1-day, 2-day, and 5-day returns ending at ``closes[t]``.

    Uses only indexes ``<= t``.
    """
    if t < 5 or t >= len(closes):
        return None
    out = [1.0]
    for k in (1, 2, 5):
        prev = closes[t - k]
        if prev <= 0 or closes[t] <= 0:
            return None
        out.append(100.0 * (closes[t] / prev - 1.0))
    return out


def label_up(closes: list[float], t: int) -> int | None:
    """1 when the next close is higher. None until that close exists."""
    if t < 0 or t + 1 >= len(closes):
        return None
    if closes[t] <= 0:
        return None
    return 1 if closes[t + 1] > closes[t] else 0


def fit_logistic(
    rows: list[list[float]],
    labels: list[int],
    *,
    steps: int = 80,
    lr: float = 1.5,
) -> list[float]:
    """One bias-included logistic regression. Labels are 0 or 1."""
    n = len(rows)
    if n == 0 or n != len(labels):
        raise ValueError("rows and labels must be the same non-empty length")
    try:
        import numpy as np

        x = np.asarray(rows, dtype=float)
        y = np.asarray(labels, dtype=float)
        w = np.zeros(x.shape[1], dtype=float)
        for _ in range(steps):
            z = np.clip(x @ w, -30.0, 30.0)
            p = 1.0 / (1.0 + np.exp(-z))
            w -= lr * (x.T @ (p - y)) / n
        return [float(v) for v in w]
    except Exception:
        w = [0.0] * len(rows[0])
        for _ in range(steps):
            grad = [0.0] * len(w)
            for x, y in zip(rows, labels):
                p = _sigmoid(sum(wi * xi for wi, xi in zip(w, x)))
                err = p - float(y)
                for j, xi in enumerate(x):
                    grad[j] += err * xi
            inv = lr / n
            for j in range(len(w)):
                w[j] -= inv * grad[j]
        return w


def predict_up(weights: list[float], row: list[float]) -> float:
    return _sigmoid(sum(w * x for w, x in zip(weights, row)))


def walk_forward_p_up(
    closes: list[float],
    t: int,
    *,
    min_train: int = 20,
) -> float | None:
    """P(next close is up) using only closes at indexes ``<= t``.

    Training labels stop at bar ``t - 1``, whose future close is ``closes[t]``.
    The label for bar ``t`` needs ``closes[t + 1]`` and is not in the fit.
    """
    rows: list[list[float]] = []
    labels: list[int] = []
    for i in range(5, t):
        row = feature_row(closes, i)
        y = label_up(closes, i)
        if row is None or y is None:
            continue
        rows.append(row)
        labels.append(y)
    if len(rows) < min_train:
        return None
    row_t = feature_row(closes, t)
    if row_t is None:
        return None
    if len(set(labels)) < 2:
        return float(sum(labels) / len(labels))
    return predict_up(fit_logistic(rows, labels), row_t)


def move_sizes(closes: list[float], t: int, *, lookback: int = 20) -> tuple[float, float] | None:
    """Average up-bar and down-bar returns ending at ``t``.

    Both numbers are positive fractions. Uses only closes at indexes ``<= t``.
    """
    if t < 1 or t >= len(closes) or lookback < 1:
        return None
    start = max(1, t - lookback + 1)
    ups: list[float] = []
    downs: list[float] = []
    for i in range(start, t + 1):
        prev = closes[i - 1]
        px = closes[i]
        if prev <= 0 or px <= 0:
            continue
        r = px / prev - 1.0
        if r > 0:
            ups.append(r)
        elif r < 0:
            downs.append(-r)
    if not ups and not downs:
        return None
    avg_up = sum(ups) / len(ups) if ups else 0.0
    avg_down = sum(downs) / len(downs) if downs else 0.0
    return avg_up, avg_down


def one_bar_ev(p_up: float, avg_up: float, avg_down: float, cost: float) -> float:
    """Expected fractional P&L of holding one bar.

    ``p_up`` is the chance the bar is an up bar. ``avg_up`` and ``avg_down``
    are the typical sizes of those bars, both as positive fractions. ``cost``
    is the round trip (buy the ask, sell the bid, plus fees), paid either way.

    A 55% call on a coin-sized move does not clear a spread. That ticket is a loss.
    """
    p = min(1.0, max(0.0, float(p_up)))
    win = max(0.0, float(avg_up))
    loss = max(0.0, float(avg_down))
    return p * win - (1.0 - p) * loss - max(0.0, float(cost))


def min_p_to_pay(avg_up: float, avg_down: float, cost: float) -> float:
    """Smallest win probability with a positive expected P&L."""
    win = max(0.0, float(avg_up))
    loss = max(0.0, float(avg_down))
    denom = win + loss
    if denom <= 1e-12:
        return 1.0
    need = (loss + max(0.0, float(cost))) / denom
    return min(1.0, max(0.0, need))


def verdict(p_up: float, *, long_min: float = 0.55, short_max: float = 0.45) -> str:
    """LONG, SHORT, or FLAT. The middle band is an explicit no-trade."""
    if p_up >= long_min:
        return "LONG"
    if p_up <= short_max:
        return "SHORT"
    return "FLAT"


def order_notional(
    equity: float,
    buying_power: float,
    *,
    ticket: float,
    max_name_frac: float = 0.10,
) -> float:
    """Dollars for one new name. Never past the name cap or live buying power."""
    if equity <= 0 or buying_power <= 0 or ticket <= 0 or max_name_frac <= 0:
        return 0.0
    return min(float(ticket), equity * float(max_name_frac), float(buying_power))


def stop_triggered(entry: float, price: float, hard_stop: float, *, side: str = "LONG") -> bool:
    g = gain_frac(entry, price, side=side)
    if g is None or hard_stop <= 0:
        return False
    return g <= -abs(hard_stop)


def simulate_book(
    closes: list[float],
    *,
    equity: float = 100_000.0,
    buying_power: float = 100_000.0,
    ticket: float = 5_000.0,
    max_name_frac: float = 0.10,
    hard_stop: float = 0.04,
    long_min: float = 0.55,
    min_train: int = 20,
    cost_frac: float = 0.0,
) -> dict:
    """One-name long book. Signal at t uses closes[: t + 1] only.

    A stop sells on the bar that breached it, at that bar's close.
    """
    cash = float(equity)
    shares = 0.0
    entry = 0.0
    trades: list[dict] = []
    for t in range(len(closes)):
        px = float(closes[t])
        if px <= 0:
            continue
        if shares > 0 and stop_triggered(entry, px, hard_stop):
            g = gain_frac(entry, px) or 0.0
            cash += shares * px
            trades.append({"t": t, "side": "STOP", "px": px, "gain": g, "qty": shares})
            shares = 0.0
            entry = 0.0
            continue
        if shares > 0 or t + 1 >= len(closes):
            continue
        p_up = walk_forward_p_up(closes[: t + 1], t, min_train=min_train)
        if p_up is None or verdict(p_up, long_min=long_min) != "LONG":
            continue
        sizes = move_sizes(closes, t)
        if sizes is None or one_bar_ev(p_up, sizes[0], sizes[1], cost_frac) <= 0.0:
            continue
        marked = cash + shares * px
        notion = order_notional(
            marked,
            min(buying_power, cash),
            ticket=ticket,
            max_name_frac=max_name_frac,
        )
        if notion < 1.0:
            continue
        qty = notion / px
        cash -= notion * (1.0 + max(0.0, float(cost_frac)))
        shares = qty
        entry = px
        trades.append({"t": t, "side": "LONG", "px": px, "qty": qty, "p_up": p_up, "cost": cost_frac})
    last = float(closes[-1]) if closes else 0.0
    return {
        "cash": cash,
        "shares": shares,
        "entry": entry,
        "equity": cash + shares * last,
        "trades": trades,
    }
