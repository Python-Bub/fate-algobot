"""Discover subtle NON-well-known ties between companies.

Rejects obvious pairs (KO/PEP, same-industry megacaps, dual listings).
Keeps only residual / volume-echo links that survive market strip — the kind
of co-move that looks random on a chart but is statistically sticky.

Kinds emitted:
  resid_leadlag  — idio residual of A leads B (or vice versa)
  vol_echo       — volume surprise of A leads return of B (cross-industry)
  shared_resid   — shared residual factor after SPY strip (low raw corr, high resid corr)
  delayed_echo   — multi-day delayed residual response (economic echo lag)
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES_PATH = ROOT / "data" / "intel" / "subtle_tie_candidates.json"

# Well-known pairs we refuse to "discover" as subtle
_BANNED_PAIRS = frozenset(
    {
        frozenset({"KO", "PEP"}),
        frozenset({"V", "MA"}),
        frozenset({"XOM", "CVX"}),
        frozenset({"GOOG", "GOOGL"}),
        frozenset({"BRK-A", "BRK-B"}),
        frozenset({"MSFT", "AAPL"}),
        frozenset({"JPM", "BAC"}),
        frozenset({"META", "GOOGL"}),
        frozenset({"META", "GOOG"}),
        frozenset({"AMD", "NVDA"}),
        frozenset({"AVGO", "NVDA"}),
        frozenset({"META", "PLTR"}),
        frozenset({"TSLA", "MSFT"}),
        frozenset({"GOOGL", "AMZN"}),
        frozenset({"COST", "WMT"}),
        frozenset({"HD", "LOW"}),
        frozenset({"UNH", "ELV"}),
        frozenset({"PFE", "MRK"}),
        frozenset({"SPY", "QQQ"}),
        frozenset({"SPY", "IWM"}),
        frozenset({"QQQ", "IWM"}),
    }
)


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _b(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in ("1", "true", "yes", "on")


@dataclass
class SubtleTie:
    a: str
    b: str
    kind: str
    lag: int
    score: float
    direction_a: int  # when pattern fires, tilt for A
    direction_b: int
    stats: dict[str, float] = field(default_factory=dict)
    rationale: str = ""

    def pair_key(self) -> str:
        x, y = sorted([self.a.upper(), self.b.upper()])
        return f"{x}__{y}__{self.kind}__l{self.lag}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _is_banned(a: str, b: str) -> bool:
    return frozenset({a.upper(), b.upper()}) in _BANNED_PAIRS


def _same_obvious_industry(a: str, b: str) -> bool:
    """Reject same-industry pairs — those are well-known peer trades."""
    try:
        from analytics.industries.integration import get_industry_profile

        pa = get_industry_profile(a, use_cache=True) or {}
        pb = get_industry_profile(b, use_cache=True) or {}
        ia = str(pa.get("industry") or pa.get("sector") or "").strip().lower()
        ib = str(pb.get("industry") or pb.get("sector") or "").strip().lower()
        if ia and ib and ia == ib:
            return True
    except Exception:
        pass
    # Also reject if cross_company peers_for lists them
    try:
        from analytics.cross_company_links import peers_for

        if b.upper() in {p.upper() for p in peers_for(a, limit=8)}:
            return True
        if a.upper() in {p.upper() for p in peers_for(b, limit=8)}:
            return True
    except Exception:
        pass
    return False


def _fetch_ohlcv(symbol: str, period: str = "2y"):
    """Fetch daily OHLCV — prefer Yahoo/aliases when Polygon is exhausted."""
    sym = symbol.strip().upper()
    # 1) Project price loader (aliases, cache, Yahoo fallback)
    try:
        from datetime import datetime, timedelta

        from feature_engineering import load_price_data
        from symbol_aliases import price_data_fallback_symbols

        years = 2 if period.endswith("y") else 1
        try:
            years = max(1, int(period.replace("y", "").replace("Y", "") or 2))
        except ValueError:
            years = 2
        start = (datetime.utcnow() - timedelta(days=365 * years + 30)).strftime("%Y-%m-%d")
        for feed in price_data_fallback_symbols(sym) or [sym]:
            df = load_price_data(feed, start, None)
            if df is not None and not getattr(df, "empty", True) and len(df) >= 80:
                return df
    except Exception:
        pass
    try:
        from data_platform.market_prices import fetch_period

        df = fetch_period(sym, period=period, interval="1d")
        if df is not None and not df.empty:
            return df
    except Exception:
        pass
    try:
        import yfinance as yf
        from symbol_aliases import price_data_fallback_symbols

        for feed in price_data_fallback_symbols(sym) or [sym]:
            df = yf.Ticker(feed).history(period=period, auto_adjust=True, actions=False)
            if df is None or df.empty:
                continue
            if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
                df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
            return df
    except Exception:
        pass
    return None


def _rets_vol(df) -> tuple[np.ndarray, np.ndarray] | None:
    if df is None or getattr(df, "empty", True):
        return None
    ccol = "Close" if "Close" in df.columns else "close"
    if ccol not in df.columns:
        return None
    c = np.asarray(df[ccol].astype(float).values, dtype=float)
    if len(c) < 80:
        return None
    rets = np.diff(c) / np.maximum(c[:-1], 1e-12)
    vcol = "Volume" if "Volume" in df.columns else "volume"
    if vcol in df.columns:
        v = np.asarray(df[vcol].astype(float).values, dtype=float)
        # align to rets length
        v = v[-len(rets) :]
        # volume surprise vs 20d mean
        vs = np.zeros_like(rets)
        for i in range(len(rets)):
            lo = max(0, i - 20)
            mu = float(np.mean(v[lo:i])) if i > lo else float(v[i])
            vs[i] = float(v[i]) / (mu + 1e-12) - 1.0
    else:
        vs = np.zeros_like(rets)
    return rets, vs


def _residualize(rets: np.ndarray, mkt: np.ndarray) -> np.ndarray:
    n = min(len(rets), len(mkt))
    r, m = rets[-n:], mkt[-n:]
    if n < 40:
        return r.copy()
    # Rolling OLS beta on expanding prior window (simple: full-sample beta on prior)
    x = m - np.mean(m)
    y = r - np.mean(r)
    beta = float(np.dot(x, y) / (float(np.dot(x, x)) + 1e-12))
    return r - beta * m


def _leadlag(x: np.ndarray, y: np.ndarray, lag: int) -> float:
    """Corr(x[:-lag], y[lag:]) — does x lead y by `lag` days?"""
    if lag <= 0 or len(x) <= lag + 20:
        return 0.0
    a, b = x[:-lag], y[lag:]
    n = min(len(a), len(b))
    a, b = a[-n:], b[-n:]
    if float(np.std(a)) < 1e-12 or float(np.std(b)) < 1e-12:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def _score_pair(
    a: str,
    b: str,
    ra: np.ndarray,
    rb: np.ndarray,
    va: np.ndarray,
    vb: np.ndarray,
    mkt: np.ndarray,
) -> list[SubtleTie]:
    if _is_banned(a, b) or _same_obvious_industry(a, b):
        return []
    n = min(len(ra), len(rb), len(mkt), len(va), len(vb))
    if n < 80:
        return []
    ra, rb, va, vb, mkt = ra[-n:], rb[-n:], va[-n:], vb[-n:], mkt[-n:]
    ida, idb = _residualize(ra, mkt), _residualize(rb, mkt)

    raw_corr = float(np.corrcoef(ra, rb)[0, 1]) if float(np.std(ra)) > 1e-12 else 0.0
    resid_corr = float(np.corrcoef(ida, idb)[0, 1]) if float(np.std(ida)) > 1e-12 else 0.0

    out: list[SubtleTie] = []

    # 1) Shared residual: raw corr weak/moderate but residual corr strong → hidden factor
    if abs(raw_corr) < 0.35 and abs(resid_corr) >= _f("SUBTLE_MIN_RESID_CORR", 0.36):
        strength = min(1.0, (abs(resid_corr) - abs(raw_corr)) / 0.5)
        if strength >= 0.28:
            out.append(
                SubtleTie(
                    a=a,
                    b=b,
                    kind="shared_resid",
                    lag=0,
                    score=strength,
                    direction_a=1 if resid_corr > 0 else -1,
                    direction_b=1 if resid_corr > 0 else -1,
                    stats={"raw_corr": raw_corr, "resid_corr": resid_corr},
                    rationale=(
                        f"subtle shared residual {a}/{b}: raw_corr={raw_corr:.2f} "
                        f"but idio_corr={resid_corr:.2f} (not an obvious peer)"
                    ),
                )
            )

    # 2) Residual lead-lag (1..5 days)
    for lag in (1, 2, 3, 5):
        c_ab = _leadlag(ida, idb, lag)
        c_ba = _leadlag(idb, ida, lag)
        # Require leading corr clearly above contemporaneous resid corr
        if abs(c_ab) >= _f("SUBTLE_MIN_LEAD", 0.14) and abs(c_ab) > abs(resid_corr) + 0.03:
            strength = min(1.0, abs(c_ab) / 0.45)
            out.append(
                SubtleTie(
                    a=a,
                    b=b,
                    kind="resid_leadlag",
                    lag=lag,
                    score=strength,
                    direction_a=1 if c_ab > 0 else -1,  # A leads → A move foreshadows B
                    direction_b=1 if c_ab > 0 else -1,
                    stats={"lead_corr": c_ab, "resid_corr": resid_corr, "leader": 1.0},
                    rationale=f"subtle idio lead: {a} leads {b} by {lag}d corr={c_ab:.2f}",
                )
            )
        if abs(c_ba) >= _f("SUBTLE_MIN_LEAD", 0.14) and abs(c_ba) > abs(resid_corr) + 0.03:
            strength = min(1.0, abs(c_ba) / 0.45)
            out.append(
                SubtleTie(
                    a=b,
                    b=a,
                    kind="resid_leadlag",
                    lag=lag,
                    score=strength,
                    direction_a=1 if c_ba > 0 else -1,
                    direction_b=1 if c_ba > 0 else -1,
                    stats={"lead_corr": c_ba, "resid_corr": resid_corr, "leader": 1.0},
                    rationale=f"subtle idio lead: {b} leads {a} by {lag}d corr={c_ba:.2f}",
                )
            )

    # 3) Volume surprise of A → residual return of B (cross echo)
    for lag in (1, 2, 3):
        c = _leadlag(va, idb, lag)
        if abs(c) >= _f("SUBTLE_MIN_VOL_ECHO", 0.14):
            strength = min(1.0, abs(c) / 0.45)
            out.append(
                SubtleTie(
                    a=a,
                    b=b,
                    kind="vol_echo",
                    lag=lag,
                    score=strength * 0.95,
                    direction_a=0,
                    direction_b=1 if c > 0 else -1,
                    stats={"vol_lead_corr": c},
                    rationale=f"subtle vol echo: {a} volume → {b} idio in {lag}d corr={c:.2f}",
                )
            )
        c2 = _leadlag(vb, ida, lag)
        if abs(c2) >= _f("SUBTLE_MIN_VOL_ECHO", 0.14):
            strength = min(1.0, abs(c2) / 0.45)
            out.append(
                SubtleTie(
                    a=b,
                    b=a,
                    kind="vol_echo",
                    lag=lag,
                    score=strength * 0.95,
                    direction_a=0,
                    direction_b=1 if c2 > 0 else -1,
                    stats={"vol_lead_corr": c2},
                    rationale=f"subtle vol echo: {b} volume → {a} idio in {lag}d corr={c2:.2f}",
                )
            )

    # 4) Delayed echo: lag 4–8 residual response (slow economic transmission)
    for lag in (4, 6, 8):
        c = _leadlag(ida, idb, lag)
        if abs(c) >= _f("SUBTLE_MIN_DELAYED", 0.14) and abs(c) > abs(resid_corr) + 0.05:
            strength = min(1.0, abs(c) / 0.45)
            out.append(
                SubtleTie(
                    a=a,
                    b=b,
                    kind="delayed_echo",
                    lag=lag,
                    score=strength * 0.9,
                    direction_a=1 if c > 0 else -1,
                    direction_b=1 if c > 0 else -1,
                    stats={"delayed_corr": c},
                    rationale=f"subtle delayed echo: {a}→{b} lag={lag}d corr={c:.2f}",
                )
            )

    # Deduplicate by kind+lag keep best score
    best: dict[str, SubtleTie] = {}
    for t in out:
        k = f"{t.kind}:l{t.lag}:{t.a}:{t.b}"
        if k not in best or t.score > best[k].score:
            best[k] = t
    return list(best.values())


def candidate_universe(limit: int = 60) -> list[str]:
    out: list[str] = []
    try:
        from fortress_universe import load_top100_symbols

        out.extend(load_top100_symbols())
    except Exception:
        pass
    for path in (
        ROOT / "data" / "hft_quality_tickers.txt",
        ROOT / "data" / "fortress_priority.txt",
    ):
        if path.is_file():
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    s = line.strip().upper().split()[0] if line.strip() else ""
                    if s and len(s) <= 6:
                        out.append(s)
            except Exception:
                pass
    # Prefer liquid names; drop pure index ETFs for pair discovery (still use SPY as market)
    skip = {"SPY", "QQQ", "IWM", "DIA", "VOO", "VTI"}
    uniq = []
    seen = set()
    for s in out:
        u = s.upper()
        if u in skip or u in seen:
            continue
        seen.add(u)
        uniq.append(u)
        if len(uniq) >= limit:
            break
    return uniq


def discover_subtle_ties(
    *,
    symbols: list[str] | None = None,
    max_pairs: int | None = None,
    period: str = "2y",
) -> list[SubtleTie]:
    """Brute/sample cross-industry pairs; return ranked subtle ties."""
    if not _b("USE_SUBTLE_TIE_DISCOVER", True):
        return []
    syms = symbols or candidate_universe(int(_f("SUBTLE_UNIVERSE", 50)))
    max_pairs = max_pairs if max_pairs is not None else int(_f("SUBTLE_MAX_PAIRS", 120))

    mkt_df = _fetch_ohlcv(os.getenv("SUBTLE_BENCH", "SPY"), period=period)
    mkt_rv = _rets_vol(mkt_df)
    if mkt_rv is None:
        return []
    mkt = mkt_rv[0]

    cache: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for s in syms:
        rv = _rets_vol(_fetch_ohlcv(s, period=period))
        if rv is not None:
            cache[s] = rv

    names = list(cache.keys())
    # Dense cross-sample: every name vs several distant indices (mix industries)
    pairs: list[tuple[str, str]] = []
    steps = (3, 5, 7, 11, 13, 17, 19, 23, 29, 31)
    for i, a in enumerate(names):
        for step in steps:
            j = (i + step) % len(names)
            if j == i:
                continue
            b = names[j]
            pairs.append((a, b) if a < b else (b, a))
            if len(pairs) >= max_pairs * 3:
                break
        if len(pairs) >= max_pairs * 3:
            break
    # unique pairs
    seen_p = set()
    uniq_pairs = []
    for a, b in pairs:
        k = (a, b)
        if k in seen_p or a == b:
            continue
        seen_p.add(k)
        uniq_pairs.append((a, b))
        if len(uniq_pairs) >= max_pairs:
            break

    ties: list[SubtleTie] = []
    for a, b in uniq_pairs:
        ra, va = cache[a]
        rb, vb = cache[b]
        ties.extend(_score_pair(a, b, ra, rb, va, vb, mkt))

    ties.sort(key=lambda t: t.score, reverse=True)
    # Cap promotions
    cap = int(_f("SUBTLE_TOP_TIES", 25))
    ties = ties[:cap]

    CANDIDATES_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts": time.time(),
        "iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n": len(ties),
        "ties": [t.to_dict() for t in ties],
    }
    CANDIDATES_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return ties


def tie_hash(tie: SubtleTie) -> str:
    h = hashlib.sha1(tie.pair_key().encode()).hexdigest()[:10]
    return h
