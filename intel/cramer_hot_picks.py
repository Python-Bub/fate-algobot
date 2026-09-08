"""Explicit Cramer hot picks / push-downs — signal-only, never name favoritism.

Operator or distilled Mad Money calls land here as dated overrides. Ranking uses
tilt math only (buy = strong positive, sell = strong negative). Letter of ticker
never affects weight.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
HOT_PATH = ROOT / "data" / "intel" / "cramer_hot_picks.json"

# 2026-07-28 Mad Money / club buys (user-confirmed). High conviction.
DEFAULT_HOT: dict[str, Any] = {
    "as_of": "2026-07-28",
    "source": "operator_confirmed_mad_money",
    "note": "Jim Cramer buy mentions — signal boost only; no alphabetical bias",
    "buys": {
        "COST": {"tilt": 0.98, "label": "Costco", "conviction": "high"},
        "WMT": {"tilt": 0.95, "label": "Walmart", "conviction": "high"},
        "NOW": {"tilt": 0.92, "label": "ServiceNow", "conviction": "high"},
        "CRM": {"tilt": 0.92, "label": "Salesforce", "conviction": "high"},
        "JNJ": {"tilt": 0.90, "label": "Johnson & Johnson", "conviction": "high"},
    },
    "sells": {},
}


def _max_age_days() -> int:
    try:
        return max(1, int(os.getenv("CRAMER_HOT_MAX_AGE_DAYS", "5")))
    except ValueError:
        return 5


def _enabled() -> bool:
    return os.getenv("USE_CRAMER_HOT_PICKS", "true").lower() in ("1", "true", "yes")


def ensure_hot_file(*, force_defaults: bool = False) -> dict[str, Any]:
    """Create or refresh hot picks file; merge defaults for today's confirmed buys."""
    HOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    doc: dict[str, Any]
    if HOT_PATH.is_file() and not force_defaults:
        try:
            doc = json.loads(HOT_PATH.read_text(encoding="utf-8"))
        except Exception:
            doc = dict(DEFAULT_HOT)
    else:
        doc = dict(DEFAULT_HOT)

    buys = dict(doc.get("buys") or {})
    sells = dict(doc.get("sells") or {})
    # Always ensure today's operator-confirmed names are present at full tilt.
    for sym, meta in DEFAULT_HOT["buys"].items():
        cur = buys.get(sym) or {}
        if float(cur.get("tilt") or 0) < float(meta["tilt"]):
            buys[sym] = {**meta}
    doc["buys"] = buys
    doc["sells"] = sells
    doc["as_of"] = doc.get("as_of") or DEFAULT_HOT["as_of"]
    doc["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    HOT_PATH.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return doc


def load_hot() -> dict[str, Any]:
    if not HOT_PATH.is_file():
        return ensure_hot_file()
    try:
        return json.loads(HOT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return ensure_hot_file(force_defaults=True)


def _fresh(doc: dict[str, Any]) -> bool:
    raw = str(doc.get("as_of") or "")[:10]
    try:
        d = datetime.strptime(raw, "%Y-%m-%d").date()
    except Exception:
        return False
    return (date.today() - d).days <= _max_age_days()


def set_sell(symbol: str, *, tilt: float = -0.9, label: str = "", reason: str = "") -> None:
    """Record a Cramer-negative push-down (signal only)."""
    doc = load_hot()
    sym = symbol.strip().upper()
    sells = dict(doc.get("sells") or {})
    sells[sym] = {
        "tilt": float(max(-1.0, min(-0.05, tilt))),
        "label": label or sym,
        "conviction": "high",
        "reason": reason[:120],
    }
    # Sell overrides buy for same name
    buys = dict(doc.get("buys") or {})
    buys.pop(sym, None)
    doc["buys"] = buys
    doc["sells"] = sells
    doc["as_of"] = date.today().isoformat()
    doc["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    HOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    HOT_PATH.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def set_buy(symbol: str, *, tilt: float = 0.95, label: str = "", reason: str = "") -> None:
    doc = load_hot()
    sym = symbol.strip().upper()
    buys = dict(doc.get("buys") or {})
    buys[sym] = {
        "tilt": float(max(0.05, min(1.0, tilt))),
        "label": label or sym,
        "conviction": "high",
        "reason": reason[:120],
    }
    sells = dict(doc.get("sells") or {})
    sells.pop(sym, None)
    doc["buys"] = buys
    doc["sells"] = sells
    doc["as_of"] = date.today().isoformat()
    doc["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    HOT_PATH.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def hot_tilt_for(symbol: str) -> float:
    """Return raw tilt in [-1, 1] from hot file, or 0 if stale/disabled."""
    if not _enabled():
        return 0.0
    doc = load_hot()
    if not _fresh(doc):
        return 0.0
    sym = symbol.strip().upper()
    sells = doc.get("sells") or {}
    if sym in sells:
        return float(sells[sym].get("tilt") or -0.9)
    buys = doc.get("buys") or {}
    if sym in buys:
        return float(buys[sym].get("tilt") or 0.9)
    return 0.0


def hot_boost_for(symbol: str) -> float:
    """Bounded boost after CRAMER_HOT_BOOST_GAIN (default strong)."""
    raw = hot_tilt_for(symbol)
    if raw == 0.0:
        return 0.0
    try:
        gain = float(os.getenv("CRAMER_HOT_BOOST_GAIN", "0.95"))
    except ValueError:
        gain = 0.95
    return max(-1.0, min(1.0, raw * gain))


def ingest_hot_into_transcript() -> int:
    """Append strong buy/sell lines into CRAMER.jsonl for extract_picks path."""
    from intel.cramer_picks import ingest_text_lines

    doc = ensure_hot_file()
    if not _fresh(doc):
        return 0
    day = str(doc.get("as_of") or date.today().isoformat())[:10]
    lines: list[str] = []
    for sym, meta in (doc.get("buys") or {}).items():
        label = meta.get("label") or sym
        lines.append(
            f"Jim Cramer screaming buy buy buy ${sym} ({label}). "
            f"Must own — pounding the table on {label}."
        )
    for sym, meta in (doc.get("sells") or {}).items():
        label = meta.get("label") or sym
        lines.append(
            f"Jim Cramer sell sell sell ${sym} ({label}). "
            f"Get out now — pounding the table on selling {label}."
        )
    if not lines:
        return 0
    return ingest_text_lines(lines, ts=day, append=True)


def distill_hot_talk_pairs() -> list[tuple[str, str]]:
    """Q&A pairs for talk teacher distillation from hot picks."""
    doc = load_hot()
    pairs: list[tuple[str, str]] = []
    buys = list((doc.get("buys") or {}).keys())
    sells = list((doc.get("sells") or {}).keys())
    if buys:
        joined = ", ".join(buys)
        pairs.append(
            (
                "what did cramer buy",
                f"Recent Cramer buys with strong signal boost: {joined}.",
            )
        )
        pairs.append(
            (
                "cramer picks today",
                f"Hot Cramer buys (signal only): {joined}. Ranking uses tilt math, not ticker letters.",
            )
        )
        for s in buys:
            pairs.append((f"is {s} a cramer buy", f"Yes — {s} has a strong positive Cramer hot-pick tilt."))
            pairs.append((f"boost {s}", f"{s} receives a high Cramer signal boost while the hot file is fresh."))
    for s in sells:
        pairs.append((f"is {s} a cramer sell", f"Yes — {s} has a strong negative Cramer push-down."))
    pairs.append(
        (
            "do you prefer stocks by name",
            "No. Ranking is signal and math only. Letter of the ticker never decides weight.",
        )
    )
    return pairs
