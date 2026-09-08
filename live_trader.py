#!/usr/bin/env python3
import time
import logging

from ib_insync import IB, Stock

from config import TICKERS, IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID
from main import run_bot

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def run_live_trading(interval_sec: int = 60):
    ib = IB()
    try:
        log.info("Connecting to IBKR at %s:%s…", IBKR_HOST, IBKR_PORT)
        ib.connect(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)
        log.info("Connected to IBKR API")
    except Exception as e:
        log.error("Connection failed: %s", e)
        return

    last_run = {s: 0.0 for s in TICKERS}

    for sym in TICKERS:
        contract = Stock(sym, "SMART", "USD")
        ib.qualifyContracts(contract)
        ticker = ib.reqMktData(contract, "", False, False)

        def make_handler(s):
            def on_tick(_tick):
                price = ticker.last
                now = time.time()
                if price is None or (now - last_run[s] < interval_sec):
                    return
                last_run[s] = now
                log.info("%s tick @ $%.2f", s, float(price))
                try:
                    pnl = run_bot(s, live_price=float(price))
                    log.info("→ PnL placeholder: %.2f", pnl)
                except Exception:
                    log.exception("Error running bot on %s", s)

            return on_tick

        ticker.updateEvent += make_handler(sym)

    log.info("Live trading loop started. Press Ctrl+C to stop.")
    ib.run()
