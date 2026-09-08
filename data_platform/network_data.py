"""Network-first data policy — fetch prices/bars from APIs instead of duplicating on disk."""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def network_first() -> bool:
    return os.getenv("NETWORK_FIRST", "false").lower() in ("1", "true", "yes")


def use_price_cache() -> bool:
    """Read OHLCV from disk cache (safe even when NETWORK_FIRST limits writes)."""
    return os.getenv("USE_PRICE_CACHE", "false").lower() in ("1", "true", "yes")


def save_price_cache() -> bool:
    """Append fresh bars to disk — off when NETWORK_FIRST to avoid huge duplication."""
    if not use_price_cache():
        return False
    if network_first() and os.getenv("NETWORK_FIRST_ALLOW_PRICE_WRITES", "false").lower() not in (
        "1",
        "true",
        "yes",
    ):
        return os.getenv("PAPER_SIM_SAVE_PRICE_CACHE", "true").lower() in ("1", "true", "yes")
    return True


def use_replay_raw_first() -> bool:
    if network_first():
        return False
    return os.getenv("USE_REPLAY_RAW_FIRST", "false").lower() in ("1", "true", "yes")


def save_replay_features() -> bool:
    if network_first():
        return False
    return os.getenv("SAVE_REPLAY_FEATURES", "false").lower() in ("1", "true", "yes")


def intraday_bar_cache() -> bool:
    if network_first():
        return False
    return os.getenv("INTRADAY_USE_CACHE", "false").lower() in ("1", "true", "yes")


def save_replay_raw() -> bool:
    if network_first():
        return False
    return os.getenv("DATA_SYNC_SAVE_RAW", "false").lower() in ("1", "true", "yes")


def skip_intraday_placeholder_disk() -> bool:
    return os.getenv("INTRADAY_SKIP_PLACEHOLDER_DISK", "true").lower() in ("1", "true", "yes")


PLACEHOLDER_REG = ROOT / "data" / "intraday_placeholder_registry.json"


def register_intraday_placeholder(symbol: str, reason: str, *, rows: int = 0) -> None:
    sym = symbol.strip().upper()
    PLACEHOLDER_REG.parent.mkdir(parents=True, exist_ok=True)
    doc: dict = {}
    if PLACEHOLDER_REG.is_file():
        try:
            doc = json.loads(PLACEHOLDER_REG.read_text(encoding="utf-8"))
        except Exception:
            doc = {}
    entries = doc.get("symbols") or {}
    if not isinstance(entries, dict):
        entries = {}
    entries[sym] = {"reason": reason, "rows": int(rows)}
    doc["symbols"] = entries
    tmp = PLACEHOLDER_REG.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=0), encoding="utf-8")
    os.replace(tmp, PLACEHOLDER_REG)


def intraday_placeholder_registered(symbol: str) -> dict | None:
    sym = symbol.strip().upper()
    if not PLACEHOLDER_REG.is_file():
        return None
    try:
        doc = json.loads(PLACEHOLDER_REG.read_text(encoding="utf-8"))
        ent = (doc.get("symbols") or {}).get(sym)
        return ent if isinstance(ent, dict) else None
    except Exception:
        return None
