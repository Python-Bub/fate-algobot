"""
Symbol universe: offline-first (no blocking on Nasdaq). Optional network merge.

Default: bundled liquid US list. Set UNIVERSE_FETCH_NETWORK=true to merge Nasdaq files
(when your network allows). Timeouts are short by default to avoid hanging.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
import urllib.request
from pathlib import Path

from bundled_universe import SYMBOLS as BUNDLED_SYMBOLS
from utils import log

try:
    import requests as _requests_mod

    _REQUESTS_OK = True
except ImportError:
    _requests_mod = None
    _REQUESTS_OK = False

NASDAQ_LISTED_HTTPS = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_HTTPS = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
NASDAQ_LISTED_FTP = "ftp://ftp.nasdaqtrader.com/SymbolDirectory/nasdaqlisted.txt"
OTHER_LISTED_FTP = "ftp://ftp.nasdaqtrader.com/SymbolDirectory/otherlisted.txt"

_DEFAULT_CACHE = Path("data") / "universe" / "us_equity_symbols.txt"


def _fetch_network_enabled() -> bool:
    return os.getenv("UNIVERSE_FETCH_NETWORK", "false").lower() in ("1", "true", "yes")


def _timeout_sec() -> int:
    return int(os.getenv("UNIVERSE_DOWNLOAD_TIMEOUT", "20"))


def _retries() -> int:
    return int(os.getenv("UNIVERSE_DOWNLOAD_RETRIES", "2"))


def _fetch_urllib(url: str, timeout: int | None) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; FATE_AlgoBot/1.2)",
            "Accept": "text/plain,*/*",
            "Connection": "close",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _fetch_requests(url: str, timeout: int | None) -> str:
    if not _REQUESTS_OK or _requests_mod is None:
        raise ImportError("requests not installed")
    r = _requests_mod.get(url, timeout=timeout, headers={"User-Agent": "FATE_AlgoBot/1.2"})
    r.raise_for_status()
    return r.text


def _fetch_curl(url: str, timeout: int) -> str:
    out = subprocess.run(
        ["curl", "-fsSL", "--max-time", str(timeout), "-A", "FATE_AlgoBot/1.2", url],
        capture_output=True,
        text=True,
        timeout=timeout + 15 if timeout else 120,
    )
    if out.returncode != 0:
        raise RuntimeError(out.stderr or "curl failed")
    return out.stdout


def fetch_url_robust(url: str) -> str:
    """Short attempts; use UNIVERSE_DOWNLOAD_TIMEOUT=0 with urllib for no socket timeout (not recommended)."""
    t = _timeout_sec()
    timeout_arg: int | None = None if t <= 0 else t
    last_err: Exception | None = None
    for attempt in range(1, _retries() + 1):
        wait = min(30, 2**attempt)
        try:
            return _fetch_urllib(url, timeout_arg)
        except Exception as e:
            last_err = e
            log.warning("[UNIVERSE] urllib %s attempt %s/%s: %s", url[:48], attempt, _retries(), e)
        if _REQUESTS_OK:
            try:
                return _fetch_requests(url, timeout_arg)
            except Exception as e:
                last_err = e
                log.warning("[UNIVERSE] requests attempt %s: %s", attempt, e)
        if t > 0:
            try:
                return _fetch_curl(url, t)
            except Exception as e:
                last_err = e
                log.warning("[UNIVERSE] curl attempt %s: %s", attempt, e)
        elif t <= 0:
            log.debug("[UNIVERSE] curl skipped (UNIVERSE_DOWNLOAD_TIMEOUT<=0)")
        if attempt < _retries():
            time.sleep(wait)
    if last_err:
        raise last_err
    raise RuntimeError("fetch_url_robust failed")


def _fetch_pair(https_url: str, ftp_url: str) -> str:
    try:
        return fetch_url_robust(https_url)
    except Exception as e_https:
        log.warning("[UNIVERSE] HTTPS failed (%s), trying FTP…", e_https)
        t = _timeout_sec()
        to = None if t <= 0 else t
        return _fetch_urllib(ftp_url, to)


def _parse_nasdaq_listed(text: str) -> list[str]:
    out: list[str] = []
    for line in text.splitlines():
        if not line or line.startswith("Symbol|") or "File Creation Time" in line:
            continue
        p = line.split("|")
        if len(p) < 2:
            continue
        sym = p[0].strip()
        if not sym or sym == "Symbol":
            continue
        if len(p) > 3 and p[3].strip() == "Y":
            continue
        if len(p) > 6 and p[6].strip() == "Y":
            continue
        if sym.endswith("Test") or ".WS" in sym or sym.startswith("^"):
            continue
        out.append(sym)
    return out


def _parse_other_listed(text: str) -> list[str]:
    out: list[str] = []
    for line in text.splitlines():
        if not line or line.startswith("ACT Symbol|") or "File Creation Time" in line:
            continue
        p = line.split("|")
        if len(p) < 6:
            continue
        sym = p[0].strip()
        if not sym or sym == "ACT Symbol":
            continue
        if p[3].strip() == "Y":
            continue
        if p[5].strip() == "Y":
            continue
        if sym.startswith("^"):
            continue
        out.append(sym)
    return out


def _fallback_from_config() -> list[str]:
    try:
        from config import TRAIN_TICKERS, TICKERS

        return sorted(set(TICKERS) | set(TRAIN_TICKERS))
    except Exception:
        return list(BUNDLED_SYMBOLS)


def download_us_listed_symbols(cache_path: Path | None = None) -> list[str]:
    """
    Always seeds cache from bundled symbols first (instant).
    Optionally merges Nasdaq/NYSE lists when UNIVERSE_FETCH_NETWORK=true.
    """
    cache_path = cache_path or _DEFAULT_CACHE
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    offline = os.getenv("UNIVERSE_OFFLINE_FILE", "").strip()
    if offline and Path(offline).is_file():
        merged = sorted(
            {ln.strip() for ln in Path(offline).read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")}
        )
        log.info("[UNIVERSE] Loaded %d symbols from UNIVERSE_OFFLINE_FILE", len(merged))
        cache_path.write_text("\n".join(merged) + "\n", encoding="utf-8")
        return merged

    base = sorted(set(BUNDLED_SYMBOLS) | set(_fallback_from_config()))
    log.info("[UNIVERSE] Seeded %d symbols from bundled + config (offline-first)", len(base))

    # Never shrink an existing larger cache (offline refresh used to overwrite ~10k → ~200).
    prev: list[str] = []
    if cache_path.is_file():
        try:
            prev = [
                ln.strip().upper()
                for ln in cache_path.read_text(encoding="utf-8").splitlines()
                if ln.strip() and not ln.startswith("#")
            ]
        except OSError:
            prev = []

    def _keep_largest(candidate: list[str], reason: str) -> list[str]:
        if prev and len(prev) > len(candidate):
            log.warning(
                "[UNIVERSE] Keeping existing cache (%d) over %s (%d) — never shrink",
                len(prev),
                reason,
                len(candidate),
            )
            return list(dict.fromkeys(prev))
        return candidate

    if not _fetch_network_enabled():
        log.info(
            "[UNIVERSE] Network fetch skipped. Set UNIVERSE_FETCH_NETWORK=true to merge Nasdaq listings."
        )
        kept = _keep_largest(base, "bundled+config")
        if kept is not prev or not cache_path.is_file():
            cache_path.write_text("\n".join(kept) + "\n", encoding="utf-8")
            log.info("[UNIVERSE] Wrote %s (%d symbols)", cache_path, len(kept))
        return kept

    try:
        log.info("[UNIVERSE] Merging Nasdaq Trader listings (network)…")
        nasdaq_raw = _fetch_pair(NASDAQ_LISTED_HTTPS, NASDAQ_LISTED_FTP)
        nasdaq = _parse_nasdaq_listed(nasdaq_raw)
        other_raw = _fetch_pair(OTHER_LISTED_HTTPS, OTHER_LISTED_FTP)
        other = _parse_other_listed(other_raw)
        remote = set(nasdaq) | set(other)
        merged = sorted(set(base) | remote | set(prev))
        log.info("[UNIVERSE] Merged remote; unique symbols: %d", len(merged))
        cache_path.write_text("\n".join(merged) + "\n", encoding="utf-8")
        log.info("[UNIVERSE] Wrote %s", cache_path)
        return merged
    except Exception as e:
        log.error("[UNIVERSE] Network merge failed (%s). Keeping largest known list.", e)
        kept = _keep_largest(base, "bundled after fetch fail")
        if kept is not prev or not cache_path.is_file():
            cache_path.write_text("\n".join(kept) + "\n", encoding="utf-8")
        return kept


def load_universe_symbols(
    cache_path: Path | None = None,
    refresh: bool = False,
) -> list[str]:
    cache_path = cache_path or _DEFAULT_CACHE
    if refresh or not cache_path.is_file():
        syms = download_us_listed_symbols(cache_path)
    else:
        lines = cache_path.read_text(encoding="utf-8").splitlines()
        syms = [ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")]
    if os.getenv("USE_SYMBOL_REGISTRY_FILTER", "true").lower() in ("1", "true", "yes"):
        try:
            from data_platform.symbol_registry import load_registry, filter_tradable

            reg = load_registry()
            if reg:
                syms = filter_tradable(syms, reg)
        except Exception as e:
            log.warning("[UNIVERSE] registry filter skipped: %s", e)
    return syms


def load_universe_with_cap(max_symbols: int | None = None, refresh: bool = False) -> list[str]:
    syms = load_universe_symbols(refresh=refresh)
    if max_symbols is not None:
        syms = syms[: int(max_symbols)]
    return syms


def filter_symbols(symbols: list[str], pattern: str | None = None) -> list[str]:
    if not pattern:
        return symbols
    rx = re.compile(pattern)
    return [s for s in symbols if rx.match(s)]
