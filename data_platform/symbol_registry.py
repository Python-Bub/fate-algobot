"""Canonical symbol registry and lightweight instrument classification.

The goal is not perfect exchange-grade taxonomy; it is to keep training/runtime
pipelines from wasting cycles on obvious non-tradables and junk suffixes while
remaining fast for large universes.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path

import yfinance as yf

from crypto_universe import is_crypto_symbol
from utils import log


REGISTRY_PATH = Path(os.getenv("SYMBOL_REGISTRY_PATH", "data/universe/symbol_registry.json"))


@dataclass
class SymbolMeta:
    symbol: str
    instrument_type: str
    exchange: str
    currency: str
    tradable: bool
    reason: str = ""


def _guess_type(symbol: str) -> str:
    s = symbol.upper()
    if is_crypto_symbol(s):
        return "crypto"
    if any(x in s for x in ("$W", "$U", "$R", "-W", "-U", "-R", ".WS", "WTS")):
        return "warrant_or_unit"
    if s.endswith(("Q", "Y")) and len(s) <= 5:
        # very rough OTC/distressed heuristic
        return "otc_or_special"
    return "equity_or_etf"


def _query_yf_meta(symbol: str) -> tuple[str, str, str]:
    try:
        tk = yf.Ticker(symbol)
        fi = getattr(tk, "fast_info", None) or {}
        currency = str(fi.get("currency", "") or "").upper()
        exchange = str(fi.get("exchange", "") or "").upper()
        quote_type = str(fi.get("quote_type", "") or "").lower()
        if not quote_type:
            info = getattr(tk, "info", {}) or {}
            quote_type = str(info.get("quoteType", "") or "").lower()
            currency = currency or str(info.get("currency", "") or "").upper()
            exchange = exchange or str(info.get("exchange", "") or "").upper()
        return quote_type, exchange, currency
    except Exception:
        return "", "", ""


def classify_symbol(symbol: str) -> SymbolMeta:
    s = symbol.strip().upper()
    base = _guess_type(s)
    qtype, exch, ccy = _query_yf_meta(s)

    instrument_type = base
    if qtype in ("etf", "mutualfund"):
        instrument_type = "etf"
    elif qtype in ("equity", "stock"):
        instrument_type = "equity"
    elif qtype in ("cryptocurrency",):
        instrument_type = "crypto"

    tradable = True
    reason = ""

    # kill obvious noisy symbols for training/universe loops
    if instrument_type in ("warrant_or_unit", "otc_or_special"):
        tradable = False
        reason = f"filtered:{instrument_type}"
    if "$" in s and not is_crypto_symbol(s):
        tradable = False
        reason = "filtered:contains_dollar_suffix"
    if exch in ("PNK", "OTC"):
        tradable = False
        reason = "filtered:otc_exchange"

    return SymbolMeta(
        symbol=s,
        instrument_type=instrument_type,
        exchange=exch or "UNKNOWN",
        currency=ccy or "UNKNOWN",
        tradable=tradable,
        reason=reason,
    )


def build_registry(symbols: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for i, s in enumerate(symbols, 1):
        try:
            meta = classify_symbol(s)
            out[s.upper()] = asdict(meta)
            if i % 200 == 0:
                log.info("[REGISTRY] classified %d/%d symbols", i, len(symbols))
        except Exception as e:
            out[s.upper()] = asdict(
                SymbolMeta(
                    symbol=s.upper(),
                    instrument_type="unknown",
                    exchange="UNKNOWN",
                    currency="UNKNOWN",
                    tradable=False,
                    reason=f"classify_error:{type(e).__name__}",
                )
            )
    return out


def save_registry(registry: dict[str, dict], path: Path | None = None) -> Path:
    p = path or REGISTRY_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, sort_keys=True)
    return p


def load_registry(path: Path | None = None) -> dict[str, dict]:
    p = path or REGISTRY_PATH
    if not p.is_file():
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def filter_tradable(symbols: list[str], registry: dict[str, dict] | None = None) -> list[str]:
    reg = registry if registry is not None else load_registry()
    out: list[str] = []
    for s in symbols:
        meta = reg.get(s.upper())
        if meta is None:
            out.append(s.upper())
            continue
        if bool(meta.get("tradable")):
            out.append(s.upper())
    return out

