"""Map legacy / universe tickers to current primary listing symbols for price and broker APIs."""

from __future__ import annotations

import json
from pathlib import Path

# Static fallbacks (registry merges on top at import + reload).
_ALIASES: dict[str, str] = {
    "SQ": "XYZ",
    "FB": "META",
    "FISV": "FI",
    "DWAC": "DJT",
    # Yahoo Finance uses hyphenated Berkshire class tickers (BRK.B is often empty).
    "BRK.B": "BRK-B",
    "BRK.A": "BRK-A",
    "BRKB": "BRK-B",
    "BRKA": "BRK-A",
}


def _registry_aliases() -> dict[str, str]:
    p = Path(__file__).resolve().parent / "data" / "universe" / "corporate_actions.json"
    if not p.is_file():
        return {}
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out = {str(k).upper(): str(v).upper() for k, v in (doc.get("aliases") or {}).items()}
    for ev in doc.get("events") or []:
        # Renames only. Spinoffs keep the parent ticker; mergers do not stitch target bars.
        if ev.get("kind") == "rename" and ev.get("old") and ev.get("new"):
            out[str(ev["old"]).upper()] = str(ev["new"]).upper()
    return out


def reload_aliases_from_registry() -> dict[str, str]:
    global _ALIASES
    merged = dict(_ALIASES)
    merged.update(_registry_aliases())
    _ALIASES = merged
    return _ALIASES


reload_aliases_from_registry()

# Class-share / dual-listing fallbacks when primary ticker has no bars.
# Also used when primary has too-few bars (thin ADRs / new listings).
_PRICE_SIBLINGS: dict[str, tuple[str, ...]] = {
    "GOOG": ("GOOGL",),
    "GOOGL": ("GOOG",),
    # Prefer hyphenated Yahoo symbols first; dotted BRK.B often returns empty.
    "BRK.A": ("BRK-A", "BRK-B", "BRK.B"),
    "BRK.B": ("BRK-B", "BRK-A", "BRK.A"),
    "BRK-A": ("BRK-B", "BRK.A", "BRK.B"),
    "BRK-B": ("BRK-A", "BRK.B", "BRK.A"),
    # SK hynix OTC/ADR thin; Korea primary has full history
    "SKHY": ("000660.KS",),
    "000660.KS": ("SKHY",),
}

# Dual-class / same-issuer keys. Buying GOOG while holding GOOGL is the same
# Alphabet bet twice — treat the group as one position.
_ISSUER_CANON: dict[str, str] = {
    "GOOG": "GOOGL",
    "GOOGL": "GOOGL",
    "BRK-A": "BRK-B",
    "BRK.A": "BRK-B",
    "BRKA": "BRK-B",
    "BRK-B": "BRK-B",
    "BRK.B": "BRK-B",
    "BRKB": "BRK-B",
    "FOX": "FOXA",
    "FOXA": "FOXA",
    "NWS": "NWSA",
    "NWSA": "NWSA",
}


def issuer_group(symbol: str) -> str:
    """Canonical issuer id so GOOG and GOOGL count as one name."""
    s = price_feed_symbol(symbol)
    return _ISSUER_CANON.get(s, s)


def issuer_siblings(symbol: str) -> tuple[str, ...]:
    """All listings that are the same company, including *symbol*."""
    g = issuer_group(symbol)
    sibs = tuple(sorted({k for k, v in _ISSUER_CANON.items() if v == g} | {g, price_feed_symbol(symbol)}))
    return sibs


def same_issuer(a: str, b: str) -> bool:
    return issuer_group(a) == issuer_group(b)


def price_feed_symbol(ticker: str) -> str:
    t = ticker.strip().upper()
    mapping = _ALIASES
    seen: set[str] = set()
    while t in mapping and t not in seen:
        seen.add(t)
        t = mapping[t]
    return t


def canonical_symbol(ticker: str) -> str:
    return price_feed_symbol(ticker)


def price_data_fallback_symbols(ticker: str) -> list[str]:
    """Ordered symbols to try when the primary listing returns no OHLCV."""
    logical = ticker.strip().upper()
    primary = price_feed_symbol(logical)
    out: list[str] = []
    # Prefer mapped feed symbol first (BRK.B → BRK-B for Yahoo).
    if primary not in out:
        out.append(primary)
    if logical not in out and logical != primary:
        out.append(logical)
    for sib in _PRICE_SIBLINGS.get(logical, ()):
        mapped = price_feed_symbol(sib)
        if mapped not in out:
            out.append(mapped)
    # Also try siblings keyed by primary feed symbol
    for sib in _PRICE_SIBLINGS.get(primary, ()):
        mapped = price_feed_symbol(sib)
        if mapped not in out:
            out.append(mapped)
    # Always keep the dotted Yahoo alias in the fallback chain.
    if logical in ("BRK-B", "BRK.B", "BRKB") and "BRK.B" not in out:
        out.append("BRK.B")
    if logical in ("BRK-A", "BRK.A", "BRKA") and "BRK.A" not in out:
        out.append("BRK.A")
    return out


def resolve_model_ticker(ticker: str) -> str | None:
    """Return a ticker with a trained on-disk model (GOOG → GOOGL, etc.)."""
    from model_trainer import training_saved_model

    for sym in price_data_fallback_symbols(ticker):
        if training_saved_model(sym):
            return sym
    # Fresh checkout has no pickles yet — still resolve to the canonical listing.
    return price_feed_symbol(ticker) or None
