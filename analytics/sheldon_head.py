"""One adaptive expected-value head over the whole trained book.

Per-ticker GBDT/LSTM models stay — they are local expertise. This module is the
single “own head” that:
  • cheap-scores every trained symbol every hunt (not a 48-name slice)
  • hunts international ADRs via market-imbalance cheap-side
  • sizes with half-Kelly / scenario EV
  • rewrites ``data/intel/sheldon_board.json`` so fortress/paper chase the bests

Young-Sheldon vibe: physics-style expected value, rewrite the board every cycle,
never delete coverage.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "data" / "intel" / "sheldon_board.json"
OVERLAY = ROOT / "data" / "self_improve" / "sheldon_overlay.json"

# US-listed names whose economics live overseas — always in the hunt.
_INTL_PRIMARIES = (
    "BABA", "JD", "BIDU", "PDD", "TSM", "ASML", "SAP", "NVO", "SONY", "TM",
    "SHEL", "BP", "UL", "DEO", "RIO", "BHP", "VALE", "PBR", "ITUB", "INFY",
    "WIT", "SNY", "NICE", "NVS", "AZN", "GSK", "HSBC", "UBS", "ING", "SAN",
    "IBN", "HDB", "MELI", "SE", "NU", "SHOP", "CNI", "TD", "RY", "BMO",
    "SONY", "SNE", "TAK", "NMR", "SMFG", "MFG", "HMC",
)


def _b(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in ("1", "true", "yes", "on")


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _i(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def international_primaries() -> list[str]:
    extra = [
        s.strip().upper()
        for s in os.getenv("SHELDON_INTL_PRIMARIES", "").split(",")
        if s.strip()
    ]
    return list(dict.fromkeys(list(_INTL_PRIMARIES) + extra))


def _paper_scores() -> dict[str, float]:
    """Last paper_sim p_adj/score keyed by ticker — cheap whole-book memory."""
    out: dict[str, float] = {}
    try:
        from analytics.paper_report import latest_valid_report

        _path, doc = latest_valid_report(min_rows=1)
    except Exception:
        doc = None
    if not doc:
        # fallback newest file
        reps = sorted((ROOT / "reports").glob("paper_sim_*.json"))
        if not reps:
            return out
        try:
            doc = json.loads(reps[-1].read_text(encoding="utf-8"))
        except Exception:
            return out
    rows = doc.get("rows") or doc.get("results") or doc.get("picks") or []
    for row in rows:
        if not isinstance(row, dict):
            continue
        sym = str(row.get("ticker") or row.get("symbol") or "").upper()
        if not sym:
            continue
        p = row.get("p_adj") or row.get("p_up") or row.get("score")
        try:
            out[sym] = float(p)
        except (TypeError, ValueError):
            continue
    return out


def _valuation_tilts() -> dict[str, float]:
    doc = _read_json(ROOT / "data" / "intel" / "valuation_alerts.json")
    rows = doc.get("rows") or {}
    out: dict[str, float] = {}
    for sym, row in rows.items():
        if not isinstance(row, dict):
            continue
        if row.get("allow_long_boost") or row.get("investigate"):
            try:
                out[str(sym).upper()] = float(row.get("tilt") or 0.0)
            except (TypeError, ValueError):
                out[str(sym).upper()] = 0.06
    return out


def _imbalance_cheap() -> dict[str, float]:
    """Positive = US primary looks cheap vs overseas twin."""
    doc = _read_json(ROOT / "data" / "intel" / "market_imbalances.json")
    hits = doc.get("hits") or doc.get("imbalances") or doc.get("rows") or []
    out: dict[str, float] = {}
    if isinstance(hits, dict):
        hits = list(hits.values())
    for h in hits:
        if not isinstance(h, dict):
            continue
        sym = str(h.get("symbol") or h.get("primary") or "").upper()
        if not sym:
            continue
        try:
            direction = int(h.get("direction") or 0)
            score = float(h.get("score") or 0.0)
        except (TypeError, ValueError):
            continue
        if direction > 0 and score > 0:
            out[sym] = max(out.get(sym, 0.0), min(0.20, score * 0.15))
    return out


def _hft_news_tilt() -> dict[str, float]:
    doc = _read_json(ROOT / "data" / "intel" / "hft_trade_news.json")
    tickers = doc.get("tickers") or {}
    out: dict[str, float] = {}
    for sym, row in tickers.items():
        if not isinstance(row, dict):
            continue
        if row.get("allow_long") is False:
            out[str(sym).upper()] = -0.04
            continue
        try:
            out[str(sym).upper()] = float(row.get("tilt") or 0.0)
        except (TypeError, ValueError):
            continue
    return out


def _is_liquid_hunt_name(sym: str, *, intl_set: set[str]) -> bool:
    """Keep EV hunt on tradeable liquid names — junk CEFs/microcaps were topping the board."""
    s = str(sym).upper()
    if not s or len(s) > 5:
        return False
    try:
        from fortress_universe import is_core_trainable_equity, is_hft_quality_equity, is_top100_equity

        if not is_core_trainable_equity(s):
            return False
        if s in intl_set or is_top100_equity(s) or is_hft_quality_equity(s):
            return True
    except Exception:
        pass
    return False


def _whole_pool() -> list[str]:
    from fortress_universe import is_core_trainable_equity, symbols_with_daily_models

    pool = [s for s in symbols_with_daily_models() if is_core_trainable_equity(s)]
    if not pool:
        from fortress_universe import symbols_with_trained_intraday

        pool = [s for s in symbols_with_trained_intraday() if is_core_trainable_equity(s)]
    return pool


def _ev(p: float, mos_tilt: float, intl: float, news: float) -> float:
    """Scenario EV: edge * (1 + MOS) + international cheap + news, half-Kelly-shaped."""
    edge = max(-0.5, min(0.5, (float(p) - 0.5) * 2.0))
    # Contrarian: cheap international + undervalued news can rescue a mediocre p
    raw = edge + 1.4 * mos_tilt + 1.2 * intl + 0.8 * news
    # Half-Kelly squash — never explode a single name
    if raw <= 0:
        return raw * 0.5
    return min(0.35, raw * _f("SHELDON_KELLY_GAIN", 0.55))


def hunt(*, symbols: list[str] | None = None, top_n: int | None = None) -> dict[str, Any]:
    """Score the whole trained database with cheap local intel. Rewrite the board."""
    pool = symbols or _whole_pool()
    pool = list(dict.fromkeys(s.strip().upper() for s in pool if s))
    paper = _paper_scores()
    val = _valuation_tilts()
    intl = _imbalance_cheap()
    news = _hft_news_tilt()
    intl_set = set(international_primaries())
    if _b("SHELDON_LIQUID_ONLY", True):
        pool = [s for s in pool if _is_liquid_hunt_name(s, intl_set=intl_set)]

    rows: list[dict[str, Any]] = []
    for sym in pool:
        p = paper.get(sym)
        if p is None:
            p = 0.50
        mos = val.get(sym, 0.0)
        imb = intl.get(sym, 0.0)
        ntilt = news.get(sym, 0.0)
        if sym in intl_set and imb == 0.0:
            imb = 0.02  # mild international coverage bonus (not name favoritism — ADR book)
        ev = _ev(p, mos, imb, ntilt)
        rows.append(
            {
                "symbol": sym,
                "p": round(float(p), 4),
                "mos_tilt": round(float(mos), 4),
                "intl": round(float(imb), 4),
                "news": round(float(ntilt), 4),
                "ev": round(float(ev), 5),
                "international": sym in intl_set,
            }
        )

    rows.sort(key=lambda r: float(r["ev"]), reverse=True)
    keep = int(top_n if top_n is not None else _i("SHELDON_TOP_N", 80))
    bests = rows[: max(8, keep)]
    # Always surface international names that are in the top half of EV
    half = rows[: max(1, len(rows) // 2)]
    for r in half:
        if r.get("international") and r["symbol"] not in {b["symbol"] for b in bests}:
            bests.append(r)
            if len(bests) >= keep + 20:
                break

    gen = 1
    prev = _read_json(BOARD)
    try:
        gen = int(prev.get("generation") or 0) + 1
    except (TypeError, ValueError):
        gen = 1

    payload = {
        "updated_ms": int(time.time() * 1000),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "generation": gen,
        "scanned": len(pool),
        "paper_scores": len(paper),
        "top_n": keep,
        "rationale": (
            "Expected-value hunt over the full trained book. Per-ticker models stay; "
            "this head rewrites the bests every cycle (Kelly-squashed EV + ADR cheap-side)."
        ),
        "bests": bests,
        "hot": [b["symbol"] for b in bests[: _i("SHELDON_HOT_N", 24)]],
    }
    BOARD.parent.mkdir(parents=True, exist_ok=True)
    BOARD.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    overlay = {
        "generation": gen,
        "updated_at": payload["updated_at"],
        "hot": payload["hot"],
        "tilts": {b["symbol"]: round(min(0.12, max(0.0, float(b["ev"]))), 4) for b in bests[:40]},
        "rewrite": True,
        "objective": "constantly earn — hunt best EV internationally, rewrite board",
    }
    OVERLAY.parent.mkdir(parents=True, exist_ok=True)
    OVERLAY.write_text(json.dumps(overlay, indent=2), encoding="utf-8")
    return payload


def load_board() -> dict[str, Any]:
    return _read_json(BOARD)


def sheldon_priority_tickers(limit: int | None = None) -> list[str]:
    """Force-scan list: hot EV names + international primaries that have models."""
    n = int(limit if limit is not None else _i("SHELDON_FORCE_SCAN", 40))
    board = load_board()
    hot = [str(s).upper() for s in (board.get("hot") or []) if s]
    if not hot:
        hot = [str(b.get("symbol") or "").upper() for b in (board.get("bests") or [])[:n] if b]
    try:
        from fortress_universe import symbols_with_daily_models

        have = set(symbols_with_daily_models())
    except Exception:
        have = set()
    intl = [s for s in international_primaries() if not have or s in have]
    out = list(dict.fromkeys(hot + intl))
    return out[: max(n, len(intl))]


def sheldon_rank_boost(symbol: str) -> tuple[float, dict[str, Any]]:
    """Bounded rank additive from the latest rewritten board."""
    if not _b("USE_SHELDON_HEAD", True):
        return 0.0, {"disabled": True}
    overlay = _read_json(OVERLAY)
    board = load_board()
    sym = symbol.strip().upper()
    meta: dict[str, Any] = {"head": "sheldon", "generation": overlay.get("generation") or board.get("generation")}
    tilts = overlay.get("tilts") or {}
    raw = 0.0
    if sym in tilts:
        try:
            raw = float(tilts[sym])
        except (TypeError, ValueError):
            raw = 0.0
        meta["hot"] = True
    else:
        # milder boost if in bests but not hot overlay
        for b in board.get("bests") or []:
            if str(b.get("symbol") or "").upper() == sym:
                try:
                    raw = min(0.06, max(0.0, float(b.get("ev") or 0.0)))
                except (TypeError, ValueError):
                    raw = 0.0
                meta["board"] = True
                break
    w = _f("RANK_W_SHELDON", 0.14)
    cap = _f("SHELDON_RANK_CAP", 0.12)
    applied = max(-cap, min(cap, raw * (w / 0.14)))
    meta["applied"] = round(applied, 4)
    return float(applied), meta
