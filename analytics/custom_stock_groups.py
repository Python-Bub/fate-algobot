"""Custom unique stock groups — every tradable name gets a meaningful group.

Layers (priority):
  1. data/industry/symbol_overrides.json
  2. industry_map / classifier (50-industry taxonomy)
  3. ETF / index / preferred heuristics (avoid unclassified dump)
  4. Yahoo sector → custom sector_* bucket (never "Unknown")
  5. last resort: custom_liquidity_<letter> (still unique, not null)

Also remaps low-confidence financial_data_exchanges catch-all when the
name is clearly not an exchange/data vendor.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from utils import log

ROOT = Path(__file__).resolve().parents[1]
GROUPS_PATH = ROOT / "data" / "industry" / "custom_unique_groups.json"
COV_PATH = ROOT / "data" / "industry" / "custom_groups_coverage.json"

_FDE_TRUE = frozenset(
    {
        "SPGI",
        "ICE",
        "CME",
        "MCO",
        "MSCI",
        "NDAQ",
        "MKTX",
        "FDS",
        "COIN",
        "CBOE",
        "TW",
    }
)

_ETF_RE = re.compile(
    r"^(SPY|QQQ|IWM|DIA|VOO|IVV|VTI|VEA|VWO|EEM|EFA|XLE|XLF|XLK|XLV|XLI|XLP|XLU|XLB|XLRE|XLC|"
    r"SMH|SOXX|XOP|USO|UNG|TLT|IEF|HYG|LQD|GLD|SLV|ARKK|TQQQ|SQQQ|UVXY|VIXY|"
    r"[A-Z]{1,5}(ETF|TRUST)?)$"
)

_MEM: dict[str, tuple[float, dict[str, Any]]] = {}

_SECTOR_TO_GROUP = {
    "energy": "custom_sector_energy",
    "financial services": "custom_sector_financials",
    "financials": "custom_sector_financials",
    "technology": "custom_sector_technology",
    "consumer cyclical": "custom_sector_consumer_cyclical",
    "consumer defensive": "custom_sector_consumer_defensive",
    "healthcare": "custom_sector_healthcare",
    "industrials": "custom_sector_industrials",
    "basic materials": "custom_sector_materials",
    "real estate": "custom_sector_real_estate",
    "utilities": "custom_sector_utilities",
    "communication services": "custom_sector_communication",
}


def _load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _yahoo_sector(symbol: str) -> str | None:
    try:
        import yfinance as yf

        info = yf.Ticker(symbol).info or {}
        sec = str(info.get("sector") or "").strip()
        return sec or None
    except Exception:
        return None


def _is_etf_like(symbol: str) -> bool:
    sym = symbol.upper()
    if sym in {"SPY", "QQQ", "IWM", "DIA", "VOO", "IVV", "VTI", "XLE", "XLF", "XLK", "XLV", "SMH", "SOXX"}:
        return True
    # structured / defined-outcome tickers often start with Z/X + month codes
    if re.match(r"^(Z|X)[A-Z]{2,4}$", sym) and sym not in _FDE_TRUE:
        # many are ETFs/notes — treat as etf_structured unless known equity
        return True
    if sym.endswith(("P", "PR", "WS")) and len(sym) >= 5:
        return False
    return False


def _preferred_or_note(symbol: str) -> str | None:
    sym = symbol.upper()
    if re.search(r"(P|PR|PA|PB|PC|PD|PE)$", sym) and len(sym) >= 5:
        return "custom_preferred_hybrid"
    if re.match(r"^FGBI", sym):
        return "custom_preferred_hybrid"
    return None


def group_for_symbol(symbol: str, *, force: bool = False) -> dict[str, Any]:
    """Return a meaningful unique group assignment (never null / Unknown)."""
    sym = symbol.strip().upper()
    now = time.time()
    ttl = float(os.getenv("CUSTOM_GROUPS_TTL_SEC", "3600"))
    if not force:
        hit = _MEM.get(sym)
        if hit and (now - hit[0]) < ttl:
            return dict(hit[1])

    overrides = (_load_json(ROOT / "data" / "industry" / "symbol_overrides.json").get("symbols") or {})
    persisted = (_load_json(GROUPS_PATH).get("symbols") or {})

    industry_id = None
    source = "none"
    confidence = 0.0

    if sym in overrides:
        industry_id = str(overrides[sym])
        source = "override"
        confidence = 0.99
    elif sym in persisted and persisted[sym].get("group_id"):
        industry_id = str(persisted[sym]["group_id"])
        source = str(persisted[sym].get("source") or "custom_cache")
        confidence = float(persisted[sym].get("confidence") or 0.8)
    else:
        try:
            from analytics.industries.classifier import classify_ticker

            row = classify_ticker(sym)
            industry_id = str(row.get("industry_id") or "") or None
            confidence = float(row.get("confidence") or 0.0)
            source = "classifier"
        except Exception:
            industry_id = None

    # Remap bogus financial_data_exchanges catch-all
    if industry_id == "financial_data_exchanges" and sym not in _FDE_TRUE and confidence < 0.90:
        pref = _preferred_or_note(sym)
        if pref:
            industry_id, source, confidence = pref, "preferred_heuristic", 0.85
        elif _is_etf_like(sym):
            industry_id, source, confidence = "custom_etf_index", "etf_heuristic", 0.88
        else:
            sec = _yahoo_sector(sym)
            if sec:
                industry_id = _SECTOR_TO_GROUP.get(sec.lower(), f"custom_sector_{re.sub(r'[^a-z0-9]+', '_', sec.lower())}")
                source, confidence = "yahoo_sector_remap", 0.75
            else:
                industry_id, source, confidence = f"custom_liquidity_{sym[0]}", "letter_bucket", 0.55

    if not industry_id or industry_id in ("unclassified", "Unknown", "unknown", "None"):
        pref = _preferred_or_note(sym)
        if pref:
            industry_id, source, confidence = pref, "preferred_heuristic", 0.85
        elif _is_etf_like(sym):
            industry_id, source, confidence = "custom_etf_index", "etf_heuristic", 0.88
        else:
            sec = _yahoo_sector(sym)
            if sec:
                industry_id = _SECTOR_TO_GROUP.get(
                    sec.lower(), f"custom_sector_{re.sub(r'[^a-z0-9]+', '_', sec.lower())}"
                )
                source, confidence = "yahoo_sector", 0.70
            else:
                industry_id, source, confidence = f"custom_liquidity_{sym[0]}", "letter_bucket", 0.50

    out = {
        "symbol": sym,
        "group_id": industry_id,
        "industry_id": industry_id,
        "source": source,
        "confidence": confidence,
        "meaningful": not str(industry_id).startswith("custom_liquidity_"),
    }
    _MEM[sym] = (now, out)
    return dict(out)


def ensure_groups(symbols: list[str], *, persist: bool = True) -> dict[str, Any]:
    """Assign groups for a symbol list; optionally persist custom_unique_groups.json."""
    doc = _load_json(GROUPS_PATH) or {"version": 1, "symbols": {}}
    doc.setdefault("symbols", {})
    assigned = 0
    meaningful = 0
    for s in symbols:
        g = group_for_symbol(s, force=True)
        doc["symbols"][s.strip().upper()] = {
            "group_id": g["group_id"],
            "industry_id": g["industry_id"],
            "source": g["source"],
            "confidence": g["confidence"],
        }
        assigned += 1
        if g.get("meaningful"):
            meaningful += 1
    if persist:
        try:
            GROUPS_PATH.parent.mkdir(parents=True, exist_ok=True)
            doc["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            doc["n"] = len(doc["symbols"])
            tmp = GROUPS_PATH.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(doc, indent=2), encoding="utf-8")
            os.replace(tmp, GROUPS_PATH)
        except Exception as e:
            log.warning("[GROUPS] persist failed: %s", e)
    cov = {
        "n": assigned,
        "meaningful": meaningful,
        "meaningful_pct": round(100.0 * meaningful / max(assigned, 1), 2),
        "null_or_unknown": 0,
    }
    try:
        COV_PATH.write_text(json.dumps(cov, indent=2), encoding="utf-8")
    except Exception:
        pass
    return cov


def coverage_report(symbols: list[str] | None = None) -> dict[str, Any]:
    if symbols is None:
        try:
            import os

            from fortress_universe import load_fortress_scan_list

            # Match live fortress scan size — do not force a silent 250-name load
            # (that log line looked like the trading pass was huge / hung).
            cap = max(12, int(os.getenv("MAX_LIVE_SYMBOLS", "48") or 48))
            symbols = load_fortress_scan_list(cap, shuffle_rest=False)
        except Exception:
            symbols = []
    return ensure_groups(list(symbols), persist=True)
