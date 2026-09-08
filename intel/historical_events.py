"""Thin shared historical + upcoming event store for all pipelines.

Single entry point so fortress / day_trade / micro_scalp / HFT / paper_sim /
feature builders read the same calendar — no duplicate earnings sources.

Sources (existing, not replaced):
  - intel.earnings_calendar (Finnhub batch, Yahoo, disk cache)
  - universe_lifecycle.corporate_actions (renames / splits registry)
  - Optional realized move stats around past earnings dates
"""

from __future__ import annotations

import json
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from utils import log

ROOT = Path(__file__).resolve().parents[1]
RADAR_PATH = ROOT / "data" / "intel" / "earnings_radar.json"
EVENTS_CACHE = ROOT / "data" / "intel" / "historical_events_cache.json"
TIME_OVERRIDES = ROOT / "data" / "intel" / "earnings_time_overrides.json"

_MEM: dict[str, tuple[float, dict[str, Any]]] = {}


def _load_time_overrides() -> dict[str, Any]:
    """Operator / IR-confirmed print+call times (PT primary, ET mirrored)."""
    if not TIME_OVERRIDES.is_file():
        return {}
    try:
        doc = json.loads(TIME_OVERRIDES.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except Exception:
        return {}


def _apply_time_override(plan: dict[str, Any], symbol: str, *, as_of: date) -> dict[str, Any]:
    """Merge IR/Finnhub time evidence into a holdings plan row."""
    ov_root = _load_time_overrides()
    entries = ov_root.get("symbols") if isinstance(ov_root.get("symbols"), dict) else ov_root
    ov = entries.get(symbol.strip().upper()) if isinstance(entries, dict) else None
    if not isinstance(ov, dict):
        return plan
    ov_date = str(ov.get("date") or ov.get("as_of") or "")
    if ov_date and ov_date != as_of.isoformat():
        # Stale override — keep calendar date fields only
        plan["time_override_stale"] = ov_date
        return plan

    plan["report_session"] = ov.get("report_session") or ov.get("finnhub_hour")  # amc|bmo
    plan["call_time_pt"] = ov.get("call_time_pt")
    plan["call_time_et"] = ov.get("call_time_et")
    plan["results_release"] = ov.get("results_release")  # e.g. after_market_close
    plan["time_sources"] = list(ov.get("sources") or [])
    plan["time_note"] = ov.get("note")
    # Into the print: always dump-watch on event day when we have a clock time
    if plan.get("days_to") == 0 or (
        plan.get("next_date") and str(plan.get("next_date"))[:10] == as_of.isoformat()
    ):
        plan["fear_dump_watch"] = True
        plan["near_event"] = True
        plan["on_radar"] = True
        # Slightly tighter stop into the print when IR clock is known
        base = float(plan.get("stop_loss_pct") or 0.015)
        plan["stop_loss_pct"] = max(0.004, min(base, 0.006))
        plan["pre_print_behavior"] = (
            "tighten stops; dump-watch; optional trim if fear-sell starts — do not blind-flatten"
        )
        plan["post_print_behavior"] = (
            "watch gap/fade vs historical avg_abs_move; do not buy weakness blindly; "
            "trim/exit only if thesis abort / stop / fear-dump"
        )
        plan["plan"] = (
            f"{symbol.strip().upper()} print TODAY — results {plan.get('results_release') or plan.get('report_session')}; "
            f"call {plan.get('call_time_pt')} PT / {plan.get('call_time_et')} ET — "
            f"{plan['pre_print_behavior']}; after: {plan['post_print_behavior']}"
        )
    return plan


def _today(as_of: date | None = None) -> date:
    if as_of is not None:
        return as_of
    return datetime.now(timezone.utc).date()


def _ttl() -> float:
    return float(os.getenv("HISTORICAL_EVENTS_TTL_SEC", "1800"))


def earnings_event(symbol: str, *, as_of: date | None = None, force: bool = False) -> dict[str, Any]:
    """Unified earnings snapshot + light historical move context."""
    sym = symbol.strip().upper()
    today = _today(as_of)
    key = f"earn:{sym}:{today.isoformat()}"
    now = time.time()
    if not force:
        hit = _MEM.get(key)
        if hit and (now - hit[0]) < _ttl():
            return dict(hit[1])

    snap: dict[str, Any] = {
        "symbol": sym,
        "kind": "earnings",
        "as_of": today.isoformat(),
        "next_date": None,
        "prev_date": None,
        "days_to": None,
        "days_since": None,
        "in_window": False,
        "upcoming": [],
        "recent": [],
        "avg_abs_move_1d": None,
        "avg_abs_move_5d": None,
        "sources": [],
    }
    try:
        from intel.earnings_calendar import earnings_snapshot, load_all_earnings_dates

        es = earnings_snapshot(sym, as_of=today, force_refresh=force)
        snap["next_date"] = es.get("next_earnings_date")
        snap["prev_date"] = es.get("prev_earnings_date")
        snap["days_to"] = es.get("days_to_earnings")
        snap["days_since"] = es.get("days_since_earnings")
        snap["in_window"] = bool(es.get("in_earnings_window"))
        snap["upcoming"] = list(es.get("upcoming_dates") or [])
        snap["recent"] = list(es.get("recent_dates") or [])
        snap["estimated_next"] = bool(es.get("estimated_next"))
        snap["hour"] = es.get("hour")
        snap["session"] = es.get("session")
        snap["next_datetime_et"] = es.get("next_datetime_et")
        snap["next_datetime_pt"] = es.get("next_datetime_pt")
        snap["call_time_pt"] = es.get("call_time_pt")
        snap["call_time_et"] = es.get("call_time_et")
        if es.get("last_earnings_date"):
            snap["last_earnings_date"] = es.get("last_earnings_date")
            # Prefer override-backed days_since when Finnhub already rolled next quarter.
            try:
                from datetime import date as _date

                led = _date.fromisoformat(str(es["last_earnings_date"])[:10])
                if led < today:
                    override_since = (today - led).days
                    if snap.get("days_since") is None or override_since <= int(snap.get("days_since") or 10**9):
                        snap["days_since"] = override_since
                        snap["prev_date"] = led.isoformat()
            except Exception:
                pass
        if es.get("last_results_release"):
            snap["last_results_release"] = es.get("last_results_release")
        if es.get("last_call_time_pt"):
            snap["last_call_time_pt"] = es.get("last_call_time_pt")
        snap["call_datetime_pt"] = es.get("call_datetime_pt")
        snap["call_datetime_et"] = es.get("call_datetime_et")
        snap["results_release"] = es.get("results_release")
        snap["time_sources"] = list(es.get("time_sources") or [])
        snap["sources"].append("earnings_calendar")
        dates = load_all_earnings_dates(sym)
        moves = _avg_earnings_moves(sym, dates, as_of=today)
        snap.update(moves)
    except Exception as e:
        snap["error"] = str(e)[:120]
        log.debug("[EVENTS] earnings %s: %s", sym, e)

    _MEM[key] = (now, snap)
    return dict(snap)


def _avg_earnings_moves(
    symbol: str,
    dates: list[date],
    *,
    as_of: date,
    lookback: int = 8,
) -> dict[str, Any]:
    """Avg |1d| / |5d| moves around prior earnings when price history exists."""
    out: dict[str, Any] = {
        "avg_abs_move_1d": None,
        "avg_abs_move_5d": None,
        "n_prints_used": 0,
    }
    past = sorted((d for d in dates if d < as_of), reverse=True)[:lookback]
    if not past:
        return out
    try:
        import pandas as pd
        from multi_source_data import fetch_yahoo

        start = (past[-1] - timedelta(days=10)).isoformat()
        end = (as_of + timedelta(days=1)).isoformat()
        df = fetch_yahoo(symbol, start, end)
        if df is None or df.empty or "Close" not in df.columns:
            return out
        closes = df["Close"].astype(float)
        idx = pd.to_datetime(closes.index).normalize()
        closes.index = idx
        m1: list[float] = []
        m5: list[float] = []
        for ed in past:
            ed_ts = pd.Timestamp(ed)
            # locate nearest trading day on/after print
            after = closes[closes.index >= ed_ts]
            before = closes[closes.index < ed_ts]
            if after.empty or before.empty:
                continue
            px0 = float(before.iloc[-1])
            if px0 <= 0:
                continue
            px1 = float(after.iloc[0])
            m1.append(abs(px1 / px0 - 1.0))
            if len(after) >= 5:
                px5 = float(after.iloc[min(4, len(after) - 1)])
                m5.append(abs(px5 / px0 - 1.0))
        if m1:
            out["avg_abs_move_1d"] = float(sum(m1) / len(m1))
            out["n_prints_used"] = len(m1)
        if m5:
            out["avg_abs_move_5d"] = float(sum(m5) / len(m5))
        if m1:
            out["sources_extra"] = ["price_history"]
    except Exception as e:
        log.debug("[EVENTS] move stats %s: %s", symbol, e)
    return out


def corporate_events(symbol: str) -> list[dict[str, Any]]:
    """Rename / merge / split events touching this symbol from registry."""
    sym = symbol.strip().upper()
    out: list[dict[str, Any]] = []
    try:
        from universe_lifecycle.corporate_actions import load_registry

        reg = load_registry()
        for ev in reg.get("events") or []:
            old = str(ev.get("old") or "").upper()
            new = str(ev.get("new") or "").upper()
            if sym in (old, new):
                out.append(
                    {
                        "kind": str(ev.get("kind") or "corporate"),
                        "old": old,
                        "new": new,
                        "note": ev.get("note"),
                        "source": ev.get("source") or "corporate_actions",
                    }
                )
    except Exception as e:
        log.debug("[EVENTS] corporate %s: %s", sym, e)
    return out


def event_features(symbol: str, *, as_of: date | None = None) -> dict[str, float | int | None]:
    """Light feature dict for train / rank / fortress (same schema everywhere)."""
    snap = earnings_event(symbol, as_of=as_of)
    dte = snap.get("days_to")
    dse = snap.get("days_since")
    feats: dict[str, float | int | None] = {
        "days_to_earnings": int(dte) if dte is not None else None,
        "days_since_earnings": int(dse) if dse is not None else None,
        "in_earnings_window": 1 if snap.get("in_window") else 0,
        "earnings_avg_abs_move_1d": snap.get("avg_abs_move_1d"),
        "earnings_avg_abs_move_5d": snap.get("avg_abs_move_5d"),
        "earnings_n_prints": int(snap.get("n_prints_used") or 0),
    }
    try:
        from analytics.event_calendar import ticker_row

        cal = ticker_row(symbol)
        if cal:
            feats["event_calendar_pre"] = float(cal.get("pre") or 0.0)
            feats["event_live_binary"] = float(cal.get("live_binary") or 0.0)
            feats["event_effective_dte"] = cal.get("effective_dte")
            feats["event_guidance"] = float(cal.get("guidance") or 0.0)
    except Exception:
        pass
    try:
        from analytics.event_learn import predict_ticker

        el = predict_ticker(symbol, as_of=as_of)
        feats["event_learn_p_up"] = float(el.get("p_up") or 0.5)
        feats["event_learn_mag"] = float(el.get("mag") or 0.0)
        feats["event_learn_skill"] = float(el.get("skill") or 0.0)
        feats["event_learn_boost"] = float(el.get("boost") or 0.0)
    except Exception:
        pass
    try:
        from analytics.event_ingenuity import event_ingenuity_rank_boost, live_features

        ing = live_features(symbol, as_of=as_of, dte=int(dte) if dte is not None else None)
        feats["event_ingenuity_peer"] = float(ing.get("peer_gap_signed") or 0.0)
        feats["event_ingenuity_crowding"] = float(ing.get("crowding") or 0.0)
        boost, _meta = event_ingenuity_rank_boost(
            symbol,
            dte=int(dte) if dte is not None else None,
        )
        feats["event_ingenuity_boost"] = float(boost)
    except Exception:
        pass
    return feats


def holdings_earnings_plan(
    symbol: str,
    *,
    as_of: date | None = None,
    is_holding: bool = False,
    now_et: datetime | None = None,
) -> dict[str, Any]:
    """
    Overnight / fortress plan around earnings:
      - allow pre-earnings momentum awareness (do not force flatten)
      - tighten stops near print / post-print fear-dump window
    """
    snap = earnings_event(symbol, as_of=as_of)
    dte = snap.get("days_to")
    dse = snap.get("days_since")
    avg1 = float(snap.get("avg_abs_move_1d") or 0.0)
    avg5 = float(snap.get("avg_abs_move_5d") or 0.0)

    pre_buf = int(os.getenv("EARNINGS_PRE_HOLD_BUFFER_DAYS", "2"))
    post_buf = int(os.getenv("EARNINGS_POST_HOLD_BUFFER_DAYS", "3"))
    near = (dte is not None and 0 <= int(dte) <= pre_buf) or (
        dse is not None and 0 <= int(dse) <= post_buf
    )

    # Historical move → stop tighten multiplier (more history vol → tighter)
    base_sl = float(os.getenv("FORTRESS_STOP_LOSS_PCT", "0.015"))
    hist_vol = max(avg1, avg5 / 2.0) if (avg1 or avg5) else 0.0
    tighten = 1.0
    if near:
        tighten = float(os.getenv("EARNINGS_STOP_TIGHTEN_MULT", "0.55"))
        if hist_vol >= 0.04:
            tighten = min(tighten, 0.45)
        if hist_vol >= 0.07:
            tighten = min(tighten, 0.35)

    sl = max(0.004, base_sl * tighten) if near else base_sl
    trim_bias = 0.0
    if near and is_holding:
        trim_bias = float(os.getenv("EARNINGS_TRIM_BIAS", "0.35"))
        if dse is not None and 0 <= int(dse) <= 1:
            trim_bias = max(trim_bias, 0.55)

    # Day-of print (dte=0): still encourage if we are pre-call / session allows —
    # missing this is why SBUX was watched all day and never bought.
    hour = snap.get("hour") or snap.get("session")
    encourage = False
    if dte is not None:
        dte_i = int(dte)
        if 0 < dte_i <= pre_buf:
            encourage = True
        elif dte_i == 0 and os.getenv("EARNINGS_BUY_DAY_OF", "true").lower() in (
            "1",
            "true",
            "yes",
        ):
            encourage = True

    print_released = False
    try:
        from analytics.earnings_gap_guard import print_has_released

        print_released = print_has_released(hour, dte, dse, now_et=now_et)
    except Exception:
        print_released = False
    if print_released:
        # Print is out — STICK/FORCE add is over. Overnight hold stays; dump-watch starts.
        encourage = False

    post_print = bool(print_released) or (dse is not None and 0 <= int(dse) <= post_buf)
    fear_dump = bool(post_print or (dte is not None and int(dte) == 0))
    if encourage:
        plan_txt = (
            "pre/day-of earnings: STICK TO bullish model — FORCE prioritize buy when p_up high; "
            "tighter stops; dump-watch after print"
        )
    elif post_print:
        plan_txt = (
            "post-earnings window: NO force-buy — tighten stops / dump-watch only; "
            "model must stay bullish to hold"
        )
    elif near:
        plan_txt = "near earnings: tighter stops; no force-buy unless pre-window"
    else:
        plan_txt = "outside earnings window"

    plan = {
        "symbol": symbol.strip().upper(),
        "on_radar": near or (dte is not None and int(dte) <= 5),
        "near_event": near,
        "days_to": dte,
        "days_since": dse,
        "next_date": snap.get("next_date"),
        "allow_overnight_hold": True,  # never force flatten for earnings alone
        "encourage_pre_momentum": encourage,
        "stop_loss_pct": sl,
        "stop_tighten_mult": tighten if near else 1.0,
        "trim_bias": trim_bias if is_holding else 0.0,
        "fear_dump_watch": fear_dump,
        "avg_abs_move_1d": snap.get("avg_abs_move_1d"),
        "avg_abs_move_5d": snap.get("avg_abs_move_5d"),
        "hour": hour,
        "report_session": snap.get("session") or hour,
        "print_released": bool(print_released),
        "plan": plan_txt,
        # Only True in the pre/day-of buy window — was always True (boosted everyone, forced no one).
        "stick_to_prediction": bool(encourage),
    }
    return _apply_time_override(plan, symbol, as_of=_today(as_of))


def refresh_earnings_radar(symbols: list[str] | None = None) -> dict[str, Any]:
    """Write data/intel/earnings_radar.json for ops + talk evidence."""
    syms = [s.strip().upper() for s in (symbols or []) if s and str(s).strip()]
    if not syms:
        try:
            from alpaca_broker import list_positions

            syms = [
                str(p.get("symbol", "")).replace("/", "-").upper()
                for p in list_positions()
                if float(p.get("qty") or 0) > 0
            ]
        except Exception:
            syms = []
        # Always include SBUX on event days / when IR override exists
        if "SBUX" not in syms:
            syms.append("SBUX")

    today = _today()
    rows = []
    for s in sorted(set(syms)):
        # is_holding reflects live book; still flag watchlist names for radar evidence
        holding = False
        try:
            from alpaca_broker import get_position

            holding = get_position(s) is not None
        except Exception:
            holding = False
        plan = holdings_earnings_plan(s, as_of=today, is_holding=holding)
        snap = earnings_event(s, as_of=today)
        rows.append(
            {
                **plan,
                "is_holding": holding,
                "recent": snap.get("recent"),
                "upcoming": snap.get("upcoming"),
                "finnhub_hour": snap.get("hour") or plan.get("report_session"),
            }
        )

    doc = {
        "version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "as_of": today.isoformat(),
        "n": len(rows),
        "holdings": rows,
        "sbux_print_evidence": {
            "date": "2026-07-29",
            "results": "after_market_close (AMC)",
            "call_pt": "13:15",
            "call_et": "16:15",
            "finnhub_hour": "amc",
            "official_ir": "https://investor.starbucks.com/",
            "note": "User PT clock 1:15 PM matches IR call; Finnhub hour=amc = results AMC / call ~4:15 ET",
        },
    }
    try:
        RADAR_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = RADAR_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        os.replace(tmp, RADAR_PATH)
        log.info("[EVENTS] earnings radar → %s (%d names)", RADAR_PATH, len(rows))
        # Evidence line for ops / fortress logs
        for row in rows:
            if row.get("symbol") == "SBUX" and row.get("call_time_pt"):
                log.warning(
                    "[EVENTS] SBUX PRINT CLOCK confirmed call=%s PT / %s ET results=%s finnhub=%s holding=%s",
                    row.get("call_time_pt"),
                    row.get("call_time_et"),
                    row.get("results_release"),
                    row.get("report_session"),
                    row.get("is_holding"),
                )
    except Exception as e:
        log.warning("[EVENTS] radar write failed: %s", e)
    return doc


def symbol_event_bundle(symbol: str, *, as_of: date | None = None) -> dict[str, Any]:
    """Full bundle: earnings + corporate + features + hold plan."""
    sym = symbol.strip().upper()
    # (rest of function unchanged below — keep existing body)
    binary: dict[str, Any] = {}
    try:
        from analytics.event_calendar import ticker_row

        binary = ticker_row(sym)
    except Exception:
        binary = {}
    return {
        "symbol": sym,
        "earnings": earnings_event(sym, as_of=as_of),
        "corporate": corporate_events(sym),
        "features": event_features(sym, as_of=as_of),
        "hold_plan": holdings_earnings_plan(sym, as_of=as_of, is_holding=False),
        "binary_events": binary,
    }
