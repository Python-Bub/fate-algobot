"""One walk through daily history. Reward after the close, never before it.

A decision on bar t may use closes at t and earlier. The next close is the
label, and it is not a feature. A win grants the asymmetric reward. A loss
denies it, with the long penalty, and the ministries that voted yes get lighter.

The walk does not fetch the web. Looking up a name on the live internet
during an old bar would show the future. A small browse budget, if used,
runs only before the first bar and only to fill missing past prices.
"""

from __future__ import annotations

import math
from typing import Callable

from analytics.ai_government import _WEIGHT, convene
from analytics.asymmetric_loss import asymmetric_reward
from analytics.government_paper import nudge_weights
from analytics.trade_kernel import (
    feature_row,
    label_up,
    min_p_to_pay,
    move_sizes,
    one_bar_ev,
    order_notional,
)


def online_signals(closes: list[float]) -> list[tuple[float, float, float] | None]:
    """Walk-forward P(up) and move sizes. Bar t does not see closes after t."""
    import numpy as np

    n = len(closes)
    out: list[tuple[float, float, float] | None] = [None] * n
    w = np.zeros(4, dtype=float)
    lr = 0.15
    rets: list[float] = []
    for t in range(n):
        if t >= 1 and closes[t - 1] > 0 and closes[t] > 0:
            rets.append(closes[t] / closes[t - 1] - 1.0)
        if t >= 6:
            row = feature_row(closes, t - 1)
            y = label_up(closes, t - 1)
            if row is not None and y is not None:
                x = np.asarray(row, dtype=float)
                z = float(np.clip(x @ w, -30.0, 30.0))
                p = 1.0 / (1.0 + math.exp(-z))
                w -= lr * (p - float(y)) * x
        if t < 25:
            continue
        row_t = feature_row(closes, t)
        sizes = move_sizes(closes, t)
        if row_t is None or sizes is None:
            continue
        x = np.asarray(row_t, dtype=float)
        z = float(np.clip(x @ w, -30.0, 30.0))
        p_up = 1.0 / (1.0 + math.exp(-z))
        out[t] = (p_up, float(sizes[0]), float(sizes[1]))
    return out


def run_history(
    panels: dict[str, dict],
    *,
    equity: float = 100_000.0,
    ticket: float = 100_000.0,
    max_names: int = 10,
    cost: float = 0.001,
    start_weights: dict[str, float] | None = None,
    state: dict | None = None,
    convene_fn: Callable[..., dict] | None = None,
    batch_fn: Callable[[list[tuple]], list[dict]] | None = None,
    progress: Callable[[dict], None] | None = None,
    progress_every: int = 20,
    review_every: int = 1,
    daily: bool = True,
    max_avg_down: float | None = 0.025,
) -> dict:
    """Walk every shared date once. One book. Rewards land on the exit bar.

    ``daily`` holds a name from one close to the next, then puts the proceeds
    back to work. The gain is that session's move. The next close is not
    known when the name is bought.
    """
    if not panels:
        return {"equity": equity, "closed": 0, "reward_sum": 0.0, "dates": 0}

    decide = convene_fn or (lambda case, weights: convene(case, weights=weights, record=False))
    names = list(panels)
    clock: list[str] = sorted({d for panel in panels.values() for d in panel["dates"]})
    at = {sym: {d: i for i, d in enumerate(panel["dates"])} for sym, panel in panels.items()}

    cash = float(equity)
    weights = {**_WEIGHT, **(start_weights or {})}
    lots: dict[str, dict] = {}
    granted = 0.0
    denied = 0.0
    reward_sum = 0.0
    wins = 0
    losses = 0
    closed = 0
    convened = 0
    bought = 0
    days_invested = 0
    vetoes = {"none": 0, "treasury": 0, "interior": 0}
    actions = {"LONG": 0, "FLAT": 0, "SHORT": 0}
    start_i = 0
    if state:
        cash = float(state.get("cash", cash))
        weights.update(state.get("weights") or {})
        lots = dict(state.get("lots") or {})
        granted = float(state.get("granted") or 0.0)
        denied = float(state.get("denied") or 0.0)
        reward_sum = float(state.get("reward_sum") or 0.0)
        wins = int(state.get("wins") or 0)
        losses = int(state.get("losses") or 0)
        closed = int(state.get("closed") or 0)
        convened = int(state.get("convened") or 0)
        bought = int(state.get("bought") or 0)
        last = state.get("last_date")
        if last in clock:
            start_i = clock.index(last) + 1

    last_px = {}
    curve_tail: list[float] = []

    def _mark() -> float:
        return cash + sum(lot["qty"] * float(last_px.get(sym, lot["entry"])) for sym, lot in lots.items())

    def _close(sym: str, i: int, d: str, px: float, reason: str) -> None:
        nonlocal cash, granted, denied, reward_sum, wins, losses, closed, weights
        lot = lots.pop(sym)
        gain = (px - lot["entry"]) / lot["entry"]
        cash += lot["qty"] * px * (1.0 - cost)
        held = max(1, i - int(lot["entry_i"]))
        reward = asymmetric_reward("LONG", gain, bars_held=held)
        reward_sum += float(reward.reward)
        if reward.reward >= 0:
            granted += float(reward.reward)
            wins += 1
        else:
            denied += float(reward.reward)
            losses += 1
        closed += 1
        weights = nudge_weights(
            weights,
            lot.get("sections") or {},
            gain,
            loss_mult=0.94,
            win_mult=1.02,
        )

    for i in range(start_i, len(clock)):
        d = clock[i]
        for sym in list(lots):
            idx = at[sym].get(d)
            if idx is None:
                continue
            last_px[sym] = float(panels[sym]["closes"][idx])
        marked = _mark()
        deployed = 0.0 if marked <= 0 else max(0.0, (marked - cash) / marked)
        pending: list[tuple] = []
        n_alive = sum(1 for sym in names if d in at[sym])
        if len(names) >= 50 and n_alive < 50:
            names_today = []
        else:
            names_today = names
        trail: list[float] = []
        for sym in names_today:
            idx = at[sym].get(d)
            if idx is None or idx < 20:
                continue
            prev = panels[sym]["closes"][idx - 20]
            px = panels[sym]["closes"][idx]
            if prev > 0 and px > 0:
                trail.append(px / prev - 1.0)
        trail.sort()
        market_up = (not trail) or trail[len(trail) // 2] >= 0.0
        for sym in names_today:
            idx = at[sym].get(d)
            if idx is None:
                continue
            sig = panels[sym]["sig"][idx]
            if sig is None:
                continue
            p_up, avg_up, avg_down = sig
            ev = one_bar_ev(p_up, avg_up, avg_down, cost)
            # Only names that clear the spread get a desk. Convening every
            # listing every day was the slow part, and it still bought coin flips.
            need = min_p_to_pay(avg_up, avg_down, cost) + 0.02
            calm = max_avg_down is None or avg_down <= max_avg_down
            # A held name stays until the edge is actually gone. Selling it
            # because today's probability dipped under the entry bar was the churn.
            if sym in lots:
                if not calm or p_up < 0.48:
                    continue
            elif (not market_up) or p_up < need or ev <= 0.0 or not calm:
                continue
            review = review_every <= 1 or (hash(sym) + i) % review_every == 0
            if not review and sym not in lots:
                continue
            pending.append((sym, p_up, avg_up, avg_down, ev, idx))
        orders: list[dict] = []
        if pending:
            cases = [
                (
                    {
                        "p_up": p_up,
                        "avg_up": avg_up,
                        "avg_down": avg_down,
                        "exec_conf": p_up,
                        "held": False,
                        "deployed_frac": deployed,
                    },
                    weights,
                )
                for _sym, p_up, avg_up, avg_down, _ev, _idx in pending
            ]
            if batch_fn is not None:
                orders = list(batch_fn(cases))
            else:
                orders = [decide(case, w) for case, w in cases]
        cands: list[tuple] = []
        for (sym, p_up, avg_up, avg_down, ev, idx), order in zip(pending, orders):
            convened += 1
            action = str(order.get("action") or "FLAT")
            actions[action] = actions.get(action, 0) + 1
            veto = order.get("veto") or "none"
            vetoes[veto] = vetoes.get(veto, 0) + 1
            if not daily and action != "LONG":
                continue
            px = float(panels[sym]["closes"][idx])
            cands.append((ev, -avg_down, p_up, float(order.get("score") or 0.0), sym, order, px))
        cands.sort(reverse=True)
        # Stay in a name that still clears the spread. Replacing it because
        # another name is a hair better is what sold the book every day.
        keep = {sym for _ev, _calm, _p, _score, sym, _order, _px in cands}
        for sym in list(lots):
            idx = at[sym].get(d)
            if idx is None:
                continue
            px = float(panels[sym]["closes"][idx])
            lot = lots[sym]
            gain = (px - lot["entry"]) / lot["entry"]
            stopped = gain <= -float(lot["stop"])
            held_for = i - int(lot["entry_i"])
            hzn = int(lot["horizon"])
            # A 5-day model bet stays for those five sessions. It is not
            # sold because tomorrow's rank moved.
            stuck = hzn < 100_000 and held_for < hzn
            aged = (hzn < 100_000 and held_for >= hzn) or ((not daily) and held_for >= hzn)
            if stopped or aged or (not stuck and sym not in keep):
                _close(sym, i, d, px, "stop" if stopped else "exit")
        for ev, _calm, p_up, _score, sym, order, px in cands:
            if sym in lots or sym not in keep:
                continue
            if len(lots) >= max_names or cash <= 1:
                break
            marked = _mark()
            # The dollar ticket used to freeze at $100k, so a bigger book
            # stopped compounding. Each name gets 10% of today's equity.
            size = float(order.get("size_mult") or 1.0)
            notion = order_notional(
                marked,
                cash / (1.0 + cost),
                ticket=(marked if daily else ticket) * size,
            )
            if notion < 1 or px <= 0:
                continue
            qty = notion / px
            cash -= notion * (1.0 + cost)
            last_px[sym] = px
            lots[sym] = {
                "qty": qty,
                "entry": px,
                "entry_i": i,
                "stop": max(0.08, float(order.get("stop") or 0.08)) if daily else float(order.get("stop") or 0.02),
                "horizon": int(panels[sym].get("hold") or (10**6 if daily else max(1, int(order.get("horizon_days") or 5)))),
                "sections": order.get("sections") or {},
            }
            bought += 1
        if lots:
            days_invested += 1
        equity_now = _mark()
        curve_tail.append(round(equity_now, 2))
        if progress and (i % progress_every == 0 or i + 1 == len(clock)):
            why = ""
            if closed == 0 and convened > 50 and bought == 0:
                top = max(vetoes, key=vetoes.get)
                why = f"no fills yet. strongest veto is {top}. chair counts {actions}"
            elif closed > 20 and wins == 0:
                why = "closes are all losses. the penalty is cutting ministries that voted yes."
            elif days_invested > 40 and equity_now < equity * 0.97 and bought > days_invested:
                why = "the book is being replaced too often. a name should stay while it still clears the spread."
            progress(
                {
                    "date": d,
                    "dates_done": i + 1,
                    "dates_total": len(clock),
                    "equity": round(equity_now, 2),
                    "cash": round(cash, 2),
                    "open": len(lots),
                    "bought": bought,
                    "closed": closed,
                    "days_invested": days_invested,
                    "wins": wins,
                    "losses": losses,
                    "reward_sum": round(reward_sum, 4),
                    "granted": round(granted, 4),
                    "denied": round(denied, 4),
                    "convened": convened,
                    "names": len(names),
                    "why": why,
                    "last_date": d,
                    "cash_state": cash,
                    "weights": weights,
                    "lots": lots,
                    "wins_n": wins,
                    "losses_n": losses,
                    "closed_n": closed,
                    "convened_n": convened,
                    "bought_n": bought,
                    "granted_n": granted,
                    "denied_n": denied,
                    "reward_n": reward_sum,
                }
            )

    if clock and lots:
        last_i = len(clock) - 1
        last_d = clock[last_i]
        for sym in list(lots):
            idx = at[sym].get(last_d)
            px = (
                float(panels[sym]["closes"][idx])
                if idx is not None
                else float(last_px.get(sym, lots[sym]["entry"]))
            )
            _close(sym, last_i, last_d, px, "exit")

    return {
        "equity": _mark() if clock else equity,
        "cash": cash,
        "closed": closed,
        "wins": wins,
        "losses": losses,
        "reward_sum": reward_sum,
        "granted": granted,
        "denied": denied,
        "convened": convened,
        "bought": bought,
        "days_invested": days_invested,
        "dates": len(clock),
        "weights": weights,
        "curve_tail": curve_tail[-30:],
        "actions": actions,
        "vetoes": vetoes,
    }
