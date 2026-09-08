#!/usr/bin/env python3
"""Quick health check for why Alpaca paper / HFT may show zero activity."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

import requests

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"
results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str, warn: bool = False) -> None:
    status = WARN if warn and ok else (PASS if ok else FAIL)
    results.append((status, name, detail))


def main() -> int:
    key = os.getenv("ALPACA_API_KEY", "")
    secret = os.getenv("ALPACA_SECRET_KEY", "") or os.getenv("ALPACA_API_SECRET", "")
    dry = os.getenv("HFT_DRY_RUN", "true").lower() in ("1", "true", "yes")
    base = "https://paper-api.alpaca.markets"
    data = os.getenv("ALPACA_DATA_URL", "https://data.alpaca.markets")

    check("HFT_DRY_RUN off", not dry, f"HFT_DRY_RUN={os.getenv('HFT_DRY_RUN', '?')}")

    # Process
    try:
        out = subprocess.check_output(["pgrep", "-fl", "obi-tape/index"], text=True, stderr=subprocess.DEVNULL)
        check("subsecond HFT process", True, out.strip() or "running")
    except subprocess.CalledProcessError:
        check("subsecond HFT process", False, "not running — run: ./run_all.sh start subsecond")

    # Alpaca clock
    if key and secret:
        try:
            r = requests.get(f"{base}/v2/clock", headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}, timeout=12)
            r.raise_for_status()
            clk = r.json()
            open_ = bool(clk.get("is_open"))
            check("Alpaca market open", open_, f"is_open={open_} next_open={clk.get('next_open')}", warn=not open_)
        except Exception as e:
            check("Alpaca clock", False, str(e))

        try:
            r = requests.get(f"{base}/v2/account", headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}, timeout=12)
            r.raise_for_status()
            acct = r.json()
            bp = float(acct.get("buying_power", 0))
            eq = float(acct.get("equity", 0))
            check("Buying power > $500", bp > 500, f"buying_power=${bp:,.2f} equity=${eq:,.2f}", warn=bp <= 500)
        except Exception as e:
            check("Alpaca account", False, str(e))

        try:
            r = requests.get(
                f"{base}/v2/orders",
                headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret},
                params={"status": "open", "limit": 50},
                timeout=12,
            )
            r.raise_for_status()
            orders = r.json() if isinstance(r.json(), list) else []
            check("Open orders not choking account", len(orders) < 30, f"{len(orders)} open orders (cancel stale to free BP)", warn=len(orders) >= 10)
        except Exception as e:
            check("Open orders", False, str(e))

        try:
            r = requests.get(
                f"{data}/v2/stocks/quotes/latest",
                headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret},
                params={"symbols": "SPY", "feed": "iex"},
                timeout=12,
            )
            r.raise_for_status()
            q = r.json().get("quotes", {}).get("SPY", {})
            bp, ap = float(q.get("bp", 0)), float(q.get("ap", 0))
            spread_bps = ((ap - bp) / ((ap + bp) / 2)) * 10_000 if ap > bp > 0 else 9999
            check("IEX quote feed", ap > 0 and bp > 0, f"SPY bid={bp} ask={ap} spread_bps={spread_bps:.1f}")
        except Exception as e:
            check("IEX quote feed", False, str(e))
    else:
        check("Alpaca keys", False, "ALPACA_API_KEY / ALPACA_SECRET_KEY missing in .env")

    # Models / neural
    n_pkl = len(list((ROOT / "models").glob("*_model.pkl")))
    n_lstm = len(list((ROOT / "models/lstm").glob("*.pt"))) if (ROOT / "models/lstm").is_dir() else 0
    check("Daily sklearn models", n_pkl > 100, f"{n_pkl} bundled *_model.pkl (tree/linear, not live HFT)")
    check("LSTM neural checkpoints", n_lstm > 0, f"{n_lstm} PyTorch .pt in models/lstm/", warn=n_lstm < 10)

    try:
        import torch

        check("PyTorch available", True, torch.__version__)
    except ImportError:
        check("PyTorch available", False, "pip install torch to train/use LSTM head")

    # Latest HFT log
    log_link = ROOT / "logs/subsecond-obi_latest.log"
    if log_link.is_file() or log_link.is_symlink():
        log_path = log_link.resolve()
        text = log_path.read_text(errors="replace")
        tail = text[-12000:]
        has_fire = "FIRE" in tail
        has_reject = "place-reject" in tail
        has_ws = "ws-open" in text
        check("Log: websocket connected", has_ws, str(log_path.name))
        check("Log: recent FIRE", has_fire, "signals firing" if has_fire else "no FIRE in tail — feed quiet or gates")
        if has_reject:
            for line in text.splitlines():
                if "insufficient buying power" in line:
                    results.append((WARN, "Log: buying power", "403 insufficient buying power in log"))
                    break
                if "Headers Timeout" in line:
                    results.append((WARN, "Log: API timeout", "Alpaca paper API slow/overloaded"))
                    break
    else:
        check("HFT log", False, "no logs/subsecond-obi_latest.log")

    print("\n=== FATE_AlgoBot paper / HFT diagnosis ===\n")
    for status, name, detail in results:
        print(f"  [{status:4}] {name}")
        print(f"         {detail}\n")

    fails = sum(1 for s, _, _ in results if s == FAIL)
    warns = sum(1 for s, _, _ in results if s == WARN)
    print(f"Summary: {fails} fail, {warns} warn, {len(results) - fails - warns} pass\n")
    print("HFT subsecond = rule-based OBI+tape (Node). NOT neural nets.")
    print("Neural: optional LSTM (PyTorch) blends into daily paper_sim; main models = sklearn bundles.\n")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
