"""Bridges for external platforms/workflows:
- QuantConnect signal export/import
- NinjaTrader order ticket CSV export
- Hummingbot config/command bridge (optional subprocess)
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def export_quantconnect_signals(signals: list[dict], path: str = "data/adapters/quantconnect_signals.json") -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "signals": signals,
    }
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(p)


def import_quantconnect_signals(path: str = "data/adapters/quantconnect_signals.json") -> list[dict]:
    p = Path(path)
    if not p.is_file():
        return []
    try:
        js = json.loads(p.read_text(encoding="utf-8"))
        return list(js.get("signals", []))
    except Exception:
        return []


def export_ninjatrader_orders(orders: list[dict], path: str = "data/adapters/ninjatrader_orders.csv") -> str:
    import csv

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    cols = ["ts_utc", "symbol", "action", "qty", "notional", "limit_price", "notes"]
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for o in orders:
            rec = {k: o.get(k) for k in cols}
            rec["ts_utc"] = rec.get("ts_utc") or datetime.now(timezone.utc).isoformat()
            w.writerow(rec)
    return str(p)


def hummingbot_bridge(command: str = "status", timeout_sec: int = 20) -> dict:
    """Run hummingbot command if installed and enabled."""
    if os.getenv("ENABLE_HUMMINGBOT_BRIDGE", "false").lower() not in ("1", "true", "yes"):
        return {"ok": False, "reason": "disabled"}
    exe = os.getenv("HUMMINGBOT_CMD", "hummingbot")
    try:
        out = subprocess.run(
            [exe, command],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        return {
            "ok": out.returncode == 0,
            "returncode": out.returncode,
            "stdout": out.stdout[-4000:],
            "stderr": out.stderr[-4000:],
        }
    except Exception as e:
        return {"ok": False, "reason": f"{type(e).__name__}: {e}"}

