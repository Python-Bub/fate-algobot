from ib_insync import IB, Stock

from config import CLIENT_IDS, IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID
from main import run_bot
from utils import log


def run_live(ticker: str):
    client_id = CLIENT_IDS.get(ticker, IBKR_CLIENT_ID)
    ib = IB()
    ib.connect(IBKR_HOST, IBKR_PORT, clientId=client_id)

    contract = Stock(ticker, "SMART", "USD")
    ib.qualifyContracts(contract)

    market_data = ib.reqMktData(contract, "", False, False)

    while True:
        ib.sleep(2)
        live_price = market_data.last
        if live_price is not None:
            try:
                run_bot(ticker, live_price=float(live_price))
            except Exception:
                log.exception("run_bot failed for %s", ticker)
