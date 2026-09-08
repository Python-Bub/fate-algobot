"""Institutional stake / 13F / activist flow — Pershing Square, Ackman, etc.

Detects high-conviction fund stake disclosures from headlines and persists them so
long-horizon scoring still reflects the signal after headlines roll off the feed.
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "intel" / "institutional_flow_state.json"

# Well-known long-only / activist managers (headline substring match).
_KNOWN_MANAGERS: tuple[str, ...] = (
    "pershing square",
    "bill ackman",
    "berkshire hathaway",
    "warren buffett",
    "baupost",
    "seth klarman",
    "tiger global",
    "coatue",
    "viking global",
    "d1 capital",
    "lone pine",
    "third point",
    "dan loeb",
    "elliott management",
    "paul singer",
    "starboard value",
    "icahn",
    "valueact",
    "trian fund",
    "appaloosa",
    "david tepper",
    "point72",
    "steve cohen",
    "renaissance",
    "citadel",
    "millennium",
    "two sigma",
    "blackrock",
    "vanguard",
)

# Stake disclosure language (13F, new position, activist builds).
_STAKE_RE = re.compile(
    r"\b("
    r"disclos(?:es|ed|ing)\s+(?:a\s+)?(?:large\s+|new\s+|major\s+)?stake|"
    r"disclos(?:es|ed|ing)\s+(?:a\s+)?(?:new\s+)?position|"
    r"new\s+stake|large\s+stake|major\s+stake|"
    r"builds?\s+(?:a\s+)?stake|takes?\s+(?:a\s+)?stake|"
    r"initiated\s+(?:a\s+)?position|raises?\s+(?:its\s+)?position|"
    r"increased\s+(?:its\s+)?position|boosts?\s+(?:its\s+)?stake|"
    r"13f\s+filing|13-f\s+filing|"
    r"activist\s+(?:investor|fund).{0,40}(?:stake|position)|"
    r"(?:stake|position)\s+in\s+\w+|"
    r"largest\s+(?:position|holding)|"
    r"top\s+(?:holding|position)|"
    r"new\s+bet\s+on|"
    r"accumulat(?:es|ed|ing)\s+shares"
    r")\b",
    re.I,
)

# Insider selling headlines — must be checked BEFORE _STAKE_RE (EQIX-style "Insiders Sold $4m").
_INSIDER_SELL_RE = re.compile(
    r"\b("
    r"insiders?\s+sold|insider\s+sale|insider\s+sell|"
    r"(?:ceo|cfo|coo|cto|chief|president|chairman|director|officer|executive|hr).{0,50}sell|"
    r"sold\s+\$[\d.,]+\s*(?:m|million|b|billion)\s*(?:of\s+)?(?:stock|shares)?|"
    r"sells?\s+\$[\d.,]+\s*(?:m|million|b|billion)|"
    r"sells?\s+[\d,]+\s+shares|"
    r"10b5-?1|form\s+4|"
    r"officer\s+sold|executive\s+sold|"
    r"chief\s+\w+\s+officer.{0,40}sell"
    r")\b",
    re.I,
)

# Bearish institutional exits (trim / exit / cut stake).
_EXIT_RE = re.compile(
    r"\b("
    r"cuts?\s+(?:its\s+)?stake|trims?\s+(?:its\s+)?stake|"
    r"reduces?\s+(?:its\s+)?position|exits?\s+(?:its\s+)?position|"
    r"sells?\s+(?:entire\s+)?stake|dumps?\s+shares|"
    r"13f\s+.*\s+(?:cut|trim|sold|exit)"
    r")\b",
    re.I,
)

_HIGH_CONVICTION_RE = re.compile(
    r"\b(largest\s+position|top\s+holding|billion|multi-?billion|major\s+stake|"
    r"large\s+(?:new\s+)?stake|significant\s+stake|substantial\s+stake)\b",
    re.I,
)

_MEM: dict[str, Any] | None = None
_TX_CACHE: dict[str, tuple[float, list[str]]] = {}


def _enabled() -> bool:
    return os.getenv("ENABLE_INSTITUTIONAL_FLOW", "true").lower() in ("1", "true", "yes")


def _cache_ttl() -> int:
    return int(os.getenv("INSTITUTIONAL_HEADLINE_CACHE_SEC", "1800"))


def _signal_ttl_days() -> int:
    return int(os.getenv("INSTITUTIONAL_SIGNAL_TTL_DAYS", "90"))


def _load_state() -> dict[str, Any]:
    global _MEM
    if _MEM is not None:
        return _MEM
    if not STATE_PATH.is_file():
        _MEM = {"version": 1, "symbols": {}}
        return _MEM
    try:
        _MEM = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        _MEM = {"version": 1, "symbols": {}}
    return _MEM


def _save_state(doc: dict[str, Any]) -> None:
    global _MEM
    doc["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    os.replace(tmp, STATE_PATH)
    _MEM = doc


def _symbol_in_text(text: str, symbol: str) -> bool:
    sym = symbol.strip().upper()
    if not sym or not text:
        return False
    if re.search(rf"\b{re.escape(sym)}\b", text, re.I):
        return True
    # Common class-share and company-name aliases
    aliases = {
        "GOOG": ("GOOGL", "Alphabet", "Google"),
        "GOOGL": ("GOOG", "Alphabet", "Google"),
        "MSFT": ("Microsoft",),
        "AAPL": ("Apple",),
        "AMZN": ("Amazon",),
        "META": ("Facebook", "Meta Platforms"),
        "NVDA": ("Nvidia", "NVIDIA"),
        "BRK.B": ("Berkshire", "BRK.A"),
        "BRK.A": ("Berkshire", "BRK.B"),
    }
    for alt in aliases.get(sym, ()):
        if alt.upper() == alt and re.search(rf"\b{re.escape(alt)}\b", text, re.I):
            return True
        if alt.lower() in text.lower():
            return True
    return False


def _fetch_headlines(symbol: str) -> list[str]:
    sym = symbol.strip().upper()
    now = time.time()
    hit = _TX_CACHE.get(sym)
    if hit and (now - hit[0]) < _cache_ttl():
        return list(hit[1])

    headlines: list[str] = []
    try:
        from intel.headline_fetch_parallel import fetch_headline_groups_parallel

        fh, na, cr = fetch_headline_groups_parallel(sym, finnhub_limit=25, news_limit=25, cramer_limit=4)
        for grp in (fh, na, cr):
            headlines.extend(str(h)[:280] for h in grp if h)
    except Exception:
        pass

    if not headlines:
        try:
            from sentiment_pipeline import fetch_finnhub_headlines, fetch_newsapi_headlines

            headlines = fetch_finnhub_headlines(sym) or fetch_newsapi_headlines(sym)
        except Exception:
            headlines = []

    headlines = list(dict.fromkeys(str(h).strip() for h in headlines if h))[:40]
    _TX_CACHE[sym] = (now, headlines)
    return headlines


def _scan_documents(symbol: str, documents: list[str]) -> dict[str, Any]:
    sym = symbol.strip().upper()
    hits: list[dict[str, Any]] = []
    managers: set[str] = set()
    bullish = 0
    bearish = 0
    high_conviction = False

    for doc in documents:
        text = str(doc or "").strip()
        if len(text) < 12:
            continue
        if not _symbol_in_text(text, sym):
            continue

        mgr = next((m for m in _KNOWN_MANAGERS if m in text.lower()), None)
        insider_sell = bool(_INSIDER_SELL_RE.search(text))
        stake_hit = bool(_STAKE_RE.search(text)) and not insider_sell
        exit_hit = bool(_EXIT_RE.search(text)) or insider_sell
        hc = bool(_HIGH_CONVICTION_RE.search(text))

        if insider_sell:
            bearish += 1
            hits.append({"headline": text[:240], "kind": "insider_sell", "manager": mgr})
        elif stake_hit and not exit_hit:
            bullish += 1
            if mgr:
                managers.add(mgr.title())
            if hc:
                high_conviction = True
            hits.append({"headline": text[:240], "kind": "stake", "manager": mgr, "high_conviction": hc})
        elif exit_hit:
            bearish += 1
            if mgr:
                managers.add(mgr.title())
            hits.append({"headline": text[:240], "kind": "exit", "manager": mgr})

    return {
        "hits": hits,
        "managers": sorted(managers),
        "bullish_count": bullish,
        "bearish_count": bearish,
        "high_conviction": high_conviction,
    }


def _parse_utc(dt_raw: str) -> datetime:
    raw = str(dt_raw or "")[:26].replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except Exception:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _persist_signal(sym: str, scan: dict[str, Any]) -> dict[str, Any] | None:
    if not scan.get("hits"):
        return None
    doc = _load_state()
    sym_row = doc.setdefault("symbols", {}).setdefault(sym, {"events": []})
    now = datetime.now(timezone.utc)
    events: list[dict[str, Any]] = list(sym_row.get("events") or [])

    for hit in scan["hits"][:6]:
        headline = str(hit.get("headline") or "")
        if any(str(e.get("headline") or "")[:80] == headline[:80] for e in events):
            continue
        events.append(
            {
                "headline": headline,
                "kind": hit.get("kind"),
                "manager": hit.get("manager"),
                "high_conviction": bool(hit.get("high_conviction")),
                "detected_at_utc": now.isoformat(),
            }
        )

    cutoff = now - timedelta(days=_signal_ttl_days())
    events = [e for e in events if _parse_utc(str(e.get("detected_at_utc", now.isoformat()))) >= cutoff]
    sym_row["events"] = events[-12:]
    _save_state(doc)
    return sym_row


def _active_state_boost(sym: str) -> dict[str, Any]:
    doc = _load_state()
    sym_row = (doc.get("symbols") or {}).get(sym) or {}
    events = list(sym_row.get("events") or [])
    if not events:
        return {"active_stakes": 0, "active_exits": 0, "high_conviction": False, "managers": []}

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=_signal_ttl_days())
    active = [e for e in events if _parse_utc(str(e.get("detected_at_utc", now.isoformat()))) >= cutoff]
    stakes = [e for e in active if e.get("kind") == "stake"]
    exits = [e for e in active if e.get("kind") == "exit"]
    managers = sorted({str(e.get("manager") or "").title() for e in active if e.get("manager")})
    return {
        "active_stakes": len(stakes),
        "active_exits": len(exits),
        "high_conviction": any(e.get("high_conviction") for e in stakes),
        "managers": managers,
        "events": active[-6:],
    }


def assess_institutional_flow(symbol: str, *, documents: list[str] | None = None) -> dict[str, Any]:
    """Return score/p_up deltas from institutional stake disclosures."""
    empty: dict[str, Any] = {
        "factor": 0.0,
        "score_delta": 0.0,
        "p_up_delta": 0.0,
        "boost_long": False,
        "block_long": False,
        "institutional_hits": [],
        "managers": [],
        "high_conviction": False,
        "source": "none",
    }
    if not _enabled():
        return empty

    sym = symbol.strip().upper()
    docs = list(documents or [])
    if not docs:
        docs = _fetch_headlines(sym)

    scan = _scan_documents(sym, docs)
    if scan["hits"]:
        _persist_signal(sym, scan)

    state = _active_state_boost(sym)
    bullish = int(scan.get("bullish_count") or 0) + int(state.get("active_stakes") or 0)
    bearish = int(scan.get("bearish_count") or 0) + int(state.get("active_exits") or 0)
    high_conviction = bool(scan.get("high_conviction") or state.get("high_conviction"))
    managers = sorted(set((scan.get("managers") or []) + (state.get("managers") or [])))

    if bullish == 0 and bearish == 0:
        return empty

    raw = min(1.0, 0.35 * bullish - 0.30 * bearish)
    if high_conviction:
        raw = min(1.0, raw + 0.25)
    if managers:
        raw = min(1.0, raw + 0.08)

    w_score = float(os.getenv("RANK_W_INSTITUTIONAL", "0.20"))
    w_p = float(os.getenv("INSTITUTIONAL_P_UP_DELTA_SCALE", "0.05"))
    hc_p = float(os.getenv("INSTITUTIONAL_HC_P_UP_BOOST", "0.04"))
    hc_s = float(os.getenv("INSTITUTIONAL_HC_SCORE_BOOST", "0.22"))

    p_delta = w_p * raw
    s_delta = w_score * raw
    boost_long = raw >= float(os.getenv("INSTITUTIONAL_BOOST_MIN_FACTOR", "0.25"))
    if high_conviction and bullish > bearish:
        p_delta += hc_p
        s_delta += hc_s
        boost_long = True

    hits = list(scan.get("hits") or []) + list(state.get("events") or [])
    hits = hits[:8]

    return {
        **empty,
        "factor": raw,
        "score_delta": s_delta,
        "p_up_delta": p_delta,
        "boost_long": boost_long,
        "institutional_hits": hits,
        "managers": managers,
        "high_conviction": high_conviction,
        "bullish_count": bullish,
        "bearish_count": bearish,
        "source": "headlines+state" if state.get("active_stakes") else "headlines",
    }


def institutional_flow_factor(ticker: str) -> float:
    return float(assess_institutional_flow(ticker).get("factor") or 0.0)
