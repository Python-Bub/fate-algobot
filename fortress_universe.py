"""Fortress live universe: full equity model pool, no letter prefix, no crypto."""

from __future__ import annotations

import json
import os
import random
from pathlib import Path

from crypto_universe import is_crypto_symbol
from utils import log

_HFT_QUALITY_SET: frozenset[str] | None = None

TOP100_CACHE = Path(__file__).resolve().parent / "data" / "top100_market_cap.json"
TOP50_CACHE = Path(__file__).resolve().parent / "data" / "top50pct_market_cap.json"
_TOP100_SET: frozenset[str] | None = None
_TOP100_RANK: dict[str, int] | None = None
_TOP100_LIST: list[str] | None = None
_TOP50_SET: frozenset[str] | None = None


def _remember_top100(syms: list[str]) -> list[str]:
    global _TOP100_SET, _TOP100_RANK, _TOP100_LIST
    clean = list(dict.fromkeys(syms))
    _TOP100_LIST = clean
    _TOP100_SET = frozenset(clean)
    _TOP100_RANK = {s: i + 1 for i, s in enumerate(clean)}
    return clean


def load_top100_symbols(refresh: bool = False) -> list[str]:
    """Top N US names by market cap (cached JSON). Default 100."""
    global _TOP100_SET, _TOP100_RANK, _TOP100_LIST
    if refresh or not TOP100_CACHE.is_file():
        try:
            import subprocess
            import sys

            subprocess.run(
                [sys.executable, "-u", "tools/refresh_top100.py"],
                cwd=str(Path(__file__).resolve().parent),
                check=False,
                timeout=300,
            )
        except Exception:
            pass
    syms: list[str] = []
    if TOP100_CACHE.is_file():
        try:
            doc = json.loads(TOP100_CACHE.read_text(encoding="utf-8"))
            syms = [str(s).upper() for s in doc.get("symbols", []) if s]
        except Exception:
            syms = []
    if not syms and _TOP100_LIST:
        # A mid-write or EMFILE read must not wipe a good in-process universe.
        return list(_TOP100_LIST)
    if not syms:
        log.warning("[TOP100] cache empty — run ./run_all.sh refresh-top100 (no static ticker fallback)")
        return []
    return _remember_top100(syms)


def is_top100_equity(symbol: str) -> bool:
    global _TOP100_SET
    s = symbol.strip().upper()
    if _TOP100_SET is None:
        load_top100_symbols()
    return s in (_TOP100_SET or frozenset())


def top100_rank(symbol: str) -> int | None:
    global _TOP100_RANK
    if _TOP100_RANK is None:
        load_top100_symbols()
    return (_TOP100_RANK or {}).get(symbol.strip().upper())


def load_top50pct_symbols(refresh: bool = False) -> list[str]:
    """Top half of trainable universe by market cap (cached JSON). Includes top-100."""
    global _TOP50_SET
    if refresh or not TOP50_CACHE.is_file():
        try:
            import subprocess
            import sys

            subprocess.run(
                [sys.executable, "-u", "tools/refresh_top100.py"],
                cwd=str(Path(__file__).resolve().parent),
                check=False,
                timeout=600,
            )
        except Exception:
            pass
    syms: list[str] = []
    if TOP50_CACHE.is_file():
        try:
            doc = json.loads(TOP50_CACHE.read_text(encoding="utf-8"))
            syms = [str(s).upper() for s in doc.get("symbols", []) if s]
        except Exception:
            syms = []
    if not syms:
        # Fallback: top100 + top half of full trainable pool (never A→Z walk).
        from universe_provider import load_universe_with_cap

        syms = list(load_top100_symbols())
        pool = [
            s.upper()
            for s in load_universe_with_cap(max_symbols=None)
            if is_core_trainable_equity(s)
        ]
        if len(pool) < 500:
            pool = list(
                dict.fromkeys(
                    pool
                    + [s for s in symbols_with_daily_models() if is_core_trainable_equity(s)]
                    + [s for s in symbols_with_trained_intraday() if is_core_trainable_equity(s)]
                )
            )
        pool = hash_shuffle(pool, "top50_fallback_pool")
        rest = [s for s in pool if s not in set(syms)]
        half = max(1, len(pool) // 2)
        top50_rest = rest[: max(0, half - len(syms))]
        syms.extend(top50_rest)
    syms = list(dict.fromkeys(syms))
    _TOP50_SET = frozenset(syms)
    return syms


def is_top50pct_equity(symbol: str) -> bool:
    global _TOP50_SET
    s = symbol.strip().upper()
    if _TOP50_SET is None:
        load_top50pct_symbols()
    return s in (_TOP50_SET or frozenset())


def load_hft_quality_tickers() -> frozenset[str]:
    """Liquid single-name symbols for sub-second HFT — never default to index ETFs."""
    global _HFT_QUALITY_SET
    if _HFT_QUALITY_SET is not None:
        return _HFT_QUALITY_SET
    raw = os.getenv(
        "HFT_QUALITY_TICKERS",
        "AAPL,MSFT,NVDA,AMD,META,AMZN,GOOGL,NFLX,AVGO,COST,JNJ,WMT,CRM,NOW,SBUX,TSLA,BX",
    ).strip()
    _HFT_QUALITY_SET = frozenset(s.strip().upper() for s in raw.split(",") if s.strip())
    # Strip banned index ETFs even if env/whitelist wrongly includes them.
    ban_raw = os.getenv(
        "HFT_BAN_INDEX_ETFS",
        os.getenv("FORTRESS_BAN_INDEX_ETFS", "SPY,QQQ,IWM,DIA,VOO,VTI,SOXX,XLK,XLF,XLE"),
    )
    banned = {s.strip().upper() for s in ban_raw.split(",") if s.strip()}
    if os.getenv("HFT_BAN_INDEX_BUYS", "true").lower() in ("1", "true", "yes"):
        _HFT_QUALITY_SET = frozenset(s for s in _HFT_QUALITY_SET if s not in banned)
    return _HFT_QUALITY_SET


def is_hft_quality_equity(symbol: str) -> bool:
    return symbol.strip().upper() in load_hft_quality_tickers()


def is_well_known_equity(symbol: str) -> bool:
    """Deprecated alias: top-100 by market cap (data/top100_market_cap.json), not a code favor list."""
    return is_top100_equity(symbol)


def load_well_known_equities() -> list[str]:
    """Deprecated alias for load_top100_symbols() — no separate static favor list."""
    return load_top100_symbols()


def is_tradeable_equity(symbol: str) -> bool:
    """Exclude crypto and obvious non-equity symbols."""
    s = symbol.strip().upper()
    if not s or len(s) > 6:
        return False
    if is_crypto_symbol(s):
        return False
    if s.endswith("-USD") or "/" in s:
        return False
    if any(ch in s for ch in ("^", "=", ".")):
        return False
    return True


def is_core_trainable_equity(symbol: str) -> bool:
    """Liquid common stocks/ETFs — skips warrants, units, and preferred stubs."""
    s = symbol.strip().upper()
    if not is_tradeable_equity(s):
        return False
    if "$" in s or len(s) < 2:
        return False
    # Warrant / SPAC unit heuristics (FIGXW, LANDO, …)
    if len(s) >= 5 and s.endswith("W"):
        return False
    if len(s) >= 5 and s.endswith("U") and s[-2].isalpha():
        return False
    if len(s) >= 6 and s.endswith("R") and s[-2].isalpha():
        return False
    return True


def has_trained_intraday_bundle(symbol: str, min_bytes: int | None = None) -> bool:
    """True when intraday pickle exists and is larger than placeholder threshold."""
    root = Path(os.getenv("INTRADAY_MODEL_DIR", "models/intraday"))
    p = root / f"{symbol.strip().upper()}_intraday.pkl"
    thresh = int(min_bytes if min_bytes is not None else INTRADAY_TRAINED_MIN_BYTES)
    try:
        return p.is_file() and p.stat().st_size > thresh
    except OSError:
        return False


def intraday_cached_gap_skip(symbol: str) -> bool:
    """True when a prior gap run already stored a permanent insufficient-data placeholder."""
    if os.getenv("INTRADAY_GAP_SKIP_CACHED_PLACEHOLDER", "true").lower() not in (
        "1",
        "true",
        "yes",
    ):
        return False
    sym = symbol.strip().upper()
    try:
        from data_platform.network_data import intraday_placeholder_registered

        reg = intraday_placeholder_registered(sym)
        if reg:
            reason = str(reg.get("reason") or "")
            rows = int(reg.get("rows") or 0)
            min_bars = int(os.getenv("INTRADAY_MIN_BARS", "800"))
            if reason in ("insufficient_data", "all_nan_after_features") and rows < min_bars:
                return True
    except ImportError:
        pass
    root = Path(os.getenv("INTRADAY_MODEL_DIR", "models/intraday"))
    p = root / f"{sym}_intraday.pkl"
    min_bars = int(os.getenv("INTRADAY_MIN_BARS", "800"))
    try:
        if not p.is_file() or p.stat().st_size > INTRADAY_TRAINED_MIN_BYTES:
            return False
    except OSError:
        return False
    try:
        import joblib

        bundle = joblib.load(p)
    except Exception:
        return False
    if not bundle.get("placeholder"):
        return False
    stats = bundle.get("stats") or {}
    reason = str(stats.get("skipped") or "")
    rows = int(stats.get("rows") or 0)
    if reason in ("insufficient_data", "all_nan_after_features") and rows < min_bars:
        return True
    return False


def symbols_with_daily_models() -> list[str]:
    model_dir = os.getenv("MODEL_DIR", "models")
    root = Path(model_dir)
    if not root.is_dir():
        return []
    out: list[str] = []
    for p in root.glob("*_model.pkl"):
        name = p.name[: -len("_model.pkl")].upper()
        if not name:
            continue
        if is_tradeable_equity(name):
            out.append(name)
            continue
        try:
            from alt_assets import is_alt_symbol, trade_alts_enabled

            if trade_alts_enabled() and is_alt_symbol(name):
                out.append(name)
        except Exception:
            pass
    return sorted(set(out))


# Neutral intraday backfills are tiny (~455 B); real GBDT bundles are ~900 KiB+.
INTRADAY_TRAINED_MIN_BYTES = int(os.getenv("INTRADAY_TRAINED_MIN_BYTES", "12000"))


def symbols_with_trained_intraday(min_bytes: int | None = None) -> list[str]:
    """Tickers with a non-placeholder intraday model (had enough bar data to train)."""
    root = Path(os.getenv("INTRADAY_MODEL_DIR", "models/intraday"))
    if not root.is_dir():
        return []
    thresh = int(min_bytes if min_bytes is not None else INTRADAY_TRAINED_MIN_BYTES)
    out: list[str] = []
    for p in root.glob("*_intraday.pkl"):
        try:
            if p.stat().st_size <= thresh:
                continue
        except OSError:
            continue
        name = p.name[: -len("_intraday.pkl")].upper()
        if name and is_tradeable_equity(name):
            out.append(name)
    return sorted(set(out))


def symbols_paper_active_universe() -> list[str]:
    """Tradeable paper universe: top-100 always in, rotating cap on the rest (not full 6k A-sorted)."""
    intra = set(symbols_with_trained_intraday())
    require_daily = os.getenv("PAPER_SIM_REQUIRE_DAILY_MODEL", "true").lower() in (
        "1",
        "true",
        "yes",
    )
    daily = set(symbols_with_daily_models()) if require_daily else set()
    if require_daily:
        pool = sorted(s for s in (intra & daily) if is_core_trainable_equity(s))
    else:
        pool = sorted(s for s in intra if is_core_trainable_equity(s))

    # Fresh clone / no pickles yet: still rotate the liquid top-100 cache
    # (never return an empty paper universe).
    if not pool:
        cached = [s for s in load_top100_symbols() if is_core_trainable_equity(s)]
        if cached:
            return apply_scan_order(cached)

    mode = os.getenv("PAPER_SIM_ACTIVE_MODE", "top100_rotate").strip().lower()
    if mode in ("all", "full", "whole", "database"):
        return apply_scan_order(pool)
    if mode in ("top50", "top50pct", "half", "top_half"):
        top50 = [s for s in load_top50pct_symbols() if s in pool]
        return apply_scan_order(top50)

    top = [s for s in load_top100_symbols() if s in pool]
    top_set = frozenset(top)
    rest = [s for s in pool if s not in top_set]
    cap = int(os.getenv("PAPER_SIM_ACTIVE_MAX", "480"))
    cap = max(len(top), min(cap, len(pool))) if pool else len(top)
    rest_cap = max(0, cap - len(top))
    rest_ordered = hash_shuffle(rest, f"{_scan_order_seed()}:rest")
    off = _load_rotate_offset(len(rest_ordered), name="paper_active") if rest_ordered else 0
    if rest_cap > 0 and rest_ordered:
        span = rest_ordered[off:] + rest_ordered[:off]
        rest_take = span[:rest_cap]
        _save_rotate_offset(off + rest_cap, len(rest_ordered), name="paper_active")
    else:
        rest_take = []
    out = top + rest_take
    return apply_scan_order(out)


def trade_quality_universe() -> frozenset[str]:
    """Symbols eligible for paper picks + family-forecast (top-100 + rotating active cap)."""
    return frozenset(symbols_paper_active_universe())


def prioritize_training_universe(
    symbols: list[str],
    *,
    cap: int | None = None,
    quality_half: bool | None = None,
) -> list[str]:
    """Training queue — equal A–Z coverage by default (no name / letter favoritism).

    Modes via ``TRAIN_PRIORITIZE``:
      - ``letter_rr`` / ``fair`` / ``equal`` (default): hash within letter, round-robin A–Z
      - ``top100_letter_rr``: top-100 first, then letter round-robin rest
      - ``top100``: top-100 then hash-shuffle
      - ``shuffle`` / ``hash``: pure hash-shuffle
      - ``alphabet``: explicit A→Z only (discouraged)

    When ``TRAIN_QUALITY_HALF=true`` or ``quality_half=True``, cap at the top half of
    the prioritized list so partial runs cover liquid names, not the first half of alphabet.
    """
    syms = [s.strip().upper() for s in symbols if s and is_core_trainable_equity(s)]
    syms = list(dict.fromkeys(syms))
    if not syms:
        return []

    mode = os.getenv("TRAIN_PRIORITIZE", "letter_rr").strip().lower()
    if mode in ("alphabet", "alpha", "a_z", "lex"):
        # Explicit opt-in only — alphabetical is name favoritism; do not use by default.
        out = sorted(syms)
    elif mode in ("0", "false", "none", "shuffle", "hash"):
        out = hash_shuffle(syms, f"{_scan_order_seed()}:train")
    elif mode in ("top100_letter_rr", "top100_rr", "liquidity_rr"):
        sym_set = set(syms)
        top = [s for s in load_top100_symbols() if s in sym_set]
        top_set = frozenset(top)
        rest = [s for s in syms if s not in top_set]
        rest = round_robin_by_first_letter(hash_shuffle(rest, f"{_scan_order_seed()}:train_rr"))
        out = top + rest
    elif mode in ("letter_rr", "fair", "round_robin", "rr", "equal_letters", "equal", "letter_fair"):
        # Every letter advances together — no mega-cap forever-first, no A-first dump.
        out = round_robin_by_first_letter(hash_shuffle(syms, f"{_scan_order_seed()}:train_rr"))
    else:
        # top100 (legacy): top-100 then hash-shuffle rest (not A→Z).
        sym_set = set(syms)
        top = [s for s in load_top100_symbols() if s in sym_set]
        top_set = frozenset(top)
        rest = [s for s in syms if s not in top_set]
        rest = hash_shuffle(rest, f"{_scan_order_seed()}:train")
        out = top + rest

    # Weak-letter boost: pull under-trained first letters ahead inside fair order.
    # Does not drop any symbols — only reorders so F/O/etc. get trained sooner.
    if os.getenv("TRAIN_WEAK_LETTER_BOOST", "false").lower() in ("1", "true", "yes"):
        weak = {
            x.strip().upper()[:1]
            for x in os.getenv("TRAIN_WEAK_LETTERS", "F,O,E,R,I").split(",")
            if x.strip()
        }
        if weak:
            head = [s for s in out if (s[:1] or "?") in weak]
            tail = [s for s in out if (s[:1] or "?") not in weak]
            # Keep letter round-robin inside the weak head
            out = round_robin_by_first_letter(head) + tail

    if quality_half is None:
        quality_half = os.getenv("TRAIN_QUALITY_HALF", "false").lower() in ("1", "true", "yes")
    if quality_half:
        half = max(1, len(out) // 2)
        cap = min(cap, half) if cap is not None else half

    if cap is not None and int(cap) > 0:
        out = out[: int(cap)]
    return out


def _rotate_offset_path(name: str = "fortress") -> Path:
    if name == "paper_active":
        return Path(os.getenv("PAPER_ACTIVE_ROTATE_FILE", "data/.paper_active_scan_offset.json"))
    return Path(os.getenv("FORTRESS_ROTATE_FILE", "data/.fortress_scan_offset.json"))


def _load_rotate_offset(n: int, *, name: str = "fortress") -> int:
    p = _rotate_offset_path(name)
    if not p.is_file() or n <= 0:
        return 0
    try:
        return int(json.loads(p.read_text()).get("offset", 0)) % n
    except Exception:
        return 0


def round_robin_by_first_letter(symbols: list[str]) -> list[str]:
    """Interleave symbols by first letter (legacy; prefer hash_shuffle for scan order)."""
    from collections import defaultdict

    buckets: dict[str, list[str]] = defaultdict(list)
    for s in symbols:
        key = (s.strip().upper()[:1] or "?")
        buckets[key].append(s.strip().upper())
    letters = sorted(buckets.keys())
    out: list[str] = []
    while any(buckets.values()):
        for letter in letters:
            if buckets[letter]:
                out.append(buckets[letter].pop(0))
    return out


def _scan_order_seed() -> str:
    """Daily seed; add hour when SCAN_ORDER_HOURLY=true so order shifts intraday."""
    from datetime import datetime, timezone

    base = os.getenv("SCAN_ORDER_SEED", "").strip()
    if base:
        return base
    now = datetime.now(timezone.utc)
    if os.getenv("SCAN_ORDER_HOURLY", "true").lower() in ("1", "true", "yes"):
        return now.strftime("%Y%m%d%H")
    return now.strftime("%Y%m%d")


def hash_shuffle(symbols: list[str], seed: str | None = None) -> list[str]:
    """Stable pseudo-random order — no A→B→C letter walk."""
    import hashlib

    s = seed or _scan_order_seed()
    return sorted(
        [x.strip().upper() for x in symbols if x],
        key=lambda t: hashlib.sha256(f"{s}:{t}".encode()).hexdigest(),
    )


def _save_rotate_offset(offset: int, pool_size: int, *, name: str = "fortress") -> None:
    if pool_size <= 0:
        return
    p = _rotate_offset_path(name)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"offset": int(offset) % pool_size}))


def apply_scan_order(symbols: list[str], *, rotate: bool = True) -> list[str]:
    """Hash-shuffle scan order by default — breaks A/B/C alphabet walks."""
    syms = [s.strip().upper() for s in symbols if s and is_tradeable_equity(s)]
    if not syms:
        return []
    mode = os.getenv("SCAN_ORDER_MODE", "hash").strip().lower()
    if mode in ("round_robin", "rr") and rotate:
        syms = round_robin_by_first_letter(syms)
    elif mode in ("random", "rand"):
        random.shuffle(syms)
    else:
        syms = hash_shuffle(syms, _scan_order_seed())
    if os.getenv("PAPER_SIM_SHUFFLE_UNIVERSE", "false").lower() in ("1", "true", "yes"):
        extra = os.getenv("PAPER_SIM_SHUFFLE_SEED", "").strip() or _scan_order_seed()
        syms = hash_shuffle(syms, f"{extra}:paper")
    return syms


def load_fortress_scan_list(max_symbols: int, shuffle_rest: bool = True) -> list[str]:
    """
    Full trained equity universe (no prefix filter):
    1) Optional: top-N by market cap (data/top100_market_cap.json) with models
    2) Rotating slice through the rest so all letters get scanned over time
    """
    raw = os.getenv("LIVE_SYMBOL_LIST", "").strip()
    if raw:
        syms = [s.strip().upper() for s in raw.split(",") if s.strip() and is_tradeable_equity(s)]
        if shuffle_rest:
            random.shuffle(syms)
        return syms[: max_symbols or len(syms)]

    pool = symbols_with_daily_models()
    if not pool:
        return []

    pool_set = set(pool)
    prioritize = os.getenv("FORTRESS_SCAN_PRIORITIZE", "top100").strip().lower()
    if prioritize in ("top100", "well_known", "mega"):
        priority = [s for s in load_top100_symbols() if s in pool_set]
    else:
        priority = []
    priority_set = frozenset(priority)
    rest = [s for s in pool if s not in priority_set]
    rest_ordered = hash_shuffle(rest, f"{_scan_order_seed()}:fortress")
    off = _load_rotate_offset(len(rest_ordered)) if rest_ordered else 0
    rest_span = rest_ordered[off:] + rest_ordered[:off] if rest_ordered else []
    if shuffle_rest and rest_span:
        chunk = hash_shuffle(rest_span, f"{_scan_order_seed()}:pass")
    else:
        chunk = list(rest_span)

    cap = max_symbols if max_symbols > 0 else len(pool)
    whole = os.getenv("FORTRESS_SCAN_WHOLE_DB", "false").lower() in ("1", "true", "yes")
    if whole and (max_symbols <= 0 or max_symbols >= len(pool)):
        # Score the entire trained book this pass (hash-shuffled, not A→Z).
        cap = len(pool)
        rest_take = len(rest_ordered)
        chunk_slice = list(rest_ordered)
    else:
        rest_take = max(0, cap - len(priority))
        if whole:
            # Large rotating chunk so the full book is covered in a few passes.
            rest_take = max(rest_take, min(len(rest_ordered), int(os.getenv("FORTRESS_WHOLE_CHUNK", "400"))))
            cap = max(cap, len(priority) + rest_take)
        chunk_slice = chunk[:rest_take]
    # Sheldon EV hot list + international ADRs always ride along (does not drop rest).
    sheldon: list[str] = []
    try:
        from analytics.sheldon_head import sheldon_priority_tickers

        sheldon = [s for s in sheldon_priority_tickers() if s in pool_set]
    except Exception:
        sheldon = []
    combined = list(dict.fromkeys(sheldon + priority + chunk_slice))
    try:
        from alt_assets import alt_scan_symbols, trade_alts_enabled

        if trade_alts_enabled():
            alts = [s for s in alt_scan_symbols() if s in pool_set or s.endswith("-USD")]
            # Crypto models use Yahoo names (BTC-USD); include if a daily pickle exists.
            model_dir = Path(os.getenv("MODEL_DIR", "models"))
            have_alt = []
            for s in alts:
                p = model_dir / f"{s}_model.pkl"
                if p.is_file() or s in pool_set:
                    have_alt.append(s)
            if have_alt:
                combined = list(dict.fromkeys(have_alt + combined))
                log.info("[FORTRESS] alt sleeve (crypto/commodities) prepended=%d", len(have_alt))
    except Exception:
        pass
    out = apply_scan_order(combined)
    if not whole:
        out = out[:cap]
    if rest_take > 0 and rest_ordered:
        _save_rotate_offset(off + rest_take, len(rest_ordered))

    if os.getenv("FORTRESS_SCAN_QUALITY_ONLY", "false").lower() in ("1", "true", "yes"):
        out = [s for s in out if is_top100_equity(s) or is_hft_quality_equity(s)]
        out = apply_scan_order(out)[:cap]

    log.info(
        "[FORTRESS] universe equities=%d  prioritized=%d  sheldon=%d  this_pass=%d  rotate_off=%d  (hash-shuffle scan)",
        len(pool),
        len(priority),
        len(sheldon),
        len(out),
        off,
    )
    return out
