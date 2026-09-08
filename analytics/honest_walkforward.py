"""Walk-forward on lagged features only — no future leak, no in-sample map.

Economics, not slogans:
  - Expected value after costs can be negative. A random walk + friction is red.
  - Labels are the *next* bar. Features at t use only data ≤ t.
  - News is filtered as_of the signal date.
  - One trade per (symbol, bar). No retries, no relabeling a loss as a win.

This module never claims a guaranteed green book. If the sim is red, it
records why (friction, hit rate, look-ahead would have faked a win).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

from analytics.asymmetric_loss import asymmetric_reward
from analytics.honest_learn import credit_once, trade_key
from intel.point_in_time import filter_items_as_of


@dataclass
class WalkForwardReport:
    n_bars: int
    n_trades: int
    n_skipped_dup: int
    gross_pnl: float
    net_pnl: float
    hit_rate: float
    mean_reward: float
    leak_pnl: float
    leak_beats_honest: bool
    red: bool
    why_red: str
    notes: str


FRICTION = 0.0005  # 5 bps round-trip — realistic, not zero


def lagged_edge(returns: pd.Series) -> pd.Series:
    """Simple momentum: yesterday's return. Never today's, never tomorrow's."""
    return returns.shift(1).fillna(0.0)


def leaked_edge(returns: pd.Series) -> pd.Series:
    """Cheat map: tomorrow's return as today's feature. Forbidden in live/hist."""
    return returns.shift(-1).fillna(0.0)


def _one_pass(
    returns: pd.Series,
    edge: pd.Series,
    *,
    symbol: str,
    allow_retry: bool,
    news_by_bar: list[list[dict]] | None = None,
) -> tuple[list[float], list[float], int]:
    """Long when lagged edge > 0. One fill per bar unless allow_retry (cheat)."""
    pnls: list[float] = []
    rewards: list[float] = []
    skipped = 0
    credited: set[str] = set()
    for i in range(1, len(returns) - 1):
        as_of = str(returns.index[i].date()) if hasattr(returns.index[i], "date") else str(i)
        if news_by_bar is not None:
            # Hist news already clamped; future headlines must not appear here.
            kept = filter_items_as_of(news_by_bar[i], as_of)
            if any(not filter_items_as_of([it], as_of) for it in news_by_bar[i]):
                # Caller passed a future item; we drop it. Do not trade on it.
                pass
            _ = kept
        sig = float(edge.iloc[i])
        if sig <= 0:
            continue
        key = trade_key(symbol, entry_ts=as_of, side="LONG")
        if (not allow_retry) and key in credited:
            skipped += 1
            continue
        ret = float(returns.iloc[i + 1])  # next bar only
        net = ret - FRICTION
        rw = asymmetric_reward("LONG", net, bars_held=1)
        if allow_retry:
            pnls.append(net)
            rewards.append(float(rw.reward))
            credited.add(key)
            continue
        applied = credit_once(key, lambda n=net, r=rw: (n, r))
        if not applied.get("applied"):
            skipped += 1
            continue
        credited.add(key)
        pnls.append(net)
        rewards.append(float(rw.reward))
    return pnls, rewards, skipped


def run_synthetic(
    *,
    n: int = 250,
    seed: int = 7,
    symbol: str = "SYN",
) -> WalkForwardReport:
    rng = np.random.default_rng(seed)
    # Zero-drift random walk — fair coin, not a planted winner.
    rets = pd.Series(rng.normal(0.0, 0.01, n), index=pd.date_range("2024-01-02", periods=n, freq="B"))
    honest_e = lagged_edge(rets)
    leak_e = leaked_edge(rets)
    h_pnl, h_rw, skipped = _one_pass(rets, honest_e, symbol=symbol, allow_retry=False)
    leak_pnl, _, _ = _one_pass(rets, leak_e, symbol=f"{symbol}_LEAK", allow_retry=False)
    gross = float(sum(h_pnl) + FRICTION * len(h_pnl)) if h_pnl else 0.0
    net = float(sum(h_pnl)) if h_pnl else 0.0
    leak_net = float(sum(leak_pnl)) if leak_pnl else 0.0
    hits = sum(1 for x in h_pnl if x > 0)
    red = net < 0
    why = ""
    if red:
        why = (
            f"honest net={net:.4f} after {FRICTION:.4f} friction/trade on {len(h_pnl)} "
            f"lagged-momentum longs; hit_rate={hits / max(1, len(h_pnl)):.2f}. "
            "Zero-drift + costs is the base case — we do not relabel or retry."
        )
    return WalkForwardReport(
        n_bars=n,
        n_trades=len(h_pnl),
        n_skipped_dup=skipped,
        gross_pnl=gross,
        net_pnl=net,
        hit_rate=hits / max(1, len(h_pnl)),
        mean_reward=float(np.mean(h_rw)) if h_rw else 0.0,
        leak_pnl=leak_net,
        leak_beats_honest=leak_net > net + 1e-12,
        red=red,
        why_red=why,
        notes="lagged momentum; next-bar label; as_of news; one credit per bar",
    )


def report_dict(rep: WalkForwardReport) -> dict[str, Any]:
    return asdict(rep)
