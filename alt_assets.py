"""Crypto + commodity instruments the live book can trade alongside equities.

Equities stay in `fortress_universe.is_tradeable_equity`. This module is the
additive alt sleeve: Alpaca crypto pairs + liquid commodity ETFs (silver, gold,
oil, grains, bitcoin ETFs).
"""

from __future__ import annotations

import os

from crypto_universe import CRYPTO_YAHOO, alpaca_symbol, is_crypto_symbol, yahoo_symbol

# Physically-backed / liquid commodity & crypto-proxy ETFs Alpaca can trade as stocks.
COMMODITY_ETFS: list[str] = [
    "SLV",   # silver
    "SIVR",  # silver
    "GLD",   # gold
    "IAU",   # gold
    "GLDM",
    "USO",   # WTI oil
    "BNO",
    "UNG",   # natural gas
    "CPER",  # copper
    "PPLT",  # platinum
    "PALL",  # palladium
    "DBA",   # agriculture
    "WEAT",
    "CORN",
    "SOYB",
    "GSG",
    "PDBC",
    "DBC",
    "BITO",  # bitcoin futures ETF
    "IBIT",  # spot bitcoin ETF
    "ETHA",  # spot ether ETF
    "GBTC",
    "ETHE",
]

_COMMODITY_SET = frozenset(COMMODITY_ETFS)


def trade_crypto_enabled() -> bool:
    return os.getenv("TRADE_CRYPTO", "true").lower() in ("1", "true", "yes", "on")


def trade_commodities_enabled() -> bool:
    return os.getenv("TRADE_COMMODITIES", "true").lower() in ("1", "true", "yes", "on")


def trade_alts_enabled() -> bool:
    return os.getenv("TRADE_ALTS", "true").lower() in ("1", "true", "yes", "on")


def is_commodity_etf(symbol: str) -> bool:
    return symbol.strip().upper() in _COMMODITY_SET


def is_alt_symbol(symbol: str) -> bool:
    s = symbol.strip().upper()
    return is_crypto_symbol(s) or is_commodity_etf(s)


def is_tradeable_instrument(symbol: str) -> bool:
    """Equities always; crypto/commodities when their sleeves are on."""
    s = symbol.strip().upper()
    if not s:
        return False
    if is_crypto_symbol(s):
        return trade_crypto_enabled() and trade_alts_enabled()
    if is_commodity_etf(s):
        return trade_commodities_enabled() and trade_alts_enabled()
    try:
        from fortress_universe import is_tradeable_equity

        return is_tradeable_equity(s)
    except Exception:
        return True


def crypto_yahoo_symbols() -> list[str]:
    extra = [
        s.strip().upper()
        for s in os.getenv("CRYPTO_EXTRA_YAHOO", "").split(",")
        if s.strip()
    ]
    out: list[str] = []
    seen: set[str] = set()
    for s in list(CRYPTO_YAHOO) + extra:
        u = s.strip().upper()
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def commodity_symbols() -> list[str]:
    extra = [
        s.strip().upper()
        for s in os.getenv("COMMODITY_EXTRA_ETFS", "").split(",")
        if s.strip()
    ]
    return list(dict.fromkeys(COMMODITY_ETFS + extra))


def alt_scan_symbols() -> list[str]:
    """Yahoo-format symbols to prepend on fortress/paper scans."""
    out: list[str] = []
    if not trade_alts_enabled():
        return out
    if trade_commodities_enabled():
        out.extend(commodity_symbols())
    if trade_crypto_enabled():
        out.extend(crypto_yahoo_symbols())
    return list(dict.fromkeys(out))


def to_alpaca_symbol(symbol: str) -> str:
    s = symbol.strip().upper()
    if is_crypto_symbol(s):
        return alpaca_symbol(s)
    return s


def to_yahoo_symbol(symbol: str) -> str:
    s = symbol.strip().upper()
    if is_crypto_symbol(s):
        return yahoo_symbol(s)
    return s
