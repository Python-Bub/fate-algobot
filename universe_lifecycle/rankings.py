"""Refresh top-100 and top-50% market-cap tiers from live yfinance caps."""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from universe_lifecycle.paths import CAP_CACHE_PATH, TOP100_PATH, TOP50_PATH

# Broad liquid seed — ranked live; same base as refresh_top100.py.
_CAP_SEED = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "BRK-B", "LLY", "AVGO",
    "JPM", "TSLA", "UNH", "XOM", "V", "MA", "PG", "JNJ", "HD", "COST",
    "ABBV", "MRK", "ORCL", "CVX", "CRM", "BAC", "NFLX", "AMD", "PEP", "KO",
    "TMO", "WMT", "CSCO", "LIN", "ACN", "MCD", "DIS", "ADBE", "DHR", "TXN",
    "INTU", "CMCSA", "QCOM", "AMGN", "INTC", "VZ", "IBM", "AMAT", "CAT", "GE",
    "HON", "UNP", "NEE", "PM", "RTX", "LOW", "SPGI", "BA", "GS", "BLK",
    "ELV", "SBUX", "DE", "GILD", "MDLZ", "ADP", "C", "MMC", "ISRG", "CB",
    "AXP", "SYK", "PGR", "REGN", "LRCX", "VRTX", "ZTS", "CI", "MO", "KLAC",
    "SNPS", "CDNS", "PANW", "EQIX", "ICE", "SHW", "CME", "WM", "HCA", "MCK",
    "PH", "USB", "PNC", "TGT", "ADI", "NOC", "FCX", "SO", "DUK", "EOG",
    "COP", "SLB", "PSX", "MPC", "VLO", "PLD", "SCHW", "MS", "BKNG", "ABT",
    "T", "TMUS", "NOW", "UBER", "ANET", "MU", "ARM", "SMCI", "PLTR", "COIN",
    "SHOP", "SQ", "PYPL", "SNOW", "CRWD", "TTD", "MELI", "ASML", "TSM",
    "BABA", "PDD", "NVO", "SAP", "SPY", "QQQ", "IWM",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path, default: dict) -> dict:
    if not path.is_file():
        return dict(default)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return dict(default)


def _write_json(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def _tier_diff(prev: list[str], cur: list[str]) -> dict[str, list[str]]:
    p, c = {x.upper() for x in prev}, {x.upper() for x in cur}
    return {"entered": sorted(c - p), "exited": sorted(p - c)}


def _trainable_model_pool() -> list[str]:
    """Full trainable equity pool for tier ranking (~3–7k), NOT only names that already have daily models.

    Using ``symbols_with_daily_models()`` alone caused a death spiral: top50pct ≈ 100
    because only ~186 dailies existed, so training never expanded across letters.
    Pool = core universe ∪ on-disk daily/intraday/LSTM stems (letter-equal opportunity).
    """
    import sys

    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from fortress_universe import (
        is_core_trainable_equity,
        symbols_with_daily_models,
        symbols_with_trained_intraday,
    )
    from universe_provider import load_universe_with_cap

    pool: set[str] = set()
    try:
        refresh = os.getenv("UNIVERSE_REFRESH_ON_RANK", "true").lower() in ("1", "true", "yes")
        for s in load_universe_with_cap(max_symbols=None, refresh=False):
            if is_core_trainable_equity(s):
                pool.add(s.upper())
        # If cache is still the tiny bundled list, merge any already-trained stems
        # so tiers can expand immediately while a network universe fetch runs.
        if len(pool) < 500:
            for s in symbols_with_daily_models():
                if is_core_trainable_equity(s):
                    pool.add(s.upper())
            for s in symbols_with_trained_intraday():
                if is_core_trainable_equity(s):
                    pool.add(s.upper())
            lstm_dir = root / "models" / "lstm"
            if lstm_dir.is_dir():
                for p in lstm_dir.rglob("*"):
                    if not p.is_file() or p.suffix.lower() not in {".pkl", ".pt", ".pth", ".joblib"}:
                        continue
                    stem = p.stem.upper().split("_")[0]
                    if is_core_trainable_equity(stem):
                        pool.add(stem)
            if refresh and len(pool) < 500:
                try:
                    os.environ.setdefault("UNIVERSE_FETCH_NETWORK", "true")
                    for s in load_universe_with_cap(max_symbols=None, refresh=True):
                        if is_core_trainable_equity(s):
                            pool.add(s.upper())
                except Exception:
                    pass
    except Exception:
        for s in symbols_with_daily_models():
            if is_core_trainable_equity(s):
                pool.add(s.upper())
    # Stable but NOT lexicographic privilege — hash order for sparse-cap fallbacks.
    try:
        from fortress_universe import hash_shuffle

        return hash_shuffle(sorted(pool), "trainable_model_pool")
    except Exception:
        return sorted(pool)


def _cap_one(symbol: str) -> tuple[str, float]:
    sym = symbol.strip().upper()
    try:
        import yfinance as yf

        tk = yf.Ticker(sym)
        cap = 0.0
        try:
            fi = tk.fast_info
            cap = float(getattr(fi, "market_cap", 0) or getattr(fi, "marketCap", 0) or 0)
        except Exception:
            pass
        if cap <= 0:
            info = tk.info or {}
            cap = float(info.get("marketCap") or 0.0)
        return sym, cap if cap > 0 else 0.0
    except Exception:
        return sym, 0.0


def _fetch_caps(symbols: list[str], *, workers: int | None = None) -> dict[str, float]:
    caps: dict[str, float] = {}
    w = workers if workers is not None else int(os.getenv("CAP_FETCH_WORKERS", "6"))
    batch_pause = float(os.getenv("CAP_FETCH_SLEEP", "0.08"))
    with ThreadPoolExecutor(max_workers=max(1, w)) as pool:
        futs = {pool.submit(_cap_one, s): s for s in symbols}
        done = 0
        for fut in as_completed(futs):
            sym, cap = fut.result()
            if cap > 0:
                caps[sym] = cap
            done += 1
            if done % 200 == 0:
                time.sleep(batch_pause)
    return caps


def _load_cap_progress() -> dict[str, Any]:
    p = CAP_CACHE_PATH.parent / "cap_fetch_progress.json"
    return _load_json(p, {"offset": 0, "last_pool_size": 0})


def _save_cap_progress(offset: int, pool_size: int) -> None:
    p = CAP_CACHE_PATH.parent / "cap_fetch_progress.json"
    _write_json(
        p,
        {
            "offset": int(offset) % max(pool_size, 1),
            "last_pool_size": pool_size,
            "updated_at_utc": _now(),
        },
    )


def _refresh_caps_progressive(pool: list[str], cached: dict[str, float]) -> dict[str, float]:
    """Fetch market caps in rotating chunks so full ~4k pool fills over multiple runs."""
    refresh = os.getenv("UNIVERSE_REFRESH_ON_RANK", "true").lower() in ("1", "true", "yes")
    if not refresh or not pool:
        return cached

    chunk = int(os.getenv("CAP_REFRESH_CHUNK", "400"))
    prog = _load_cap_progress()
    if int(prog.get("last_pool_size") or 0) != len(pool):
        prog["offset"] = 0
    offset = int(prog.get("offset") or 0) % len(pool)
    missing = [s for s in pool if cached.get(s, 0) <= 0]
    if not missing:
        return cached

    # Rotate through missing list so every weekly refresh advances coverage.
    # Hash-shuffle — never A→Z privilege for who gets caps first.
    try:
        from fortress_universe import hash_shuffle

        missing_ordered = hash_shuffle(list(missing), "cap_fetch_missing")
    except Exception:
        missing_ordered = list(missing)
    start = offset % len(missing_ordered) if missing_ordered else 0
    rotated = missing_ordered[start:] + missing_ordered[:start]
    to_fetch = rotated[:chunk]

    seed_missing = [s for s in _CAP_SEED if s in pool and cached.get(s, 0) <= 0]
    to_fetch = list(dict.fromkeys(seed_missing + to_fetch))[:chunk]

    fresh = _fetch_caps(to_fetch)
    cached.update(fresh)
    _save_cap_progress(offset + len(to_fetch), len(pool))
    return cached


def _rank_pool_by_cap(pool: list[str], caps: dict[str, float], seed: list[str]) -> list[str]:
    """Rank pool by market cap; never fall back to pure A→Z when caps are sparse."""
    seed_rank = {s: i for i, s in enumerate(seed)}
    pool_set = set(pool)
    with_cap = [(s, float(caps.get(s, 0) or 0)) for s in pool if float(caps.get(s, 0) or 0) > 0]
    with_cap.sort(key=lambda x: -x[1])

    if len(with_cap) >= max(80, len(pool) // 20):
        ranked = [s for s, _ in with_cap]
        no_cap = [s for s in pool if float(caps.get(s, 0) or 0) <= 0]
        no_cap.sort(key=lambda s: (seed_rank.get(s, 99999), s))
        ranked.extend(no_cap)
        return ranked

    # Sparse caps: mega-cap seed first, then stable hash order (not alphabet walk)
    try:
        from fortress_universe import hash_shuffle

        top = [s for s in seed if s in pool_set]
        top_set = set(top)
        rest = hash_shuffle([s for s in pool if s not in top_set], "top50_rank_fallback")
        return top + rest
    except Exception:
        return sorted(pool, key=lambda s: (seed_rank.get(s, 99999), s))


def refresh_market_cap_tiers(
    *,
    top_n: int | None = None,
    top50_pct: float | None = None,
    merge_cache: bool = True,
) -> dict[str, Any]:
    """
    Refresh data/top100_market_cap.json and data/top50pct_market_cap.json.

    Top-50% = upper half of the **full trainable model universe** (~1970 of ~3940),
    not the small bundled offline symbol list.
    """
    top_n = top_n or int(os.getenv("TOP100_COUNT", "100"))
    top50_pct = top50_pct if top50_pct is not None else float(os.getenv("TOP50_PCT", "0.5"))

    prev100 = _load_json(TOP100_PATH, {"symbols": []}).get("symbols") or []
    prev50 = _load_json(TOP50_PATH, {"symbols": []}).get("symbols") or []

    pool = _trainable_model_pool()
    seed = list(dict.fromkeys(s.upper() for s in _CAP_SEED if s))

    cache = _load_json(CAP_CACHE_PATH, {"caps": {}}) if merge_cache else {"caps": {}}
    cached_caps = {str(k).upper(): float(v) for k, v in (cache.get("caps") or {}).items()}
    cached_caps = _refresh_caps_progressive(pool, cached_caps)

    ranked_all = _rank_pool_by_cap(list(dict.fromkeys(seed + pool)), cached_caps, seed)

    top100 = [s for s in ranked_all if s in set(pool)][:top_n]
    for etf in ("SPY", "QQQ"):
        if etf in pool and etf not in top100:
            if len(top100) >= top_n:
                top100[-1] = etf
            else:
                top100.append(etf)
    top100 = list(dict.fromkeys(top100))[:top_n]

    half_n = max(1, int(len(pool) * top50_pct))
    pool_ranked = _rank_pool_by_cap(pool, cached_caps, seed)
    top50 = list(dict.fromkeys(pool_ranked[:half_n]))

    # Ensure top-100 mega caps are always inside top-50% tier
    top50_set = set(top50)
    for s in top100:
        if s not in top50_set:
            top50.insert(0, s)
            top50_set.add(s)
    if len(top50) > half_n + len(top100):
        top50 = top50[: half_n + len(top100)]

    cap_doc = {"updated_at_utc": _now(), "count": len(cached_caps), "caps": cached_caps}
    _write_json(CAP_CACHE_PATH, cap_doc)

    caps_in_pool = sum(1 for s in pool if cached_caps.get(s, 0) > 0)
    doc100 = {
        "updated_at_utc": _now(),
        "source": "yfinance_market_cap",
        "universe_pool": "full_trainable_equity",
        "count": len(top100),
        "symbols": top100,
    }
    doc50 = {
        "updated_at_utc": _now(),
        "source": "yfinance_market_cap_top_half",
        "universe_pool": "full_trainable_equity",
        "universe_size": len(pool),
        "pct": top50_pct,
        "target_half_count": half_n,
        "count": len(top50),
        "caps_known_in_pool": caps_in_pool,
        "symbols": top50,
    }
    # Never wipe a nonempty on-disk cache with an empty refresh (offline / sparse caps).
    if top100:
        _write_json(TOP100_PATH, doc100)
    elif prev100:
        top100 = [str(s).upper() for s in prev100 if s]
        doc100["symbols"] = top100
        doc100["count"] = len(top100)
        doc100["preserved_nonempty_cache"] = True
    else:
        _write_json(TOP100_PATH, doc100)
    if top50:
        _write_json(TOP50_PATH, doc50)
    elif prev50:
        top50 = [str(s).upper() for s in prev50 if s]
        doc50["symbols"] = top50
        doc50["count"] = len(top50)
        doc50["preserved_nonempty_cache"] = True
    else:
        _write_json(TOP50_PATH, doc50)

    return {
        "top100": top100,
        "top50pct": top50,
        "top100_diff": _tier_diff(prev100, top100),
        "top50_diff": _tier_diff(prev50, top50),
        "caps_fetched": caps_in_pool,
        "universe_size": len(pool),
        "top50_target": half_n,
    }


def main() -> int:
    import sys

    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    out = refresh_market_cap_tiers()
    print(
        f"[rankings] top100={len(out['top100'])} top50={len(out['top50pct'])} "
        f"universe={out['universe_size']} target_half={out['top50_target']}"
    )
    print(f"[rankings] top100 entered={out['top100_diff']['entered'][:8]} exited={out['top100_diff']['exited'][:8]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
