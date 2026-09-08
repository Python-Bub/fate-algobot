import requests
from utils import log

IBKR_BASE_URL = "https://localhost:5000/v1/api"

def check_gateway_status():
    try:
        r = requests.get(f"{IBKR_BASE_URL}/iserver/auth/status", verify=False)
        return r.json()
    except Exception as e:
        log.error(f"[IBKR] Gateway status failed: {e}")
        return {}

def get_account_summary():
    try:
        r = requests.get(f"{IBKR_BASE_URL}/portfolio/accounts", verify=False)
        return r.json()
    except Exception as e:
        log.error(f"[IBKR] Account summary failed: {e}")
        return []

def get_conid(symbol: str):
    try:
        r = requests.get(f"{IBKR_BASE_URL}/iserver/secdef/search?symbol={symbol}", verify=False)
        return r.json()[0]["conid"]
    except Exception as e:
        log.error(f"[IBKR] Conid lookup failed for {symbol}: {e}")
        return None

def submit_order(symbol: str, action: str, quantity: int, order_type: str = "MKT"):
    conid = get_conid(symbol)
    if not conid:
        log.error(f"[IBKR] No conid available for {symbol}. Order aborted.")
        return {}

    payload = {
        "conid": conid,
        "orderType": order_type,
        "side": action.lower(),
        "quantity": quantity,
        "tif": "DAY"
    }

    try:
        r = requests.post(f"{IBKR_BASE_URL}/iserver/account/orders", json=payload, verify=False)
        return r.json()
    except Exception as e:
        log.error(f"[IBKR] Order failed: {e}")
        return {}
