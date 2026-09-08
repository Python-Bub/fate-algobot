"""Ingenious *public* event tells — used live, not after the 92-name crawl.

WMT 2026-08-20: the print was on the calendar; COST/TGT/DG were the same trade
and sat through the sympathy dump. These methods fire on first tick:

  1. Peer-print cascade — industry + hard retail/bank/tech graphs
  2. Quiet-period silence vs 8-K burst (EDGAR, cached)
  3. Form 4 cluster into the blackout (cached insider flow)
  4. Sector print crowding (how many peers print ±2d)
  5. Tape positioning — 5d vol z / range expansion into dte≤2
  6. Cross-listed / link-peer gap (BRK-A/B, GOOG/GOOGL)
  7. Straddle proxy — hist |print| × proximity (no options trading)

Does not guess unpublished results. Does not enable Alpaca options.
"""

from __future__ import annotations

import json
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
GAPS_PATH = ROOT / "data" / "intel" / "book_session_gaps.json"

INGENUITY_KEYS: tuple[str, ...] = (
    "peer_gap_signed",
    "peer_gap_abs",
    "peer_printed",
    "crowding",
    "eightk_burst",
    "silence",
    "form4_sell",
    "form4_buy",
    "vol_z5",
    "range_expand",
    "link_peer_gap",
    "straddle_proxy",
)

# Hard graphs desks actually trade. Industry map is the fallback.
HARD_PEERS: dict[str, tuple[str, ...]] = {
    "WMT": ("COST", "TGT", "DG", "DLTR", "KR", "BJ"),
    "COST": ("WMT", "TGT", "BJ", "DG"),
    "TGT": ("WMT", "COST", "DG", "DLTR"),
    "SBUX": ("MCD", "CMG", "YUM", "DPZ", "SBUX"),
    "MCD": ("SBUX", "YUM", "CMG", "QSR"),
    "AAPL": ("MSFT", "GOOGL", "GOOG", "AMZN", "META"),
    "MSFT": ("AAPL", "GOOGL", "AMZN", "ORCL"),
    "GOOGL": ("GOOG", "MSFT", "META", "AMZN", "AAPL"),
    "GOOG": ("GOOGL", "MSFT", "META", "AMZN"),
    "AMZN": ("WMT", "COST", "MSFT", "GOOGL", "AAPL"),
    "META": ("GOOGL", "GOOG", "AMZN", "SNAP"),
    "NVDA": ("AMD", "AVGO", "TSM", "INTC", "MU", "AMAT", "LRCX"),
    "AMD": ("NVDA", "INTC", "AVGO", "MU"),
    "TSLA": ("GM", "F", "RIVN", "LCID"),
    "BAC": ("JPM", "WFC", "C", "GS", "MS"),
    "JPM": ("BAC", "WFC", "C", "GS"),
    "XOM": ("CVX", "COP", "BP"),
    "CVX": ("XOM", "COP"),
    "JNJ": ("PFE", "MRK", "ABBV", "LLY"),
    "PFE": ("JNJ", "MRK", "ABBV", "MRNA"),
    "MRNA": ("PFE", "BNTX", "NVAX"),
    "NFLX": ("DIS", "PARA", "WBD"),
    "V": ("MA", "AXP"),
    "MA": ("V", "AXP"),
}


def _b(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def enabled() -> bool:
    return _b("USE_EVENT_INGENUITY", True)


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))


def industry_id(symbol: str) -> str:
    try:
        from analytics.industries.peer_ticker_map import TICKER_INDUSTRY

        row = TICKER_INDUSTRY.get(str(symbol).strip().upper())
        if isinstance(row, dict):
            return str(row.get("industry_id") or "unclassified")
        if isinstance(row, str):
            return row
    except Exception:
        pass
    return "unclassified"


_REV: dict[str, list[str]] | None = None


def industry_peers(symbol: str, *, cap: int = 16) -> list[str]:
    global _REV
    iid = industry_id(symbol)
    if not iid or iid == "unclassified":
        return []
    if _REV is None:
        rev: dict[str, list[str]] = {}
        try:
            from analytics.industries.peer_ticker_map import TICKER_INDUSTRY

            for t, meta in TICKER_INDUSTRY.items():
                i = meta.get("industry_id") if isinstance(meta, dict) else None
                if i:
                    rev.setdefault(str(i), []).append(str(t).upper())
        except Exception:
            rev = {}
        _REV = rev
    sym = symbol.strip().upper()
    out = [p for p in (_REV.get(iid) or []) if p != sym]
    return out[: max(1, int(cap))]


def peer_universe(symbol: str, *, cap: int = 12) -> list[str]:
    sym = symbol.strip().upper()
    hard = [p for p in HARD_PEERS.get(sym, ()) if p != sym]
    ind = industry_peers(sym, cap=cap)
    return list(dict.fromkeys(hard + ind))[:cap]


def score_peer_cascade(peer_gaps: list[float]) -> dict[str, float]:
    """peer_gaps = signed session returns of peers that already printed / are dumping."""
    gs = [float(g) for g in peer_gaps if g is not None]
    if not gs:
        return {"peer_gap_signed": 0.0, "peer_gap_abs": 0.0, "peer_printed": 0.0}
    worst = min(gs)
    # Weight the dump more than a mild green print (contagion is left-tailed).
    signed = 0.65 * worst + 0.35 * (sum(gs) / len(gs))
    return {
        "peer_gap_signed": _clip(signed, -0.25, 0.15),
        "peer_gap_abs": _clip(max(abs(g) for g in gs), 0.0, 0.25),
        "peer_printed": 1.0,
    }


def score_crowding(n_peer_prints: int, *, typical: int = 4) -> float:
    return _clip(float(n_peer_prints) / float(max(1, typical)), 0.0, 1.0)


def score_filings(
    *,
    eightk_2d: int = 0,
    eightk_14d: int = 0,
    form4_sell: float = 0.0,
    form4_buy: float = 0.0,
) -> dict[str, float]:
    burst = _clip(eightk_2d / 3.0, 0.0, 1.0)
    silence = 1.0 if eightk_14d <= 0 and eightk_2d <= 0 else 0.0
    sell = _clip(form4_sell, 0.0, 1.0)
    buy = _clip(form4_buy, 0.0, 1.0)
    return {
        "eightk_burst": burst,
        "silence": silence,
        "form4_sell": sell,
        "form4_buy": buy,
    }


def score_tape(*, vol_z5: float = 0.0, range_ratio: float = 1.0) -> dict[str, float]:
    return {
        "vol_z5": _clip(vol_z5 / 3.0, -1.0, 1.0),
        "range_expand": _clip((float(range_ratio) - 1.0), -0.5, 1.5),
    }


def straddle_proxy(hist_abs: float, dte: int | None) -> float:
    """Market-style implied-move stand-in: hist |print| × time kernel. No options."""
    h = max(0.0, float(hist_abs or 0.0))
    if dte is None:
        return _clip(h * 0.25, 0.0, 0.20)
    k = 2.718281828 ** (-abs(int(dte)) / 3.0)
    return _clip(h * k, 0.0, 0.20)


def contagion_decision(
    own_gap: float | None,
    peer_gaps: list[float],
) -> dict[str, Any]:
    """First-tick book action. Trim/kill only if WE are also red — never flatten greens.

    Always block *adds* into a peer dump (COST into WMT −9%).
    """
    out = {
        "kill": False,
        "trim_frac": 0.0,
        "watch": False,
        "block_add": False,
        "reason": "none",
        "worst_peer": None,
    }
    gs = [float(g) for g in peer_gaps if g is not None]
    if not gs:
        return out
    worst = min(gs)
    out["worst_peer"] = worst
    kill_at = -abs(_f("INGENUITY_PEER_KILL_PCT", 0.035))
    if worst > kill_at:
        return out
    out["watch"] = True
    out["block_add"] = True
    own = None if own_gap is None else float(own_gap)
    if own is None:
        out["reason"] = f"peer_dump_{worst:.3f}_no_own_quote"
        return out
    if own > 0.004:
        out["reason"] = "peer_dump_but_own_green"
        return out
    severe_peer = -abs(_f("INGENUITY_PEER_SEVERE_PCT", 0.05))
    if own <= -0.025 and worst <= severe_peer:
        out["kill"] = True
        out["trim_frac"] = 1.0
        out["reason"] = f"peer_cascade_kill own={own:.3f} peer={worst:.3f}"
        return out
    if own < 0.0:
        trim = 0.40 if worst <= severe_peer else 0.25
        out["trim_frac"] = trim
        out["reason"] = f"peer_cascade_trim own={own:.3f} peer={worst:.3f}"
        return out
    out["reason"] = f"peer_dump_watch peer={worst:.3f}"
    return out


def rank_boost_from_features(feats: dict[str, float], *, dte: int | None = None) -> float:
    """Immediate rank (not gated on event_learn skill). Negative = fade."""
    if not enabled():
        return 0.0
    near = dte is not None and 0 <= int(dte) <= 5
    signed = float(feats.get("peer_gap_signed") or 0.0)
    # Peer dump is a fade even if we don't have our own print.
    boost = 1.15 * signed
    boost -= 0.28 * float(feats.get("form4_sell") or 0.0)
    boost += 0.12 * float(feats.get("form4_buy") or 0.0)
    burst = float(feats.get("eightk_burst") or 0.0)
    boost += (0.22 if near else 0.08) * burst
    # Silence into a scheduled print = bigger surprise, not a directional call.
    # Slightly fade (unknown) rather than chase.
    if near:
        boost -= 0.06 * float(feats.get("silence") or 0.0)
        boost -= 0.10 * float(feats.get("crowding") or 0.0)  # crowded week → fade chase
    boost += 0.35 * float(feats.get("link_peer_gap") or 0.0)
    return _clip(boost, -1.0, 1.0)


def _today(as_of: date | None = None) -> date:
    if as_of is not None:
        return as_of
    return datetime.now(timezone.utc).date()


def _i(val: Any) -> int | None:
    if val is None or val == "":
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


_CAL_MEM: tuple[float, dict[str, Any]] | None = None


def _shared_cal() -> dict[str, Any]:
    global _CAL_MEM
    now = time.time()
    if _CAL_MEM is not None and now - _CAL_MEM[0] < 180:
        return _CAL_MEM[1]
    try:
        from intel.earnings_calendar import load_shared_earnings_calendar

        doc = load_shared_earnings_calendar() or {}
    except Exception:
        doc = {}
    _CAL_MEM = (now, doc)
    return doc


def crowding_from_calendar(symbol: str, *, as_of: date | None = None, window: int = 2) -> float:
    """How many peers print within ±window days (attention / gap-vol crowding)."""
    today = _today(as_of)
    peers = peer_universe(symbol, cap=24)
    if not peers:
        return 0.0
    n = 0
    try:
        rows = (_shared_cal().get("symbols") or {})
        for p in peers:
            row = rows.get(p) or rows.get(p.upper()) or {}
            nd = str(row.get("next_earnings_date") or "")[:10]
            if not nd:
                continue
            d = date.fromisoformat(nd)
            if abs((d - today).days) <= window:
                n += 1
    except Exception:
        return 0.0
    return score_crowding(n)


def _cached_open_web(symbol: str) -> dict[str, Any] | None:
    try:
        from intel import open_web_intel as ow

        hit = getattr(ow, "_CACHE", {}).get(symbol.strip().upper())
        if hit and ( __import__("time").time() - float(hit[0]) ) < 2400:
            return hit[1] if isinstance(hit[1], dict) else None
    except Exception:
        return None
    return None


def load_book_gaps() -> dict[str, float]:
    if not GAPS_PATH.is_file():
        return {}
    try:
        doc = json.loads(GAPS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: dict[str, float] = {}
    for src in (doc.get("sticky") or {}, doc.get("gaps") or {}):
        if not isinstance(src, dict):
            continue
        for k, v in src.items():
            try:
                out[str(k).upper()] = float(v)
            except (TypeError, ValueError):
                pass
    return out


def save_book_gaps(
    gaps: dict[str, float],
    *,
    as_of: date | None = None,
    dump_floor: float | None = None,
) -> None:
    """Persist session gaps so rank sees a peer dump after we already sold it."""
    today = (_today(as_of)).isoformat()
    floor = dump_floor if dump_floor is not None else -abs(_f("INGENUITY_PEER_KILL_PCT", 0.035))
    sticky: dict[str, float] = {}
    if GAPS_PATH.is_file():
        try:
            prev = json.loads(GAPS_PATH.read_text(encoding="utf-8"))
            if str(prev.get("as_of") or "") == today:
                sticky = {
                    str(k).upper(): float(v)
                    for k, v in (prev.get("sticky") or {}).items()
                    if v is not None
                }
        except Exception:
            sticky = {}
    for s, g in gaps.items():
        try:
            gf = float(g)
        except (TypeError, ValueError):
            continue
        if gf <= floor:
            sticky[str(s).upper()] = gf
    GAPS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = GAPS_PATH.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(
            {
                "as_of": today,
                "ts": time.time(),
                "gaps": {str(k).upper(): float(v) for k, v in gaps.items() if v is not None},
                "sticky": sticky,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    os.replace(tmp, GAPS_PATH)


def live_features(
    ticker: str,
    *,
    as_of: date | None = None,
    dte: int | None = None,
    hist_abs_1d: float = 0.0,
    peer_gaps: dict[str, float] | None = None,
    vol_z5: float = 0.0,
    range_ratio: float = 1.0,
    link_peer_gap: float | None = None,
) -> dict[str, float]:
    """Fill ingenuity features. peer_gaps is first-tick (Alpaca book) — no extra HTTP."""
    out = {k: 0.0 for k in INGENUITY_KEYS}
    if not enabled():
        return out
    sym = ticker.strip().upper()
    peers = peer_universe(sym, cap=12)
    book = peer_gaps if peer_gaps is not None else load_book_gaps()
    gaps: list[float] = []
    if book:
        for p in peers:
            g = book.get(p)
            if g is not None:
                try:
                    gaps.append(float(g))
                except (TypeError, ValueError):
                    pass
    out.update(score_peer_cascade(gaps))
    out["crowding"] = crowding_from_calendar(sym, as_of=as_of)
    out.update(score_tape(vol_z5=vol_z5, range_ratio=range_ratio))
    out["straddle_proxy"] = straddle_proxy(hist_abs_1d, dte)
    if link_peer_gap is not None:
        out["link_peer_gap"] = _clip(float(link_peer_gap), -0.25, 0.15)
    else:
        try:
            from analytics.cross_company_links import load_cache

            doc = load_cache() or {}
            for hit in doc.get("hits") or []:
                if str(hit.get("symbol") or "").upper() != sym:
                    continue
                peer = str(hit.get("peer") or "").upper()
                if book and peer in book and book[peer] is not None:
                    out["link_peer_gap"] = _clip(float(book[peer]), -0.25, 0.15)
                break
        except Exception:
            pass
    near = dte is not None and int(dte) <= 10
    if not near:
        return out
    web = _cached_open_web(sym)
    eightk_2d = eightk_14d = 0
    if web:
        sec = web.get("sec") or {}
        eightk_2d = int(sec.get("eightk_count") or web.get("eightk_count") or 0)
        eightk_14d = eightk_2d
    form4_sell = form4_buy = 0.0
    try:
        from intel.insider_signals import assess_insider_flow

        flow = assess_insider_flow(sym)
        sell = float(flow.get("recent_sell_shares") or 0.0)
        buy = float(flow.get("recent_buy_shares") or 0.0)
        tot = max(sell + buy, 1.0)
        form4_sell = sell / tot if sell > buy else 0.0
        form4_buy = buy / tot if buy > sell else 0.0
        if flow.get("block_long"):
            form4_sell = max(form4_sell, 0.85)
    except Exception:
        pass
    out.update(
        score_filings(
            eightk_2d=eightk_2d,
            eightk_14d=eightk_14d,
            form4_sell=form4_sell,
            form4_buy=form4_buy,
        )
    )
    return out


def block_add_on_peer_dump(symbol: str, own_gap: float | None = None) -> bool:
    """True → do not STICK-add this name (peer already dumped this session)."""
    if not enabled():
        return False
    book = load_book_gaps()
    peers = peer_universe(symbol, cap=12)
    pg = [book[p] for p in peers if p in book]
    return bool(contagion_decision(own_gap, pg).get("block_add"))


def event_ingenuity_rank_boost(
    ticker: str,
    *,
    mom_5d: float = 0.0,
    ret_1d: float | None = None,
    dte: int | None = None,
    hist_abs_1d: float = 0.0,
    peer_gaps: dict[str, float] | None = None,
    sleeve: str | None = None,
) -> tuple[float, dict[str, Any]]:
    meta: dict[str, Any] = {"applied": 0.0}
    if not enabled() or str(sleeve or "").lower() == "hft":
        meta["skipped"] = "disabled_or_hft"
        return 0.0, meta
    feats = live_features(
        ticker,
        dte=dte,
        hist_abs_1d=hist_abs_1d,
        peer_gaps=peer_gaps,
        vol_z5=0.0,
        range_ratio=1.0,
    )
    # Tape: mild fade if we already ripped into the print.
    if ret_1d is not None and float(ret_1d) >= 0.04:
        feats["peer_gap_signed"] = min(float(feats["peer_gap_signed"]), -0.01)
    boost = rank_boost_from_features(feats, dte=dte)
    if mom_5d and float(mom_5d) <= -0.04 and (dte is None or int(dte) <= 2):
        boost = min(boost, boost - 0.08)
    boost = _clip(boost, -1.0, 1.0)
    meta.update({"applied": round(boost, 4), "feats": {k: round(float(feats[k]), 4) for k in INGENUITY_KEYS}})
    return boost, meta


def contagion_for_book(
    positions: list[dict[str, Any]],
    *,
    gap_of=None,
) -> list[dict[str, Any]]:
    """Map open longs → peer-cascade actions. gap_of(pos) → session gap float|None."""
    if not enabled() or not positions:
        return []
    from analytics.earnings_gap_guard import session_gap_from_pos

    getter = gap_of or session_gap_from_pos
    gaps: dict[str, float] = {}
    qty: dict[str, float] = {}
    for p in positions:
        try:
            q = float(p.get("qty") or 0)
        except (TypeError, ValueError):
            continue
        if q <= 0:
            continue
        sym = str(p.get("symbol", "")).replace("/", "-").upper()
        if not sym:
            continue
        g = getter(p)
        qty[sym] = q
        if g is not None:
            try:
                gaps[sym] = float(g)
            except (TypeError, ValueError):
                pass
    actions: list[dict[str, Any]] = []
    for sym, q in qty.items():
        peers = peer_universe(sym, cap=12)
        pg = [gaps[p] for p in peers if p in gaps]
        dec = contagion_decision(gaps.get(sym), pg)
        if not (dec.get("kill") or float(dec.get("trim_frac") or 0) > 0 or dec.get("watch")):
            continue
        actions.append(
            {
                "symbol": sym,
                "qty": q,
                "own_gap": gaps.get(sym),
                **dec,
            }
        )
    return actions
