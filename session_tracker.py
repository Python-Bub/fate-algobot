import json
import os
from datetime import datetime

PERSIST_FILE = "session_data.json"

# load or initialize
if os.path.exists(PERSIST_FILE):
    with open(PERSIST_FILE, "r") as f:
        data = json.load(f)
else:
    data = {
        "initialNetLiquidation": None,
        "trades": []
    }

def _reload_data():
    """Re-import file so we merge child-process logs before saving."""
    global data
    if os.path.exists(PERSIST_FILE):
        with open(PERSIST_FILE, "r") as f:
            data = json.load(f)

def save():
    with open(PERSIST_FILE, "w") as f:
        json.dump(data, f, indent=2)

def set_initial_balance(net_liq):
    _reload_data()
    if data["initialNetLiquidation"] is None:
        data["initialNetLiquidation"] = round(net_liq, 2)
        save()

def log_trade(ticker, pnl):
    """Call this for each executed trade with real pnl != 0."""
    _reload_data()
    record = {
        "timestamp": datetime.utcnow().isoformat(),
        "ticker": ticker,
        "pnl": round(pnl, 2)
    }
    data["trades"].append(record)
    save()

def get_initial_balance():
    return data["initialNetLiquidation"] or 0.0

def get_all_trades():
    _reload_data()
    return data["trades"]
