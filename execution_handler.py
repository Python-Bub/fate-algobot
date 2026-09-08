"""
Limit-at-mid execution + simple TWAP slice helper (IBKR via ib_insync).
"""

from __future__ import annotations

import os
import time
from typing import Optional

from ib_insync import IB, LimitOrder, MarketOrder, Stock, Ticker

from utils import log


def mid_price(ticker: Ticker) -> Optional[float]:
    b, a = ticker.bid, ticker.ask
    if b and a and b > 0 and a > 0:
        return (b + a) / 2
    if ticker.last:
        return float(ticker.last)
    return None


def place_limit_mid(
    ib: IB,
    symbol: str,
    qty: int,
    action: str,
    wait_sec: float = 30.0,
    repost_sec: float = 30.0,
    _depth: int = 0,
) -> None:
    if _depth > int(os.getenv("EXEC_MAX_REPOSTS", "5")):
        log.error("[EXEC] Max reposts — abort %s", symbol)
        return
    contract = Stock(symbol, "SMART", "USD")
    ib.qualifyContracts(contract)
    t = ib.reqMktData(contract, "", False, False)
    ib.sleep(0.5)
    m = mid_price(t)
    ib.cancelMktData(contract)
    if m is None:
        log.warning("[EXEC] No bid/ask for %s — market order fallback", symbol)
        ib.placeOrder(contract, MarketOrder(action.upper(), qty))
        return
    px = round(m, 2)
    order = LimitOrder(action.upper(), qty, px)
    trade = ib.placeOrder(contract, order)
    log.info("[EXEC] Limit %s %s @ %.2f", action, symbol, px)
    deadline = time.time() + wait_sec
    while time.time() < deadline and not trade.isDone():
        ib.sleep(1)
    if not trade.isDone():
        ib.cancelOrder(order)
        log.info("[EXEC] Repost limit in %.0fs…", repost_sec)
        ib.sleep(repost_sec)
        place_limit_mid(ib, symbol, qty, action, wait_sec, repost_sec, _depth=_depth + 1)


def twap_slices(
    ib: IB,
    symbol: str,
    total_qty: int,
    action: str,
    n_slices: int,
    pause_sec: float = 60.0,
) -> None:
    q_each = max(1, total_qty // n_slices)
    rest = total_qty
    for i in range(n_slices):
        q = min(q_each, rest)
        if q <= 0:
            break
        place_limit_mid(ib, symbol, q, action, wait_sec=25.0, repost_sec=25.0)
        rest -= q
        if rest <= 0:
            break
        ib.sleep(pause_sec)
