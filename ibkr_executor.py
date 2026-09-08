"""
Place orders via ib_insync (TWS / IB Gateway socket API).

Requires: TWS or Gateway running, API enabled, correct port.
Paper default 7497; many live setups use 7496 (confirm in your TWS settings).
"""

from __future__ import annotations

import os

from ib_insync import IB, MarketOrder, Stock

from config import IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID
from utils import log


def connect_ib() -> IB:
    ib = IB()
    cid = int(os.getenv("IBKR_CLIENT_ID", str(IBKR_CLIENT_ID)))
    ib.connect(IBKR_HOST, IBKR_PORT, clientId=cid)
    return ib


def place_market_order(ib: IB, symbol: str, quantity: int, action: str) -> bool:
    """
    action: 'BUY' or 'SELL'
    """
    if quantity <= 0:
        log.warning("[EXEC] quantity<=0, skip %s", symbol)
        return False
    contract = Stock(symbol, "SMART", "USD")
    ib.qualifyContracts(contract)
    side = action.upper()
    if side not in ("BUY", "SELL"):
        raise ValueError(action)
    if side == "BUY":
        from intel.algo_risk_filter import gate_buy_order

        if not gate_buy_order(symbol, source="ibkr"):
            return False
    order = MarketOrder(side, quantity)
    ib.placeOrder(contract, order)
    log.warning("[EXEC] Submitted %s %s x%s — verify fills in TWS", side, symbol, quantity)
    return True
