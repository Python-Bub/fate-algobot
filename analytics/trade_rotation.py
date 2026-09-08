"""Rotate picks and trades — avoid repeating the same symbols every pass."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _recent_file() -> Path:
    return Path(os.getenv("RECENT_TRADES_FILE", str(ROOT / "data" / "recent_trades.json")))


def _last_picks_file() -> Path:
    return Path(os.getenv("LAST_PICKS_FILE", str(ROOT / "data" / "last_algorithm_picks.json")))


def __getattr__(name: str):
    """Back-compat for tools that import RECENT_FILE / LAST_PICKS_FILE."""
    if name == "RECENT_FILE":
        return _recent_file()
    if name == "LAST_PICKS_FILE":
        return _last_picks_file()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _enabled() -> bool:
    return os.getenv("USE_TRADE_ROTATION", "true").lower() in ("1", "true", "yes")


def cooldown_hours() -> float:
    return float(os.getenv("TRADE_COOLDOWN_HOURS", "24"))


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def record_trade(symbol: str, *, side: str = "BUY", source: str = "unknown") -> None:
    if not _enabled():
        return
    sym = str(symbol).strip().upper()
    if not sym:
        return
    doc = _load_json(_recent_file())
    trades = list(doc.get("trades") or [])
    trades.append(
        {
            "symbol": sym,
            "side": side.upper(),
            "source": source,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
    )
    keep = int(os.getenv("RECENT_TRADES_MAX", "500"))
    doc["trades"] = trades[-keep:]
    _save_json(_recent_file(), doc)


def _cooldown_sources_for(engine: str | None) -> frozenset[str] | None:
    """Which trade sources count toward cooldown for this engine (None = all)."""
    if not engine:
        return None
    eng = engine.strip().lower()
    if eng in ("fortress", "slow", "intraday"):
        raw = os.getenv(
            "FORTRESS_COOLDOWN_SOURCES",
            "fortress,day_trade,weekly,paper_sim",
        )
        return frozenset(s.strip().lower() for s in raw.split(",") if s.strip())
    if eng in ("hft", "obi", "subsecond"):
        raw = os.getenv("HFT_COOLDOWN_SOURCES", "hft,obi,mr,alpaca_sync")
        return frozenset(s.strip().lower() for s in raw.split(",") if s.strip())
    return None


def recent_symbols(
    *,
    hours: float | None = None,
    sources: frozenset[str] | None = None,
    side: str | None = "BUY",
) -> frozenset[str]:
    if not _enabled():
        return frozenset()
    hrs = float(hours if hours is not None else cooldown_hours())
    cutoff = time.time() - hrs * 3600.0
    out: set[str] = set()
    side_u = (side or "").strip().upper()
    for t in _load_json(_recent_file()).get("trades") or []:
        sym = str(t.get("symbol", "")).upper()
        if not sym:
            continue
        if sources is not None:
            src = str(t.get("source", "unknown")).strip().lower()
            if src not in sources:
                continue
        if side_u and str(t.get("side", "BUY")).upper() != side_u:
            continue
        ts = t.get("ts", "")
        try:
            when = datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
        except Exception:
            when = time.time()
        if when >= cutoff:
            out.add(sym)
    return frozenset(out)


def in_cooldown(
    symbol: str,
    *,
    hours: float | None = None,
    for_engine: str | None = "fortress",
) -> bool:
    sources = _cooldown_sources_for(for_engine)
    return symbol.strip().upper() in recent_symbols(hours=hours, sources=sources, side="BUY")


def apply_score_penalty(
    symbol: str,
    score: float,
    *,
    for_engine: str | None = "fortress",
) -> float:
    """Down-rank symbols traded recently so the next pass surfaces fresh names."""
    if not _enabled():
        return float(score)
    sym = symbol.strip().upper()
    # Soft penalty for last-algorithm picks even outside hard cooldown window
    if sym in last_picks():
        score = float(score) * float(os.getenv("TRADE_LAST_PICK_SCORE_MULT", "0.55"))
    if not in_cooldown(sym, for_engine=for_engine):
        return float(score)
    mult = float(os.getenv("TRADE_COOLDOWN_SCORE_MULT", "0.12"))
    return float(score) * mult


def filter_rows_by_cooldown(rows: list[dict], *, allow_if_empty: bool = True) -> list[dict]:
    if not _enabled():
        return rows
    cool = recent_symbols()
    if not cool:
        return rows
    fresh = [r for r in rows if str(r.get("ticker", "")).upper() not in cool]
    if fresh or not allow_if_empty:
        return fresh
    return rows


def save_picks(tickers: list[str], *, source: str = "paper_sim") -> None:
    doc = {
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "tickers": [str(t).upper() for t in tickers if t],
    }
    _save_json(_last_picks_file(), doc)


def last_picks() -> frozenset[str]:
    doc = _load_json(_last_picks_file())
    return frozenset(str(t).upper() for t in (doc.get("tickers") or []) if t)


def _letter(ticker: str) -> str:
    t = str(ticker).strip().upper()
    return t[0] if t else "?"


def _letter_diversify_enabled() -> bool:
    return os.getenv("TRADE_LETTER_DIVERSIFY", "true").lower() in ("1", "true", "yes")


def max_buys_per_letter() -> int:
    return max(1, int(os.getenv("TRADE_MAX_BUYS_PER_LETTER", "1")))


def max_held_per_letter() -> int:
    return max(1, int(os.getenv("TRADE_MAX_HELD_PER_LETTER", "2")))


def letter_counts(symbols: frozenset[str] | set[str] | list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for s in symbols:
        L = _letter(str(s))
        out[L] = out.get(L, 0) + 1
    return out


def apply_letter_penalty(
    symbol: str,
    score: float,
    *,
    held: frozenset[str] | set[str] | list[str] | None = None,
) -> float:
    """Down-rank when portfolio already holds too many names with the same first letter."""
    if not _letter_diversify_enabled():
        return float(score)
    held_set = frozenset(str(s).upper() for s in (held or ()))
    cnt = letter_counts(held_set).get(_letter(symbol), 0)
    cap = max_held_per_letter()
    if cnt >= cap:
        return float(score) * 0.05
    if cnt == cap - 1:
        return float(score) * 0.55
    return float(score)


def select_diversified_buys(
    candidates: list[dict],
    max_n: int,
    *,
    score_key: str = "score",
    ticker_key: str = "ticker",
    held: frozenset[str] | set[str] | list[str] | None = None,
    max_per_letter: int | None = None,
) -> list[dict]:
    """Greedy top-score picks with a cap per first letter (stops AAPL+AMZN+AVGO same pass).

    FORCE/STICK candidates (force_priority=True) are pinned first so high-conviction
    UP predictions cannot lose the pass to index-ETF spam.
    """
    if max_n <= 0 or not candidates:
        return []

    forced = [c for c in candidates if c.get("force_priority")]
    rest = [c for c in candidates if not c.get("force_priority")]
    held2 = set(str(s).upper() for s in (held or ()))
    try:
        from symbol_aliases import issuer_group
    except Exception:
        issuer_group = lambda s: str(s).strip().upper()  # noqa: E731
    seen_iss = {issuer_group(s) for s in held2 if s}

    def _take(c: dict) -> bool:
        t = str(c.get(ticker_key, "")).upper()
        if not t:
            return False
        g = issuer_group(t)
        if t in held2 or g in seen_iss:
            return False
        held2.add(t)
        seen_iss.add(g)
        return True

    # Force names skip letter diversify so a STICK buy is never dropped for letter caps.
    # They still cannot double an issuer (GOOG + GOOGL).
    forced_out = []
    for c in sorted(forced, key=lambda x: float(x.get(score_key, 0.0)), reverse=True):
        if _take(c):
            forced_out.append(c)
    if not _letter_diversify_enabled():
        out = list(forced_out)
        for c in sorted(rest, key=lambda x: float(x.get(score_key, 0.0)), reverse=True):
            if _take(c):
                out.append(c)
        return out[:max_n]

    out = forced_out[:max_n]
    if len(out) >= max_n:
        return out

    per_letter = max_per_letter if max_per_letter is not None else max_buys_per_letter()
    held_counts = letter_counts(frozenset(held2))
    batch_counts: dict[str, int] = {}
    for c in sorted(rest, key=lambda x: float(x.get(score_key, 0.0)), reverse=True):
        t = str(c.get(ticker_key, "")).upper()
        if not t or t in held2 or issuer_group(t) in seen_iss:
            continue
        L = _letter(t)
        if held_counts.get(L, 0) + batch_counts.get(L, 0) >= max_held_per_letter():
            continue
        if batch_counts.get(L, 0) >= per_letter:
            continue
        out.append(c)
        held2.add(t)
        seen_iss.add(issuer_group(t))
        batch_counts[L] = batch_counts.get(L, 0) + 1
        if len(out) >= max_n:
            break
    return out


def diversify_rank_key(ticker: str, base_rank: tuple) -> tuple:
    """Hourly jitter so tie-breaks shift without changing quality ordering much."""
    hour = datetime.now(timezone.utc).strftime("%Y%m%d%H")
    import hashlib

    jitter = int(hashlib.sha256(f"{hour}:{ticker}".encode()).hexdigest()[:8], 16)
    last = last_picks()
    repeat_penalty = 1 if ticker in last else 0
    return (*base_rank, -repeat_penalty, jitter)
