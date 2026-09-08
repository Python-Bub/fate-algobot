"""Market imbalances — same economic exposure, different venue/region price.

Detects when dual listings, ADRs, share classes, or FX-linked twins trade away
from their historical parity (same stock / company, different region or ticker).

Examples:
  BABA (US) vs 9988.HK (HK) after FX + ADR ratio
  TSM vs 2330.TW
  GOOG vs GOOGL (share class)
  SHEL vs SHEL.L

Outputs: `data/intel/market_imbalances.json` and feeds hidden-anomaly hits so
fortress can softly prefer the cheap side of a stretched pair.
"""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "data" / "intel" / "market_imbalances.json"
PAIRS_PATH = ROOT / "data" / "intel" / "cross_listing_pairs.json"


@dataclass
class ImbalanceHit:
    symbol: str  # primary (usually US/Alpaca-tradable) side
    peer: str
    score: float  # 0..1 how stretched vs history
    direction: int  # +1 primary looks cheap vs peer, -1 rich
    gap_pct: float  # (primary_fair - peer_usd) / mid  (signed)
    z: float
    fx: str
    ratio: float
    reasons: list[str] = field(default_factory=list)
    primary_px: float = 0.0
    peer_px_local: float = 0.0
    peer_px_usd: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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


def default_pairs() -> list[dict[str, Any]]:
    """Curated same-company / same-exposure twins across regions or share classes.

    `ratio` = how many local shares equal one primary share (ADR ratio), or
    share-class conversion (BRK.A / BRK.B ≈ 1500).
    `fx` = Yahoo FX pair that converts local → USD (local_ccy per 1 USD for
    XXXUSD=X style, or inverted for USDXXX=X — see `_fx_to_usd`).
    """
    return [
        # Share classes / dual US
        {"primary": "GOOGL", "peer": "GOOG", "fx": "USDUSD", "ratio": 1.0, "note": "share_class"},
        {"primary": "BRK-B", "peer": "BRK-A", "fx": "USDUSD", "ratio": 0.0006666667, "note": "share_class"},
        # ADR / local
        {"primary": "BABA", "peer": "9988.HK", "fx": "USDHKD=X", "ratio": 8.0, "note": "adr_hk"},
        {"primary": "JD", "peer": "9618.HK", "fx": "USDHKD=X", "ratio": 2.0, "note": "adr_hk"},
        {"primary": "BIDU", "peer": "9888.HK", "fx": "USDHKD=X", "ratio": 8.0, "note": "adr_hk"},
        {"primary": "TSM", "peer": "2330.TW", "fx": "USDTWD=X", "ratio": 5.0, "note": "adr_tw"},
        {"primary": "ASML", "peer": "ASML.AS", "fx": "EURUSD=X", "ratio": 1.0, "note": "dual_eu"},
        {"primary": "SAP", "peer": "SAP.DE", "fx": "EURUSD=X", "ratio": 1.0, "note": "dual_eu"},
        {"primary": "NVO", "peer": "NOVO-B.CO", "fx": "USDDKK=X", "ratio": 1.0, "note": "adr_dk"},
        {"primary": "SONY", "peer": "6758.T", "fx": "USDJPY=X", "ratio": 1.0, "note": "adr_jp"},
        {"primary": "TM", "peer": "7203.T", "fx": "USDJPY=X", "ratio": 10.0, "note": "adr_jp"},
        # HMC ADR ratio varies — omit until confirmed
        {"primary": "SHEL", "peer": "SHEL.L", "fx": "GBPUSD=X", "ratio": 2.0, "note": "dual_uk"},
        {"primary": "BP", "peer": "BP.L", "fx": "GBPUSD=X", "ratio": 6.0, "note": "dual_uk"},
        {"primary": "UL", "peer": "ULVR.L", "fx": "GBPUSD=X", "ratio": 1.0, "note": "adr_uk"},
        {"primary": "DEO", "peer": "DGE.L", "fx": "GBPUSD=X", "ratio": 1.0, "note": "adr_uk"},
        {"primary": "RIO", "peer": "RIO.L", "fx": "GBPUSD=X", "ratio": 1.0, "note": "dual_uk"},
        {"primary": "BHP", "peer": "BHP.AX", "fx": "AUDUSD=X", "ratio": 1.0, "note": "dual_au"},
        {"primary": "VALE", "peer": "VALE3.SA", "fx": "USDBRL=X", "ratio": 1.0, "note": "adr_br"},
        {"primary": "PBR", "peer": "PETR4.SA", "fx": "USDBRL=X", "ratio": 2.0, "note": "adr_br"},
        {"primary": "ITUB", "peer": "ITUB4.SA", "fx": "USDBRL=X", "ratio": 1.0, "note": "adr_br"},
        {"primary": "INFY", "peer": "INFY.NS", "fx": "USDINR=X", "ratio": 1.0, "note": "adr_in"},
        {"primary": "WIT", "peer": "WIPRO.NS", "fx": "USDINR=X", "ratio": 1.0, "note": "adr_in"},
        {"primary": "SNY", "peer": "SAN.PA", "fx": "EURUSD=X", "ratio": 2.0, "note": "adr_fr"},
        {"primary": "NICE", "peer": "NICE.TA", "fx": "USDILS=X", "ratio": 1.0, "note": "adr_il"},
        {"primary": "NVS", "peer": "NOVN.SW", "fx": "USDCHF=X", "ratio": 1.0, "note": "adr_ch"},
        {"primary": "AZN", "peer": "AZN.L", "fx": "GBPUSD=X", "ratio": 1.0, "note": "adr_uk"},
        {"primary": "GSK", "peer": "GSK.L", "fx": "GBPUSD=X", "ratio": 1.0, "note": "adr_uk"},
        {"primary": "HSBC", "peer": "HSBA.L", "fx": "GBPUSD=X", "ratio": 1.0, "note": "adr_uk"},
        {"primary": "UBS", "peer": "UBSG.SW", "fx": "USDCHF=X", "ratio": 1.0, "note": "adr_ch"},
        {"primary": "ING", "peer": "INGA.AS", "fx": "EURUSD=X", "ratio": 1.0, "note": "adr_nl"},
        {"primary": "SAN", "peer": "SAN.MC", "fx": "EURUSD=X", "ratio": 1.0, "note": "adr_es"},
        {"primary": "IBN", "peer": "IBN.NS", "fx": "USDINR=X", "ratio": 1.0, "note": "adr_in"},
        {"primary": "HDB", "peer": "HDFCBANK.NS", "fx": "USDINR=X", "ratio": 1.0, "note": "adr_in"},
        {"primary": "SHOP", "peer": "SHOP.TO", "fx": "USDCAD=X", "ratio": 1.0, "note": "dual_ca"},
        {"primary": "TD", "peer": "TD.TO", "fx": "USDCAD=X", "ratio": 1.0, "note": "dual_ca"},
        {"primary": "RY", "peer": "RY.TO", "fx": "USDCAD=X", "ratio": 1.0, "note": "dual_ca"},
        # Tight US twins only (same NAV exposure)
        {"primary": "SPY", "peer": "IVV", "fx": "USDUSD", "ratio": 1.0, "note": "etf_twin"},
    ]


def load_pairs() -> list[dict[str, Any]]:
    if PAIRS_PATH.is_file():
        try:
            doc = json.loads(PAIRS_PATH.read_text(encoding="utf-8"))
            pairs = doc.get("pairs") if isinstance(doc, dict) else doc
            if isinstance(pairs, list) and pairs:
                return pairs
        except Exception:
            pass
    pairs = default_pairs()
    try:
        PAIRS_PATH.parent.mkdir(parents=True, exist_ok=True)
        PAIRS_PATH.write_text(
            json.dumps({"pairs": pairs, "note": "edit to add dual listings / ADRs"}, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass
    return pairs


def _fetch_close_series(symbol: str, period: str = "6mo"):
    try:
        from data_platform.market_prices import fetch_period

        df = fetch_period(symbol, period=period, interval="1d")
        if df is not None and not getattr(df, "empty", True):
            return df
    except Exception:
        pass
    try:
        import yfinance as yf

        df = yf.download(symbol, period=period, interval="1d", progress=False, auto_adjust=True)
        if df is None or df.empty:
            return None
        if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        return df
    except Exception:
        return None


def _last_close(df) -> float | None:
    if df is None or getattr(df, "empty", True):
        return None
    col = "Close" if "Close" in df.columns else "close"
    if col not in df.columns:
        return None
    try:
        v = float(df[col].astype(float).iloc[-1])
        return v if v > 0 and math.isfinite(v) else None
    except Exception:
        return None


def _close_array(df) -> np.ndarray | None:
    if df is None or getattr(df, "empty", True):
        return None
    col = "Close" if "Close" in df.columns else "close"
    if col not in df.columns:
        return None
    c = np.asarray(df[col].astype(float).values, dtype=float)
    return c if len(c) >= 20 else None


def _fx_to_usd_series(fx: str, period: str = "6mo") -> np.ndarray | None:
    """Return series of USD per 1 local currency unit (multiply local_px * fx → USD).

    Conventions:
      USDUSD → ones
      EURUSD=X → already EUR→USD
      GBPUSD=X → GBP→USD
      AUDUSD=X → AUD→USD
      USDHKD=X → HKD per USD → invert
      USDJPY=X → JPY per USD → invert
    """
    fx_u = (fx or "USDUSD").upper().replace("=X", "")
    if fx_u in ("USDUSD", "USD", "1", "NONE"):
        return None  # signal: use ones

    yahoo = fx if fx.endswith("=X") else f"{fx}=X"
    # Normalize common forms
    if fx_u.endswith("USD") and not fx_u.startswith("USD"):
        # EURUSD, GBPUSD, AUDUSD
        yahoo = f"{fx_u}=X"
        invert = False
    elif fx_u.startswith("USD") and fx_u != "USDUSD":
        # USDHKD, USDJPY, USDBRL, …
        yahoo = f"{fx_u}=X"
        invert = True
    else:
        invert = False

    df = _fetch_close_series(yahoo, period=period)
    c = _close_array(df)
    if c is None:
        return None
    if invert:
        c = 1.0 / np.maximum(c, 1e-12)
    return c


def _align_tail(*arrays: np.ndarray, n: int = 60) -> list[np.ndarray]:
    m = min(len(a) for a in arrays)
    m = min(m, n)
    return [a[-m:] for a in arrays]


def analyze_pair(pair: dict[str, Any], *, period: str = "6mo") -> ImbalanceHit | None:
    """Compare primary vs peer after FX + ratio; flag z-score stretch vs history."""
    primary = str(pair.get("primary") or "").strip().upper()
    peer = str(pair.get("peer") or "").strip()
    if not primary or not peer:
        return None
    ratio = float(pair.get("ratio") or 1.0)
    if ratio <= 0:
        ratio = 1.0
    fx = str(pair.get("fx") or "USDUSD")
    note = str(pair.get("note") or "cross_list")

    pdf = _fetch_close_series(primary, period=period)
    qdf = _fetch_close_series(peer, period=period)
    p = _close_array(pdf)
    q = _close_array(qdf)
    if p is None or q is None:
        return None

    # London Yahoo quotes are usually in pence (GBp); convert to pounds unless overridden.
    peer_u = peer.upper()
    gbx = bool(pair.get("gbx"))
    if gbx or (peer_u.endswith(".L") and pair.get("gbx") is not False):
        q = q / 100.0
        note = f"{note}+gbx"

    fx_s = _fx_to_usd_series(fx, period=period)
    if fx_s is None:
        fx_use = np.ones(len(q), dtype=float)
    elif len(fx_s) >= len(q):
        fx_use = fx_s[-len(q) :]
    else:
        fx_use = np.interp(
            np.linspace(0, 1, len(q)),
            np.linspace(0, 1, len(fx_s)),
            fx_s,
        )

    # `ratio` = multiplier from 1 peer share (in USD) → 1 primary share units.
    # ADR example BABA: 1 ADR ≈ 8 HK shares → ratio=8 → peer_as_primary = HK*fx*8
    # Share class BRK-B vs BRK-A: 1 A ≈ 1500 B → ratio=1/1500
    peer_as_primary = q * fx_use * ratio

    n = min(len(p), len(peer_as_primary))
    if n < 25:
        return None
    p = p[-n:]
    peer_as_primary = peer_as_primary[-n:]

    mid = (p + peer_as_primary) / 2.0
    gap = (p - peer_as_primary) / np.maximum(mid, 1e-12)
    hist = gap[:-1]
    last = float(gap[-1])
    mu = float(np.mean(hist))
    sigma = float(np.std(hist) + 1e-12)
    z = (last - mu) / sigma

    # Reject obvious misconfigured ratios (parity off by >40% and not a z-shock)
    max_abs = _f("MARKET_IMBALANCE_MAX_ABS_GAP", 0.40)
    if abs(last) > max_abs and abs(z) < 2.5:
        return None

    min_z = _f("MARKET_IMBALANCE_MIN_Z", 1.5)
    min_gap = _f("MARKET_IMBALANCE_MIN_GAP_PCT", 0.006)
    sticky = _f("MARKET_IMBALANCE_STICKY_GAP_PCT", 0.02)
    # Need a real gap; then either statistical shock OR sticky absolute premium/discount
    if abs(last) < min_gap:
        return None
    if abs(z) < min_z and abs(last) < sticky:
        return None

    score = min(
        1.0,
        max(0.0, (abs(z) - 1.0) / 3.0) * 0.55 + min(1.0, abs(last) / 0.05) * 0.45,
    )
    if score < _f("MARKET_IMBALANCE_MIN_SCORE", 0.30):
        return None

    # +1 = primary cheap vs peer parity (gap negative)
    direction = 1 if last < 0 else -1

    tag = "shock" if abs(z) >= min_z else "sticky_premium"
    reasons = [
        f"parity_gap={100 * last:+.2f}% z={z:+.2f} vs {peer} ({tag})",
        f"fx={fx} mult={ratio:g} ({note})",
        f"px primary={p[-1]:.2f} peer_as_primary={peer_as_primary[-1]:.2f}",
    ]
    return ImbalanceHit(
        symbol=primary.replace(".", "-"),
        peer=peer,
        score=float(score),
        direction=int(direction),
        gap_pct=float(last),
        z=float(z),
        fx=fx,
        ratio=ratio,
        reasons=reasons,
        primary_px=float(p[-1]),
        peer_px_local=float(q[-1]),
        peer_px_usd=float(peer_as_primary[-1]),
    )


def scan_imbalances(*, period: str = "6mo") -> list[ImbalanceHit]:
    if not _b("USE_MARKET_IMBALANCE", True):
        return []
    hits: list[ImbalanceHit] = []
    for pair in load_pairs():
        try:
            hit = analyze_pair(pair, period=period)
            if hit is not None:
                hits.append(hit)
        except Exception:
            continue
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits


def save_imbalances(hits: list[ImbalanceHit], path: Path | None = None) -> Path:
    p = path or OUT_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts": time.time(),
        "iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "count": len(hits),
        "hits": [h.to_dict() for h in hits],
        "by_symbol": {h.symbol: h.to_dict() for h in hits},
    }
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return p


def load_imbalances(path: Path | None = None) -> dict[str, Any]:
    p = path or OUT_PATH
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def imbalance_rank_boost(symbol: str) -> tuple[float, dict[str, Any]]:
    """Boost cheap side of a stretched cross-listing; soft-penalty if rich."""
    if not _b("USE_MARKET_IMBALANCE", True):
        return 0.0, {"enabled": False}
    doc = load_imbalances()
    age = time.time() - float(doc.get("ts") or 0)
    if age > _f("MARKET_IMBALANCE_MAX_AGE_SEC", 7200):
        return 0.0, {"stale": True, "age_sec": age}
    sym = symbol.strip().upper().replace(".", "-")
    row = (doc.get("by_symbol") or {}).get(sym)
    if not row:
        # Also match if this symbol is a peer mentioned in any hit
        for h in doc.get("hits") or []:
            if str(h.get("peer") or "").upper().replace(".", "-") == sym:
                # peer side: invert direction
                score = float(h.get("score") or 0)
                direction = -int(h.get("direction") or 0)
                w = _f("RANK_W_MARKET_IMBALANCE", 0.10)
                boost = w * score * (1.0 if direction >= 0 else -0.7)
                return float(boost), {
                    "hit": True,
                    "as_peer": True,
                    "primary": h.get("symbol"),
                    "score": score,
                    "direction": direction,
                    "boost": boost,
                }
        return 0.0, {"hit": False}
    score = float(row.get("score") or 0)
    direction = int(row.get("direction") or 0)
    w = _f("RANK_W_MARKET_IMBALANCE", 0.10)
    boost = w * score * (1.0 if direction >= 0 else -0.7)
    return float(boost), {
        "hit": True,
        "score": score,
        "direction": direction,
        "peer": row.get("peer"),
        "gap_pct": row.get("gap_pct"),
        "z": row.get("z"),
        "reasons": list(row.get("reasons") or [])[:3],
        "boost": boost,
    }


def run_imbalance_cycle() -> dict[str, Any]:
    hits = scan_imbalances()
    path = save_imbalances(hits)
    return {
        "imbalance_hits": len(hits),
        "imbalance_path": str(path),
        "imbalances": [h.to_dict() for h in hits[:15]],
    }
