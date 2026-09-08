"""Crypto universe for FATE_AlgoBot.

Ticker formats that coexist on purpose:
- Yahoo / yfinance: BTC-USD
- Alpaca orders:    BTC/USD
- Alpaca positions: BTCUSD  (compact, no slash)

`alpaca_symbol` / `yahoo_symbol` translate between them.
"""

from __future__ import annotations

# Liquid spot crypto pairs Alpaca paper trading currently supports.
CRYPTO_YAHOO: list[str] = [
    "BTC-USD",
    "ETH-USD",
    "SOL-USD",
    "DOGE-USD",
    "AVAX-USD",
    "LINK-USD",
    "DOT-USD",
    "LTC-USD",
    "BCH-USD",
    "POL-USD",  # Polygon (MATIC rebrand)
    "MATIC-USD",  # keep alias while some feeds still list it
    "UNI-USD",
    "AAVE-USD",
    "XRP-USD",
    "ADA-USD",
    "ATOM-USD",
    "NEAR-USD",
    "ARB-USD",
    "OP-USD",
    "SHIB-USD",
    "GRT-USD",
]

_CRYPTO_BASES = frozenset(s.split("-", 1)[0] for s in CRYPTO_YAHOO)


def alpaca_symbol(yahoo_sym: str) -> str:
    """BTC-USD / BTCUSD -> BTC/USD"""
    s = yahoo_sym.strip().upper().replace(" ", "")
    if "/" in s:
        return s
    if s.endswith("-USD"):
        return s.replace("-", "/")
    if s.endswith("USD") and s[:-3] in _CRYPTO_BASES:
        return f"{s[:-3]}/USD"
    return s.replace("-", "/")


def yahoo_symbol(alpaca_sym: str) -> str:
    """BTC/USD / BTCUSD -> BTC-USD"""
    s = alpaca_sym.strip().upper().replace(" ", "")
    if "-" in s:
        return s
    if "/" in s:
        return s.replace("/", "-")
    if s.endswith("USD") and s[:-3] in _CRYPTO_BASES:
        return f"{s[:-3]}-USD"
    return s.replace("/", "-")


def is_crypto_symbol(sym: str) -> bool:
    s = sym.strip().upper().replace(" ", "")
    if "/" in s and s.endswith("/USD"):
        return True
    if s.endswith("-USD") and not s.endswith("USDC-USD"):
        return True
    if s.endswith("USD") and s[:-3] in _CRYPTO_BASES:
        return True
    return False


def crypto_alpaca_pairs() -> list[str]:
    return [alpaca_symbol(s) for s in CRYPTO_YAHOO]


def same_crypto(a: str, b: str) -> bool:
    if not (is_crypto_symbol(a) and is_crypto_symbol(b)):
        return False
    return yahoo_symbol(a) == yahoo_symbol(b)
