"""Fill / quote slippage audit — logs expected vs submitted price in bps."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from utils import log

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "data" / "journal" / "slippage_audit.jsonl"


def _enabled() -> bool:
    return os.getenv("SLIPPAGE_AUDIT", "true").lower() in ("1", "true", "yes")


def _path() -> Path:
    return Path(os.getenv("SLIPPAGE_AUDIT_PATH", str(DEFAULT_PATH)))


def audit_slippage(
    symbol: str,
    side: str,
    *,
    expected_px: float | None,
    submitted_px: float | None,
    qty: float | None = None,
    notional: float | None = None,
    source: str = "alpaca",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Append one slippage audit row. Returns the row when logged."""
    if not _enabled():
        return None
    exp = float(expected_px or 0.0)
    sub = float(submitted_px or 0.0)
    if exp <= 0 or sub <= 0:
        return None
    side_u = (side or "").strip().upper()
    # Buy: paying above mid is adverse; sell: filling below mid is adverse.
    raw_bps = 10_000.0 * (sub - exp) / exp
    adverse_bps = raw_bps if side_u.startswith("B") else -raw_bps
    row: dict[str, Any] = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "symbol": str(symbol).strip().upper(),
        "side": side_u,
        "expected_px": round(exp, 6),
        "submitted_px": round(sub, 6),
        "slippage_bps": round(raw_bps, 3),
        "adverse_bps": round(adverse_bps, 3),
        "qty": qty,
        "notional": notional,
        "source": source,
    }
    if extra:
        row.update(extra)
    try:
        p = _path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
    except Exception as e:
        log.debug("[SLIPPAGE_AUDIT] write failed: %s", e)
        return row
    warn = float(os.getenv("SLIPPAGE_AUDIT_WARN_BPS", "25") or 25)
    if abs(adverse_bps) >= warn:
        log.warning(
            "[SLIPPAGE_AUDIT] %s %s adverse=%.1fbps expected=%.4f submitted=%.4f",
            row["symbol"],
            side_u,
            adverse_bps,
            exp,
            sub,
        )
    else:
        log.info(
            "[SLIPPAGE_AUDIT] %s %s adverse=%.1fbps",
            row["symbol"],
            side_u,
            adverse_bps,
        )
    return row
