"""
Post-trade journal: CSV + optional SQLite with regime, rationale, MFE.
"""

from __future__ import annotations

import csv
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def _utc_iso() -> str:
    """Naive-UTC ISO string (same shape as the retired datetime.utcnow())."""
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


JOURNAL_DECISIONS = Path(os.getenv("TRADE_DECISIONS_JSONL", "data/journal/decisions.jsonl"))
JOURNAL_CSV = Path(os.getenv("TRADE_JOURNAL_CSV", "data/journal/trades.csv"))
JOURNAL_SQLITE = Path(os.getenv("TRADE_JOURNAL_SQLITE", "data/journal/trades.db"))


def log_decision(payload: dict) -> None:
    """Append one decision/order lifecycle record (full precision, no rounding)."""
    try:
        import json

        JOURNAL_DECISIONS.parent.mkdir(parents=True, exist_ok=True)
        row = {"ts": _utc_iso(), **payload}
        with open(JOURNAL_DECISIONS, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, default=str) + "\n")
    except Exception:
        pass


def _ensure():
    JOURNAL_CSV.parent.mkdir(parents=True, exist_ok=True)
    if not JOURNAL_CSV.is_file():
        with open(JOURNAL_CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(
                [
                    "ts",
                    "symbol",
                    "side",
                    "qty",
                    "entry",
                    "exit",
                    "pnl",
                    "mfe",
                    "regime",
                    "vix",
                    "model_p",
                    "sentiment",
                    "notes",
                ]
            )


def _sqlite_log(
    symbol: str,
    side: str,
    qty: int,
    entry: float,
    exit_px: float,
    pnl: float,
    mfe: float,
    regime: str,
    vix: float,
    model_p: float,
    sentiment: float,
    notes: str,
) -> None:
    if os.getenv("USE_SQLITE_JOURNAL", "false").lower() not in ("1", "true", "yes"):
        return
    JOURNAL_SQLITE.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(JOURNAL_SQLITE)
    con.execute(
        """CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, symbol TEXT, side TEXT, qty INTEGER,
            entry REAL, exit_px REAL, pnl REAL, mfe REAL,
            regime TEXT, vix REAL, model_p REAL, sentiment REAL, notes TEXT)"""
    )
    con.execute(
        "INSERT INTO trades VALUES (NULL,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            _utc_iso(),
            symbol,
            side,
            qty,
            entry,
            exit_px,
            pnl,
            mfe,
            regime,
            vix,
            model_p,
            sentiment,
            notes,
        ),
    )
    con.commit()
    con.close()


def log_trade(
    symbol: str,
    side: str,
    qty: int,
    entry: float,
    exit_px: float,
    pnl: float,
    mfe: float,
    regime: str,
    vix: float,
    model_p: float,
    sentiment: float,
    notes: str = "",
) -> None:
    try:
        _ensure()
        with open(JOURNAL_CSV, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(
                [
                    _utc_iso(),
                    symbol,
                    side,
                    qty,
                    f"{entry:.4f}",
                    f"{exit_px:.4f}",
                    f"{pnl:.4f}",
                    f"{mfe:.4f}",
                    regime,
                    f"{vix:.2f}",
                    f"{model_p:.4f}",
                    f"{sentiment:.4f}",
                    notes,
                ]
            )
        _sqlite_log(symbol, side, qty, entry, exit_px, pnl, mfe, regime, vix, model_p, sentiment, notes)
    except Exception:
        log_decision(
            {
                "kind": "log_trade_fallback",
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "entry": entry,
                "notes": notes,
            }
        )
