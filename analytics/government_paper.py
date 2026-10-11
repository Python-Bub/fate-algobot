"""Paper book run by the government. No broker orders.

This machine observes. The GCP paper VM is the only Alpaca orderer, so this
ledger never sends an order. It still fills, marks, stops, and learns.

On each close the section weights move: a ministry that voted for a winner
gets a little heavier, one that voted for a loser gets a little lighter.
The other learners (proven-online, events, the meta head, neural replay)
are credited through the same close path the live book uses. The big neural
fit stays off this loop so a fill cannot sit inside a 24-epoch retrain.
"""

from __future__ import annotations

import os
from typing import Callable

from analytics.ai_government import _WEIGHT, convene
from analytics.trade_kernel import move_sizes, one_bar_ev, order_notional, walk_forward_p_up


def learn_close(symbol: str, gain: float, extra: dict | None = None) -> dict:
    """Credit every learner that can take one closed paper trade.

    Neural checkpoint fitting stays off. The row is still written, and the
    json-state learners (algo adapter, events, proven-online, industry,
    insider, hidden patterns, the ultimate engine, gen-learn) all see the close.
    """
    os.environ["LEARN_FIT_NEURAL_ON_FILL"] = "false"
    extra = extra or {}
    p_up = float(extra.get("p_up") or 0.5)
    mom = float(extra.get("mom") or 0.0)
    state = {
        "p_up": p_up,
        "p_long": p_up,
        "p_short": 1.0 - p_up,
        "p_gap": 0.0,
        "execution_confidence": p_up,
        "momentum_5d": mom,
        "mom_5d": mom,
        "sentiment_impulse": 0.0,
        "vol_regime_ratio": 1.0,
        "regime_transition_flag": 0.0,
        "alpha_proxy_20": mom,
    }
    out: dict = {"symbol": symbol, "gain": gain, "applied": []}
    try:
        from online_learning.trade_feedback import learn_from_realized_trade

        learn_from_realized_trade(
            symbol, "LONG", float(gain), state=state, source="government_paper"
        )
        out["applied"].append("trade_feedback")
    except Exception as e:
        out["trade_feedback"] = str(e)
    try:
        from analytics.gen_learn import online_update

        gen = online_update({}, float(gain), p_up=p_up, mom_5d=mom)
        if gen.get("applied"):
            out["applied"].append("gen_learn")
        else:
            out["gen_learn"] = gen.get("reason") or "skipped"
    except Exception as e:
        out["gen_learn"] = str(e)
    return out


def nudge_weights(
    weights: dict[str, float],
    sections: dict,
    gain: float,
    *,
    loss_mult: float = 0.98,
    win_mult: float = 1.02,
) -> dict[str, float]:
    """Move ministry weights from the trade that just closed."""
    out = dict(weights)
    won = gain > 0
    for name, info in sections.items():
        if name == "opposition":
            continue
        score = float((info or {}).get("round2") or 0.0)
        agreed = score > 0.05
        if not agreed:
            continue
        cur = float(out.get(name, _WEIGHT.get(name, 1.0)))
        cur = cur * (win_mult if won else loss_mult)
        out[name] = min(2.0, max(0.35, cur))
    return out


def study_losses(
    trades: list[dict],
    weights: dict[str, float] | None = None,
    *,
    rounds: int = 3,
    learn: Callable[..., dict] | None = None,
    train_neural: bool = True,
) -> dict:
    """Replay every stopped trade so the learners sit with the loss.

    The stock-model files stay put. This updates the online heads, the
    json-state learners, and one short neural step on the replay.
    """
    os.environ["LEARN_FIT_NEURAL_ON_FILL"] = "false"
    os.environ["USE_ONLINE_UPDATER"] = "true"
    credit = learn if learn is not None else learn_close
    table = {**_WEIGHT, **(weights or {})}
    losses = [
        t
        for t in trades
        if t.get("side") == "SELL" and float(t.get("gain") or 0.0) < 0.0
    ]
    steps = 0
    for _ in range(max(1, rounds)):
        for trade in losses:
            gain = float(trade["gain"])
            extra = {
                "p_up": trade.get("p_up") or 0.5,
                "mom": trade.get("mom") if trade.get("mom") is not None else gain,
            }
            try:
                credit(str(trade.get("symbol") or ""), gain, extra)
            except TypeError:
                credit(str(trade.get("symbol") or ""), gain)
            steps += 1
            sections = trade.get("sections") or {}
            if sections:
                table = nudge_weights(table, sections, gain, loss_mult=0.94)
    neural = "skipped"
    if train_neural and losses:
        try:
            os.environ["NEURAL_EPOCHS"] = "1"
            os.environ["NEURAL_MAX_SAMPLES"] = "300"
            os.environ["NEURAL_MIN_SAMPLES"] = "8"
            from online_learning.neural_ensemble import train_neural_ensemble_for_ticker

            rep = train_neural_ensemble_for_ticker(str(losses[-1].get("symbol") or "SPY"))
            neural = str(getattr(rep, "reason", None) or rep)
        except Exception as e:
            neural = str(e)
    return {
        "losses": len(losses),
        "steps": steps,
        "rounds": rounds,
        "weights": table,
        "neural": neural,
    }


def run_government_paper(
    series: dict[str, list[float]],
    *,
    equity: float = 100_000.0,
    ticket: float = 5_000.0,
    max_names: int = 3,
    cost: float = 0.001,
    learn: Callable[..., dict] | None = learn_close,
    flatten: bool = True,
    dates: dict[str, list[str]] | None = None,
) -> dict:
    """Walk the closes. One government order per name per bar. Local fills only."""
    names = [s for s, px in series.items() if len(px) >= 30]
    if not names:
        return {"equity": equity, "trades": [], "curve": [equity], "weights": dict(_WEIGHT)}
    n = min(len(series[s]) for s in names)
    cash = float(equity)
    weights = dict(_WEIGHT)
    lots: dict[str, dict] = {}
    trades: list[dict] = []
    curve = [cash]
    learns: list[dict] = []

    def _date(sym: str, t: int) -> str | None:
        if not dates or sym not in dates:
            return None
        row = dates[sym]
        if 0 <= t < len(row):
            return row[t]
        return None

    def _close(sym: str, t: int, px: float, reason: str) -> None:
        nonlocal cash
        lot = lots.pop(sym)
        gain = (px - lot["entry"]) / lot["entry"]
        cash += lot["qty"] * px
        rec = {
            "t": t,
            "date": _date(sym, t),
            "symbol": sym,
            "side": "SELL",
            "reason": reason,
            "px": px,
            "gain": gain,
            "entry": lot["entry"],
            "entry_t": lot["entry_t"],
        }
        trades.append(rec)
        if learn is not None:
            extra = {
                "p_up": lot.get("p_up"),
                "mom": lot.get("mom"),
                "entry_t": lot.get("entry_t"),
                "t": t,
                "reason": reason,
            }
            try:
                learns.append(learn(sym, gain, extra))
            except TypeError:
                learns.append(learn(sym, gain))
        nudged = nudge_weights(dict(weights), lot["sections"], gain)
        weights.clear()
        weights.update(nudged)

    for t in range(n):
        for sym in list(lots):
            px = float(series[sym][t])
            lot = lots[sym]
            if px <= 0 or lot["entry"] <= 0:
                continue
            gain = (px - lot["entry"]) / lot["entry"]
            held_bars = t - int(lot["entry_t"])
            if gain <= -float(lot["stop"]):
                _close(sym, t, px, "stop")
            elif held_bars >= int(lot["horizon"]):
                _close(sym, t, px, "horizon")
        if len(lots) < max_names:
            for sym in names:
                if sym in lots or t + 1 >= n:
                    continue
                closes = series[sym][: t + 1]
                p_up = walk_forward_p_up(closes, t)
                sizes = move_sizes(closes, t)
                if p_up is None or sizes is None:
                    continue
                order = convene(
                    {
                        "p_up": p_up,
                        "avg_up": sizes[0],
                        "avg_down": sizes[1],
                        "exec_conf": p_up,
                        "held": False,
                    },
                    weights=weights,
                )
                if order.get("action") != "LONG":
                    continue
                if one_bar_ev(p_up, sizes[0], sizes[1], cost) <= 0:
                    continue
                px = float(series[sym][t])
                mom = 0.0
                if t >= 5 and float(closes[t - 5]) > 0:
                    mom = px / float(closes[t - 5]) - 1.0
                marked = cash + sum(v["qty"] * float(series[s][t]) for s, v in lots.items())
                notion = order_notional(marked, cash, ticket=ticket * float(order.get("size_mult") or 1.0))
                if notion < 1 or px <= 0:
                    continue
                qty = notion / px
                cash -= notion * (1.0 + cost)
                lots[sym] = {
                    "qty": qty,
                    "entry": px,
                    "entry_t": t,
                    "stop": float(order.get("stop") or 0.02),
                    "horizon": max(1, int(order.get("horizon_days") or 5)),
                    "sections": order.get("sections") or {},
                    "p_up": p_up,
                    "mom": mom,
                }
                trades.append(
                    {
                        "t": t,
                        "date": _date(sym, t),
                        "symbol": sym,
                        "side": "BUY",
                        "px": px,
                        "qty": qty,
                        "p_up": p_up,
                        "horizon": lots[sym]["horizon"],
                        "stop": lots[sym]["stop"],
                        "n_desks": order.get("n_desks"),
                    }
                )
                if len(lots) >= max_names:
                    break
        marked = cash + sum(v["qty"] * float(series[s][t]) for s, v in lots.items())
        curve.append(marked)

    if flatten:
        last = n - 1
        for sym in list(lots):
            _close(sym, last, float(series[sym][last]), "mark")
        curve.append(cash)
    marked = cash + sum(
        v["qty"] * float(series[s][n - 1]) for s, v in lots.items()
    )
    open_lots = {
        sym: {
            "qty": lot["qty"],
            "entry": lot["entry"],
            "entry_t": lot["entry_t"],
            "stop": lot["stop"],
            "horizon": lot["horizon"],
            "p_up": lot.get("p_up"),
            "last": float(series[sym][n - 1]),
            "gain": (float(series[sym][n - 1]) - lot["entry"]) / lot["entry"],
        }
        for sym, lot in lots.items()
    }
    return {
        "equity": cash if flatten else marked,
        "cash": cash,
        "start": equity,
        "trades": trades,
        "curve": curve,
        "weights": weights,
        "learns": learns,
        "open": len(lots),
        "lots": open_lots,
    }


def load_market_panels(*, min_bars: int = 100) -> dict[str, dict]:
    """Every cached common stock we can mark without calling the broker."""
    from pathlib import Path

    import pandas as pd

    from fortress_universe import is_core_trainable_equity

    root = Path("data/cache/prices")
    model_root = Path("models")
    trained: set[str] = set()
    if model_root.is_dir():
        for path in model_root.glob("*_model.pkl"):
            try:
                if path.stat().st_size < 20_000:
                    continue
            except OSError:
                continue
            trained.add(path.name[: -len("_model.pkl")].upper())
    panels: dict[str, dict] = {}
    newest = ""
    staged: list[tuple[str, list[str], list[float]]] = []
    for path in sorted(root.glob("*.parquet")):
        sym = path.stem.upper()
        if not is_core_trainable_equity(sym):
            continue
        if trained and sym not in trained:
            continue
        try:
            df = pd.read_parquet(path, columns=["Close"])
        except Exception:
            continue
        if df is None or df.empty or "Close" not in df.columns:
            continue
        dates = [str(x)[:10] for x in df.index]
        closes = [float(x) for x in df["Close"].tolist()]
        keep = [(d, c) for d, c in zip(dates, closes) if c > 0]
        if len(keep) < min_bars:
            continue
        keep = keep[-140:]
        if keep[-1][1] < 1.0:
            continue
        staged.append((sym, [d for d, _ in keep], [c for _, c in keep]))
        if keep[-1][0] > newest:
            newest = keep[-1][0]
    # A handful of freshly fetched names can end a week later than the
    # cache. Keep anything that printed within three weeks of that newest bar.
    cutoff = ""
    if newest:
        from datetime import datetime, timedelta

        cutoff = (datetime.fromisoformat(newest) - timedelta(days=21)).date().isoformat()
    for sym, dates, closes in staged:
        if cutoff and dates[-1] < cutoff:
            continue
        panels[sym] = {"dates": dates, "closes": closes}
    return panels


def run_market_book(
    panels: dict[str, dict],
    *,
    equity: float = 100_000.0,
    ticket: float = 8_000.0,
    max_names: int = 12,
    cost: float = 0.001,
    sessions: int = 60,
    learn: Callable[..., dict] | None = None,
    full_last: bool = True,
    progress: Callable[[str], None] | None = None,
    start_weights: dict[str, float] | None = None,
    flatten: bool = True,
) -> dict:
    """Rank the whole panel. The chair's score decides who gets the next slot.

    On the last session every desk votes on every name. Earlier sessions
    convene a name when the kernel already sees a possible long, so the book
    can walk months of the market without dropping the desks.
    """
    if not panels:
        return {"equity": equity, "trades": [], "curve": [equity], "open": 0}

    from collections import Counter

    ends = Counter(p["dates"][-1] for p in panels.values())
    anchor = ends.most_common(1)[0][0]
    clock_src = panels.get("SPY")
    if clock_src is None or clock_src["dates"][-1] != anchor:
        clock_src = next(
            p for p in panels.values() if p["dates"][-1] == anchor and len(p["dates"]) >= sessions
        )
    clock = list(clock_src["dates"][-sessions:])
    if len(clock) < 5:
        return {"equity": equity, "trades": [], "curve": [equity], "open": 0}
    full_dates = {clock[-1]} if full_last else set()

    done = 0
    total = len(panels)
    if progress:
        progress(f"names {total} sessions {len(clock)}")
    for panel in panels.values():
        done += 1
        if progress and (done % 250 == 0 or done == total):
            progress(f"signals {done}/{total}")
        closes = panel["closes"]
        at = {d: i for i, d in enumerate(panel["dates"])}
        sig: dict[str, tuple] = {}
        for d in clock:
            t = at.get(d)
            if t is None or t < 20:
                continue
            p_up = walk_forward_p_up(closes, t)
            sizes = move_sizes(closes, t)
            if p_up is None or sizes is None or closes[t] <= 0:
                continue
            mom = 0.0
            if t >= 5 and closes[t - 5] > 0:
                mom = closes[t] / closes[t - 5] - 1.0
            sig[d] = (float(p_up), float(sizes[0]), float(sizes[1]), float(closes[t]), mom)
        panel["sig"] = sig

    cash = float(equity)
    weights = {**_WEIGHT, **(start_weights or {})}
    lots: dict[str, dict] = {}
    trades: list[dict] = []
    learns: list[dict] = []
    curve = [cash]
    last_px = {sym: float(panel["closes"][-1]) for sym, panel in panels.items()}
    desk_rounds = 0
    screened = 0
    convened = 0
    census = {"LONG": 0, "FLAT": 0, "SHORT": 0, "veto": {}, "n": 0, "no_signal": 0}
    sec_sum: dict[str, float] = {}
    wanted: list[dict] = []

    def _mark(i_date: str) -> float:
        return cash + sum(
            lot["qty"] * float(last_px.get(sym, lot["entry"])) for sym, lot in lots.items()
        )

    def _close(sym: str, i: int, d: str, px: float, reason: str) -> None:
        nonlocal cash
        lot = lots.pop(sym)
        gain = (px - lot["entry"]) / lot["entry"]
        cash += lot["qty"] * px
        rec = {
            "t": i,
            "date": d,
            "symbol": sym,
            "side": "SELL",
            "reason": reason,
            "px": px,
            "gain": gain,
            "entry": lot["entry"],
            "entry_t": lot["entry_t"],
            "dollar": lot["qty"] * (px - lot["entry"]),
            "p_up": lot.get("p_up"),
            "mom": lot.get("mom"),
            "sections": lot.get("sections") or {},
        }
        trades.append(rec)
        if learn is not None:
            extra = {
                "p_up": lot.get("p_up"),
                "mom": lot.get("mom"),
                "entry_t": lot.get("entry_t"),
                "t": i,
                "reason": reason,
            }
            try:
                learns.append(learn(sym, gain, extra))
            except TypeError:
                learns.append(learn(sym, gain))
        nudged = nudge_weights(dict(weights), lot["sections"], gain)
        weights.clear()
        weights.update(nudged)

    for i, d in enumerate(clock):
        for sym in list(lots):
            sig = panels[sym]["sig"].get(d)
            if not sig:
                continue
            px = float(sig[3])
            last_px[sym] = px
            lot = lots[sym]
            gain = (px - lot["entry"]) / lot["entry"]
            held_bars = i - int(lot["entry_t"])
            if gain <= -float(lot["stop"]):
                _close(sym, i, d, px, "stop")
            elif held_bars >= int(lot["horizon"]):
                _close(sym, i, d, px, "horizon")
        full = d in full_dates
        cands: list[tuple] = []
        marked = _mark(d)
        deployed = 0.0 if marked <= 0 else (marked - cash) / marked
        for sym, panel in panels.items():
            held_now = sym in lots
            sig = panel["sig"].get(d)
            if not sig:
                if full:
                    census["no_signal"] += 1
                continue
            p_up, avg_up, avg_down, px, mom = sig
            ev = one_bar_ev(p_up, avg_up, avg_down, cost)
            if held_now and not full:
                continue
            if not full and not (p_up >= 0.50 and ev > 0):
                screened += 1
                continue
            order = convene(
                {
                    "p_up": p_up,
                    "avg_up": avg_up,
                    "avg_down": avg_down,
                    "exec_conf": p_up,
                    "held": False,
                    "deployed_frac": deployed,
                },
                weights=weights,
                record=False,
            )
            convened += 1
            desk_rounds += int(order.get("n_desks") or 0) * 2
            if full:
                action = str(order.get("action") or "FLAT")
                census[action] = int(census.get(action, 0)) + 1
                census["n"] += 1
                veto = order.get("veto") or "none"
                census["veto"][veto] = int(census["veto"].get(veto, 0)) + 1
                for name, info in (order.get("sections") or {}).items():
                    sec_sum[name] = sec_sum.get(name, 0.0) + float((info or {}).get("round2") or 0.0)
                if action == "LONG":
                    wanted.append(
                        {
                            "symbol": sym,
                            "score": float(order.get("score") or 0.0),
                            "p_up": p_up,
                            "stop": float(order.get("stop") or 0.0),
                            "horizon": int(order.get("horizon_days") or 0),
                        }
                    )
            # A fat down-day is how the book filled itself with whip names.
            # The chair can still say long. The book will not buy that tape.
            if avg_down > 0.025:
                continue
            if held_now or order.get("action") != "LONG" or ev <= 0:
                continue
            cands.append(
                (
                    float(order.get("score") or 0.0),
                    -float(avg_down),
                    float(p_up),
                    sym,
                    order,
                    px,
                    mom,
                )
            )
        # Tied chair scores used to fall through to the fattest move, which
        # clustered on a handful of wild tickers. Prefer the calmer down-day.
        cands.sort(reverse=True)
        for score, _calm, p_up, sym, order, px, mom in cands:
            if len(lots) >= max_names or cash <= 1:
                break
            marked = _mark(d)
            notion = order_notional(
                marked,
                cash / (1.0 + cost),
                ticket=ticket * float(order.get("size_mult") or 1.0),
            )
            if notion < 1 or px <= 0:
                continue
            qty = notion / px
            cash -= notion * (1.0 + cost)
            last_px[sym] = px
            lots[sym] = {
                "qty": qty,
                "entry": px,
                "entry_t": i,
                "stop": float(order.get("stop") or 0.02),
                "horizon": max(1, int(order.get("horizon_days") or 5)),
                "sections": order.get("sections") or {},
                "p_up": p_up,
                "mom": mom,
            }
            trades.append(
                {
                    "t": i,
                    "date": d,
                    "symbol": sym,
                    "side": "BUY",
                    "px": px,
                    "qty": qty,
                    "p_up": p_up,
                    "score": score,
                    "horizon": lots[sym]["horizon"],
                    "stop": lots[sym]["stop"],
                    "n_desks": order.get("n_desks"),
                }
            )
        curve.append(_mark(d))

    # A 60-day hold cannot finish inside this window, so only stops were
    # closing. Mark what is still open or the book learns losses alone.
    if flatten and lots and clock:
        last_i = len(clock) - 1
        last_d = clock[-1]
        for sym in list(lots):
            px = float(last_px.get(sym) or lots[sym]["entry"])
            _close(sym, last_i, last_d, px, "mark")
        curve.append(cash)

    open_lots = {}
    for sym, lot in lots.items():
        px = float(last_px.get(sym, lot["entry"]))
        open_lots[sym] = {
            "qty": lot["qty"],
            "entry": lot["entry"],
            "entry_t": lot["entry_t"],
            "stop": lot["stop"],
            "horizon": lot["horizon"],
            "p_up": lot.get("p_up"),
            "last": px,
            "gain": (px - lot["entry"]) / lot["entry"] if lot["entry"] else 0.0,
            "dollar": lot["qty"] * (px - lot["entry"]),
        }
    n_sec = max(1, census["n"])
    sections = {name: sec_sum[name] / n_sec for name in sec_sum}
    sells = [t for t in trades if t["side"] == "SELL"]
    wins = [t for t in sells if float(t["gain"]) > 0]
    wanted.sort(key=lambda row: row["score"], reverse=True)
    return {
        "equity": curve[-1] if curve else equity,
        "cash": cash,
        "start": equity,
        "trades": trades,
        "curve": curve,
        "dates": clock,
        "weights": weights,
        "learns": learns,
        "open": len(lots),
        "lots": open_lots,
        "names": len(panels),
        "desk_rounds": desk_rounds,
        "convened": convened,
        "screened": screened,
        "census": census,
        "sections": sections,
        "wanted": wanted[:12],
        "closed": len(sells),
        "wins": len(wins),
        "asof": clock[-1],
    }
