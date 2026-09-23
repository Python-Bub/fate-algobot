#!/usr/bin/env python3
"""Show what the real algorithm would trade per horizon — read-only mirror of paper_sim.

Uses today's paper_sim report only (no feature builds, no crowd re-adjustment).
Shows each horizon's own model-head % (raw spread, not compressed toward 50%).

Stdout only (--json). Never writes files.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

_DEFAULT_FAMILY_BLOCK = frozenset({"HACK"})  # broken/delisted ETF — never suggest to family

HEAD_LABEL = {
    "p_daily": "model_daily",
    "p_short": "model_short",
    "p_long": "model_long",
    "p_xlong": "model_xlong",
    "p_ultra": "fundamental_proxy",
    "model_bounce_blend": "bounce_recovery",
}


def _horizon_fields_for(edition: str | None) -> list[tuple[str, str, str, int]]:
    from analytics.family_horizons import horizon_fields

    return horizon_fields(edition=edition)


@dataclass
class Pick:
    ticker: str
    label: str
    title: str
    days: int
    chance_pct: int
    p_up: float
    signal: str
    head: str
    buy_et: str = "09:00"
    sell_et: str = "15:45"
    sell_rule: str = ""
    instructions: str = ""
    momentum_5d: float = 0.0
    rally_signal: float = 0.0
    rally_continuation: bool = False
    model_note: str = ""
    industry_primary: str = ""
    industry_note: str = ""
    industries: list[dict] | None = None
    conviction: float = 0.0
    rank: int = 1


def _signal(p_up: float, *, bullish: float, bearish: float) -> str:
    if p_up >= bullish:
        return "UP"
    if p_up <= bearish:
        return "DOWN"
    return "HOLD"


def _latest_paper_report() -> tuple[Path | None, dict | None]:
    from analytics.paper_report import latest_valid_report

    max_age = float(os.getenv("FAMILY_REPORT_MAX_AGE_HOURS", "72"))
    path, doc = latest_valid_report(min_rows=50, max_age_hours=max_age)
    if path and doc:
        return path, doc
    # Degraded overnight / first-open: accept older *or* partial fresh reports
    # (never invent picks). Morning paper-sim / fortress will refresh to full bar.
    soft = float(os.getenv("FAMILY_REPORT_SOFT_MAX_AGE_HOURS", "2400"))  # ~100d degraded
    soft_min = int(os.getenv("FAMILY_REPORT_SOFT_MIN_TRADEABLE", "50"))
    soft_top = int(os.getenv("FAMILY_REPORT_SOFT_MIN_TOP100", "40"))
    prev = os.environ.get("PAPER_REPORT_MIN_TRADEABLE")
    prev_top = os.environ.get("PAPER_REPORT_MIN_TOP100")
    try:
        os.environ["PAPER_REPORT_MIN_TRADEABLE"] = str(soft_min)
        os.environ["PAPER_REPORT_MIN_TOP100"] = str(soft_top)
        if soft > max_age:
            path, doc = latest_valid_report(min_rows=50, max_age_hours=soft)
            if path and doc:
                return path, doc
        # Prefer newest partial over ancient full report
        return latest_valid_report(min_rows=50, max_age_hours=soft, require_usable=False)
    finally:
        if prev is None:
            os.environ.pop("PAPER_REPORT_MIN_TRADEABLE", None)
        else:
            os.environ["PAPER_REPORT_MIN_TRADEABLE"] = prev
        if prev_top is None:
            os.environ.pop("PAPER_REPORT_MIN_TOP100", None)
        else:
            os.environ["PAPER_REPORT_MIN_TOP100"] = prev_top


def _try_offhours_refresh() -> bool:
    """Kick a non-blocking off-hours score refresh for tomorrow morning."""
    if os.getenv("FAMILY_AUTO_REFRESH", "true").lower() not in ("1", "true", "yes"):
        return False
    try:
        import subprocess

        log = ROOT / "logs" / "paper_sim_family_refresh.log"
        env = os.environ.copy()
        env["PAPER_SIM_ALLOW_OFFHOURS"] = "true"
        env["HOLD_DAYS_DEFAULT"] = env.get("HOLD_DAYS_DEFAULT", "1")
        env["PAPER_SIM_LITE_INTEL"] = "true"
        env["PAPER_SIM_WORKERS"] = env.get("PAPER_SIM_WORKERS", "2")
        subprocess.Popen(
            [str(ROOT / "venv" / "bin" / "python"), "-u", "paper_sim_today.py"],
            cwd=str(ROOT),
            env=env,
            stdout=log.open("a"),
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        return True
    except Exception:
        return False


def _report_age_hours(path: Path, doc: dict | None = None) -> float:
    from analytics.paper_report import report_age_hours_from_doc

    if doc:
        return report_age_hours_from_doc(doc, path)
    try:
        return (datetime.now(timezone.utc).timestamp() - path.stat().st_mtime) / 3600.0
    except OSError:
        return 9999.0


def _horizon_value(row: dict, prefix: str, *, hold_days: int | None = None) -> tuple[float, int]:
    """Raw model probability + display % — bounce names get horizon-aware blending."""
    from analytics.family_horizons import horizon_effective_probability, resolve_model_probability
    from analytics.probability_calibrate import display_chance_pct

    if hold_days is not None:
        raw, _head = horizon_effective_probability(row, prefix, hold_days=hold_days)
    else:
        raw, _head = resolve_model_probability(row, prefix)
    if raw is None:
        pct_key = f"{prefix}_chance_pct"
        if pct_key in row and row[pct_key] is not None:
            pct = int(row[pct_key])
            return pct / 100.0, pct
        legacy = {
            "p_short": "p_short_model",
            "p_long": "p_long_model",
            "p_daily": "p_daily_model",
            "p_xlong": "p_xlong_model",
        }
        leg = row.get(legacy.get(prefix))
        if leg is not None:
            raw_f = float(leg)
            return raw_f, display_chance_pct(raw_f)
        return 0.0, 0

    raw_f = float(raw)
    return raw_f, display_chance_pct(raw_f)


def _live_headwinds_enabled() -> bool:
    return os.getenv("FAMILY_LIVE_HEADWINDS", "false").lower() in ("1", "true", "yes")


def _unified_intel_enabled() -> bool:
    return os.getenv("FAMILY_UNIFIED_INTEL", "true").lower() in ("1", "true", "yes")


def _family_intel_blocks(ticker: str) -> tuple[bool, list[str]]:
    if not _unified_intel_enabled():
        return False, []
    try:
        from intel.unified_intel import blocks_long

        return blocks_long(ticker)
    except Exception:
        return False, []


def _live_risk_check_enabled() -> bool:
    return os.getenv("FAMILY_LIVE_RISK_CHECK", "false").lower() in ("1", "true", "yes")


def _family_blocklist() -> frozenset[str]:
    raw = os.getenv("FAMILY_BLOCK_SYMBOLS", "HACK").strip()
    extra = {s.strip().upper() for s in raw.split(",") if s.strip()}
    return _DEFAULT_FAMILY_BLOCK | extra


def _family_symbol_ok(ticker: str, row: dict, *, days: int) -> tuple[bool, str]:
    """Family picks: liquid tradeable names — no delisted, blocked, or risk-flagged."""
    t = str(ticker or "").upper().strip()
    if not t:
        return False, "empty"
    if t in _family_blocklist():
        return False, "blocked symbol"
    from fortress_universe import is_core_trainable_equity, is_top100_equity, is_tradeable_equity

    if not is_tradeable_equity(t) or not is_core_trainable_equity(t):
        return False, "not a tradeable stock"
    if os.getenv("FAMILY_TOP100_ONLY", "false").lower() in ("1", "true", "yes"):
        if not is_top100_equity(t):
            return False, "not top-100"
    try:
        from universe_lifecycle.corporate_actions import load_registry

        reg = load_registry()
        delisted = {
            str(x.get("symbol", "")).upper()
            for x in (reg.get("delisted") or [])
            if isinstance(x, dict)
        }
        if t in delisted:
            return False, "delisted"
        try:
            from universe_lifecycle.corporate_actions import is_dead_money

            if is_dead_money(t):
                return False, "dead money (cash takeout / listing ended)"
        except Exception:
            pass
    except Exception:
        pass
    if str(row.get("asym_action", "")).upper() == "SHORT":
        return False, "short signal"
    ar = row.get("algo_risk") or {}
    if ar and not bool(ar.get("approved", True)):
        return False, str(ar.get("reason") or "risk block")
    if row.get("skipped"):
        return False, "skipped in report"
    if _live_risk_check_enabled():
        try:
            from intel.algo_risk_filter import blocks_buy

            blocked, reason = blocks_buy(t, hold_days=days)
            if blocked:
                return False, reason or "live risk"
        except Exception:
            pass
    return True, ""


def _eligible_rows(rows: list[dict]) -> list[dict]:
    """Names from paper report — quality/active rotate pool by default (not top-100 only)."""
    from fortress_universe import is_core_trainable_equity, is_top100_equity, trade_quality_universe

    quality_only = os.getenv("FAMILY_QUALITY_UNIVERSE", "true").lower() in ("1", "true", "yes")
    quality = trade_quality_universe()
    min_px = float(os.getenv("FAMILY_MIN_SHARE_PRICE", os.getenv("FORTRESS_MIN_SHARE_PRICE", "5")))
    out: list[dict] = []
    for row in rows:
        if row.get("skipped"):
            continue
        t = str(row.get("ticker", "")).upper()
        if not t or not is_core_trainable_equity(t):
            continue
        if quality_only and t not in quality and not is_top100_equity(t):
            continue
        ok, _ = _family_symbol_ok(t, row, days=int(os.getenv("HOLD_DAYS_DEFAULT", "5")))
        if not ok:
            continue
        px = row.get("sig_close") or row.get("close") or row.get("price")
        if px is not None:
            try:
                if float(px) < min_px:
                    continue
            except (TypeError, ValueError):
                pass
        out.append(row)
    return out


def _picks_from_long_picks(
    saved: list[dict],
    *,
    bullish: float,
    bearish: float,
    rows_by_ticker: dict[str, dict] | None = None,
    horizon_fields: list[tuple[str, str, str, int]] | None = None,
) -> list[Pick]:
    """Build horizon view from algorithm long_picks (same names the stack would buy)."""
    fields = horizon_fields or _horizon_fields_for(None)
    macro_bundle = _prefetch_macro_bundle()
    if not saved:
        return []
    picks: list[Pick] = []
    for label, title, prefix, days in fields:
        best_row = None
        best_key: tuple | None = None
        for row in saved:
            pct_key = f"{prefix}_chance_pct"
            pct = row.get(pct_key)
            if pct is None:
                p = float(row.get("p_up", 0.5))
                pct = int(round(p * 100))
            else:
                p = float(pct) / 100.0
            if int(pct) < int(bullish * 100):
                continue
            t = str(row.get("ticker", "")).upper()
            full = (rows_by_ticker or {}).get(t) or row
            sym_ok, _ = _family_symbol_ok(t, full, days=days)
            if not sym_ok:
                continue
            if not _family_momentum_filter(full, days):
                continue
            if _live_headwinds_enabled():
                try:
                    from intel.near_term_headwinds import blocks_horizon_pick

                    if blocks_horizon_pick(t, label)[0]:
                        continue
                except Exception:
                    pass
            hw = full.get("near_term_headwinds") or full.get("headwinds") or {}
            if isinstance(hw, dict) and hw.get("block_playbook"):
                continue
            blocked, _ = _family_intel_blocks(t)
            if blocked:
                continue
            rk = _family_rank(full, prefix, days, macro_bundle=macro_bundle)
            key = (int(pct), rk)
            if best_key is None or key > best_key:
                best_key = key
                best_row = (full, p, int(pct))
        if not best_row:
            continue
        row, p, pct = best_row
        t = str(row.get("ticker", "")).upper()
        sig = _signal(p, bullish=bullish, bearish=bearish)
        if sig == "DOWN":
            continue
        pick = Pick(
            ticker=t,
            label=label,
            title=title,
            days=days,
            chance_pct=pct,
            p_up=p,
            signal=sig,
            head=HEAD_LABEL.get(prefix, prefix),
            model_note=_model_note(row, prefix, days),
        )
        picks.append(_attach_schedule(pick, row))
    return picks


def _picks_from_saved(saved: list[dict], *, bullish: float, bearish: float) -> list[Pick]:
    """Map saved long_picks rows to horizon display (daily head on top entry)."""
    if not saved:
        return []
    top = saved[0]
    t = str(top.get("ticker", "")).upper()
    p = float(top.get("p_up", 0.5))
    pct = int(top.get("chance_pct") or round(p * 100))
    return [
        Pick(
            ticker=t,
            label="one_day",
            title="1 day",
            days=1,
            chance_pct=pct,
            p_up=p,
            signal=_signal(p, bullish=bullish, bearish=bearish),
            head="algorithm_long_pick",
        )
    ]


def _attach_industry(pick: Pick) -> Pick:
    try:
        from analytics.industries.integration import family_industry_note, get_industry_profile

        prof = get_industry_profile(pick.ticker)
        note = family_industry_note(pick.ticker)
        return Pick(
            **{**pick.__dict__, "industry_primary": prof.get("primary_industry_id") or "", "industry_note": note, "industries": prof.get("industries")}
        )
    except Exception:
        return pick


def _attach_schedule(pick: Pick, row: dict | None = None) -> Pick:
    from analytics.family_horizon_schedule import schedule_dict, schedule_for_label

    sch = schedule_for_label(pick.label)
    if not sch:
        return pick
    sd = schedule_dict(sch)
    mom5 = float((row or {}).get("momentum_5d", 0))
    rally = float((row or {}).get("rally_signal", 0))
    return _attach_industry(
        Pick(
            ticker=pick.ticker,
            label=pick.label,
            title=pick.title,
            days=sch.hold_days,
            chance_pct=pick.chance_pct,
            p_up=pick.p_up,
            signal=pick.signal,
            head=pick.head,
            buy_et=sd["buy_et"],
            sell_et=sd["sell_et"],
            sell_rule=sd["sell_rule"],
            instructions=sd["instructions"],
            momentum_5d=mom5,
            rally_signal=rally,
            rally_continuation=bool((row or {}).get("rally_continuation", False)),
            model_note=pick.model_note,
            industry_primary=pick.industry_primary,
            industry_note=pick.industry_note,
            industries=pick.industries,
            conviction=float(pick.conviction or 0.0),
            rank=int(pick.rank or 1),
        )
    )


def _family_momentum_filter(row: dict, days: int) -> bool:
    try:
        from signals.dip_momentum import family_momentum_ok

        ok, _ = family_momentum_ok(row, days)
        return ok
    except Exception:
        return True


def _prefetch_macro_bundle() -> dict:
    try:
        from signals.fred_macro import get_macro_bundle

        return dict(get_macro_bundle() or {})
    except Exception:
        return {}


def _family_rank(row: dict, prefix: str, days: int, *, macro_bundle: dict | None = None) -> tuple:
    from analytics.family_horizons import (
        horizon_timeframe_fit,
        is_bounce_back_candidate,
        resolve_model_probability,
    )
    from fortress_universe import is_top100_equity

    p, pct = _horizon_value(row, prefix, hold_days=days)
    t = str(row.get("ticker", "")).upper()
    top = 1.0 if is_top100_equity(t) else 0.0
    if row.get("asym_action") == "LONG":
        thesis = 1.0
    elif is_bounce_back_candidate(row) and days >= 21:
        thesis = 0.9
    else:
        thesis = 0.0
    fit = horizon_timeframe_fit(row, hold_days=days)
    try:
        from signals.dip_momentum import family_momentum_rank_boost

        mom_boost = family_momentum_rank_boost(row, days)
    except Exception:
        mom_boost = float(row.get("momentum_5d", 0))
    _, head = resolve_model_probability(row, prefix)
    industry_boost = 0.0
    intel_adj = 0.0
    try:
        from analytics.industries.pipeline import family_rank_bias

        headlines = None
        ns = (row.get("news_ai") or {}).get("top_bullish") or []
        if ns:
            headlines = [str(h) for h in ns[:10]]
        industry_boost = family_rank_bias(
            t, row=row, news_headlines=headlines, macro_bundle=macro_bundle
        )
    except Exception:
        industry_boost = 0.0
    if _unified_intel_enabled():
        try:
            from intel.unified_intel import family_intel_adjustment

            intel_adj = family_intel_adjustment(t)
        except Exception:
            intel_adj = 0.0
    # Fit + displayed chance first — family picks are horizon-native, not paper asym gates.
    try:
        from analytics.horizon_picks import directional_conviction, horizon_independent

        conv = directional_conviction(p)
        if horizon_independent():
            base = (
                conv,
                float(pct) if p >= 0.5 else float(100 - pct),
                thesis,
                top,
                float(row.get("score", 0.0)) + industry_boost + intel_adj,
                mom_boost,
                head,
            )
        else:
            base = (
                fit,
                float(pct),
                thesis,
                top,
                float(row.get("score", 0.0)) + industry_boost + intel_adj,
                mom_boost,
                head,
            )
    except Exception:
        base = (
            fit,
            float(pct),
            thesis,
            top,
            float(row.get("score", 0.0)) + industry_boost + intel_adj,
            mom_boost,
            head,
        )
    try:
        from analytics.trade_rotation import diversify_rank_key, in_cooldown

        if os.getenv("FAMILY_RESPECT_COOLDOWN", "true").lower() in ("1", "true", "yes") and in_cooldown(t):
            return (-1.0, 0.0, 0.0, 0.0, 0.0)
        return diversify_rank_key(t, base)
    except Exception:
        return base


def _model_note(row: dict, prefix: str, hold_days: int) -> str:
    from analytics.family_horizons import horizon_effective_probability, is_bounce_back_candidate

    if prefix != "p_ultra":
        _, head = horizon_effective_probability(row, prefix, hold_days=hold_days)
        if head == "model_bounce_blend" or (
            is_bounce_back_candidate(row) and prefix == "p_long" and hold_days <= 21
        ):
            return "bounce recovery (xlong-weighted; not a 1-day/week trade)"
        if head and head not in (prefix, HEAD_LABEL.get(prefix, "")):
            return f"head={head}"
        return ""
    return "multi-year proxy (xlong + quality/fundamentals)"


def _best_from_report(
    rows: list[dict],
    *,
    bullish: float,
    bearish: float,
    horizon_fields: list[tuple[str, str, str, int]] | None = None,
    macro_bundle: dict | None = None,
) -> list[Pick]:
    fields = horizon_fields or _horizon_fields_for(None)
    macro_bundle = macro_bundle if macro_bundle is not None else _prefetch_macro_bundle()
    eligible = _eligible_rows(rows)
    if not eligible:
        eligible = [r for r in rows if not r.get("skipped")]

    require_long = os.getenv("FAMILY_REQUIRE_ASYM_LONG", "false").lower() in ("1", "true", "yes")
    min_score = float(os.getenv("FAMILY_MIN_SCORE", "0"))

    def _pool_for_horizon(prefix: str, days: int) -> list[dict]:
        from analytics.family_horizons import short_horizon_blocked

        try:
            from analytics.horizon_picks import horizon_independent

            independent = horizon_independent()
        except Exception:
            independent = False
        out: list[dict] = []
        for row in eligible:
            if short_horizon_blocked(row, hold_days=days):
                continue
            p, pct = _horizon_value(row, prefix, hold_days=days)
            if pct <= 0:
                continue
            if independent:
                if not (p >= bullish or p <= bearish):
                    continue
            elif p < bullish:
                continue
            if require_long and row.get("asym_action") != "LONG":
                continue
            if min_score > 0 and float(row.get("score", 0.0)) < min_score:
                continue
            out.append(row)
        if not out:
            for row in eligible:
                if short_horizon_blocked(row, hold_days=days):
                    continue
                p, pct = _horizon_value(row, prefix, hold_days=days)
                if pct <= 0:
                    continue
                if independent:
                    if not (p >= bullish or p <= bearish):
                        continue
                elif p < bullish:
                    continue
                if row.get("asym_action") == "SHORT":
                    continue
                if min_score > 0 and float(row.get("score", 0.0)) < min_score * 0.85:
                    continue
                out.append(row)
        return out

    try:
        from analytics.horizon_picks import directional_conviction, horizon_independent, horizon_top_k

        independent = horizon_independent()
        top_n = horizon_top_k(int(os.getenv("FAMILY_TOP_K", os.getenv("HORIZON_TOP_K", "3")) or 3))
    except Exception:
        independent = False
        top_n = 1
        directional_conviction = lambda p: abs(float(p) - 0.5) * 2.0  # noqa: E731

    picked: list[Pick] = []
    for label, title, prefix, days in fields:
        pool = _pool_for_horizon(prefix, days)
        scored: list[tuple] = []
        for row in pool:
            p, pct = _horizon_value(row, prefix, hold_days=days)
            t = str(row.get("ticker", "")).upper()
            if not t:
                continue
            sig = _signal(p, bullish=bullish, bearish=bearish)
            if independent:
                if sig == "HOLD":
                    continue
            elif p < bullish or sig == "DOWN":
                continue
            sym_ok, _ = _family_symbol_ok(t, row, days=days)
            if not sym_ok:
                continue
            if not _family_momentum_filter(row, days):
                continue
            if _live_headwinds_enabled():
                try:
                    from intel.near_term_headwinds import blocks_horizon_pick

                    if blocks_horizon_pick(t, label)[0]:
                        continue
                except Exception:
                    pass
            hw = row.get("near_term_headwinds") or row.get("headwinds") or {}
            if isinstance(hw, dict) and hw.get("block_playbook"):
                continue
            blocked, _ = _family_intel_blocks(t)
            # Long-block must not hide an independent DOWN call on another horizon.
            if blocked and not (independent and sig == "DOWN"):
                continue
            rk = _family_rank(row, prefix, days, macro_bundle=macro_bundle)
            conv = directional_conviction(p)
            scored.append((conv, rk, row, p, pct, t, sig))
        scored.sort(key=lambda item: (-float(item[0]), item[1]))
        seen: set[str] = set()
        rank_i = 0
        from analytics.family_horizons import horizon_effective_probability

        for conv, rk, row, p, pct, t, sig in scored:
            if t in seen:
                continue
            seen.add(t)
            rank_i += 1
            _, eff_head = horizon_effective_probability(row, prefix, hold_days=days)
            head_key = eff_head if eff_head in HEAD_LABEL else prefix
            pick = Pick(
                ticker=t,
                label=label,
                title=title,
                days=days,
                chance_pct=pct,
                p_up=p,
                signal=sig,
                head=HEAD_LABEL.get(head_key, HEAD_LABEL.get(prefix, prefix)),
                model_note=_model_note(row, prefix, days),
                conviction=float(conv),
                rank=rank_i,
            )
            picked.append(_attach_schedule(pick, row))
            if rank_i >= top_n:
                break
    return picked


def _hold_label(days: int) -> str:
    if days <= 1:
        return "same day"
    if days <= 5:
        return f"{days} trading days (~1 week)"
    if days <= 21:
        return f"~{days} trading days (~1 month)"
    if days <= 126:
        return f"~{days} trading days (~6 months)"
    if days <= 252:
        return f"~{days} trading days (~1 year)"
    if days <= 1260:
        return "~5 years (investment horizon)"
    return "~10 years (investment horizon)"


def _print_picks(
    picks: list[Pick],
    meta: str,
    report: dict,
    *,
    horizon_fields: list[tuple[str, str, str, int]] | None = None,
) -> None:
    from analytics.family_horizon_schedule import _fmt_et

    bb = report.get("market_bull_bear") or {}
    mkt = str(bb.get("bull_bear_label") or report.get("regime") or "?").upper()
    vix = bb.get("vix", report.get("vix"))

    fields = horizon_fields or _horizon_fields_for(None)

    print()
    print("=" * 52)
    print("  FAMILY FORECAST")
    print("  Buy ~9:00 AM ET   |   Sell ~3:45 PM ET (end of hold)")
    print("=" * 52)
    print(f"  Report: {meta}")
    print(f"  Market: {mkt}" + (f"   VIX {float(vix):.1f}" if vix is not None else ""))
    print("-" * 52)

    from collections import defaultdict

    by_label: dict[str, list[Pick]] = defaultdict(list)
    for p in picks:
        by_label[p.label].append(p)
    for label, title, _, _days in fields:
        group = by_label.get(label) or []
        if not group:
            print()
            print(f"  {title.upper()}")
            print("    (no pick — nothing in report at >=55% conviction for this horizon)")
            continue
        print()
        print(f"  {title.upper()}  (top {len(group)} by this timeframe's confidence)")
        for p in group:
            buy_d = _fmt_et(p.buy_et) if p.buy_et else "9:00 AM ET"
            sell_d = _fmt_et(p.sell_et) if p.sell_et else "3:45 PM ET"
            hold = _hold_label(p.days)
            mom = f"5d {p.momentum_5d * 100:+.1f}%"
            if p.rally_continuation and p.momentum_5d > 0:
                mom += "  (trend up)"
            side = "up" if p.signal == "UP" else ("down" if p.signal == "DOWN" else "hold")
            chance = p.chance_pct if p.signal != "DOWN" else max(0, 100 - int(p.chance_pct))
            print(f"    #{p.rank} {p.ticker}  {chance}% {side}  conv={p.conviction:.2f}")
            print(f"       When     Buy {buy_d}  ->  Sell {sell_d}  ({hold})")
            print(f"       Momentum {mom}")
            if p.model_note:
                print(f"       Model    {p.model_note}")
            if p.industry_note:
                print(f"       Sector   {p.industry_note}")
    print()
    print("-" * 52)
    print("  Not financial advice.")
    print("=" * 52)


def main() -> int:
    ap = argparse.ArgumentParser(description="Mirror algorithm horizon picks from paper_sim report")
    ap.add_argument("--bullish", type=float, default=float(os.getenv("FAMILY_BULLISH_P", "0.55")))
    ap.add_argument("--bearish", type=float, default=float(os.getenv("FAMILY_BEARISH_P", "0.45")))
    ap.add_argument("--json", action="store_true")
    ap.add_argument(
        "--edition",
        type=str,
        default="",
        help="Show one horizon only: one_day, one_week, one_month, six_months, one_year, five_years, ten_years",
    )
    ap.add_argument("--fresh", action="store_true", help="Ignored — always uses latest report")
    args = ap.parse_args()

    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))

    edition = args.edition.strip() or None
    try:
        fields = _horizon_fields_for(edition)
    except ValueError as e:
        print(f"[family-forecast] {e}")
        return 1

    report_path, report = _latest_paper_report()
    if not report or not report_path:
        kicked = _try_offhours_refresh()
        msg = "[family-forecast] No paper_sim report in reports/ — run paper trading first."
        if kicked:
            msg += " Started off-hours refresh (PAPER_SIM_ALLOW_OFFHOURS); retry in a few minutes."
        print(msg)
        return 1

    max_age = float(os.getenv("FAMILY_REPORT_MAX_AGE_HOURS", "72"))
    age_h = _report_age_hours(report_path, report)
    stale_warn = age_h > max_age

    rows = list(report.get("rows") or [])
    rows_by_ticker = {str(r.get("ticker", "")).upper(): r for r in rows if r.get("ticker")}
    eligible_n = len(_eligible_rows(rows))
    from analytics.paper_report import report_quality_metrics

    q = report_quality_metrics(report)
    macro_bundle = _prefetch_macro_bundle()
    # Per-horizon picks from scored rows (not raw long_picks — avoids junk like delisted HACK).
    picks = _best_from_report(
        rows,
        bullish=args.bullish,
        bearish=args.bearish,
        horizon_fields=fields,
        macro_bundle=macro_bundle,
    )
    saved = report.get("long_picks") or []
    if len(picks) < len(fields):
        extra = _picks_from_long_picks(
            saved,
            bullish=args.bullish,
            bearish=args.bearish,
            rows_by_ticker=rows_by_ticker,
            horizon_fields=fields,
        )
        have = {p.label for p in picks}
        picks.extend(p for p in extra if p.label not in have)
    if not picks and saved:
        picks = _picks_from_saved(saved, bullish=args.bullish, bearish=args.bearish)
    gen = str(report.get("generated_at_utc", ""))[:19]
    meta = f"{report_path.name} @ {gen}Z"

    if not args.json:
        print("[family-forecast] Paper-active quality universe (not limited to top-100).")
        print(f"  Eligible names in report: {eligible_n}")
        print(f"  Report pool: {q.get('tradeable')} scored, {q.get('top100')} top-100")
        print(f"  UP >= {args.bullish:.0%}   |   DOWN <= {args.bearish:.0%}")
        if stale_warn:
            print(
                f"  ⚠ Report is {age_h:.0f}h old (>{max_age:.0f}h). "
                f"Refresh: ./run_all.sh paper-sim"
            )
        elif age_h > 12:
            print(f"  Report age: {age_h:.1f}h")

    if not picks:
        from analytics.paper_report import latest_valid_report

        alt_path, alt = latest_valid_report(min_rows=1)
        if alt and alt_path and alt_path != report_path:
            rows = list(alt.get("rows") or [])
            saved = alt.get("long_picks") or []
            picks = _best_from_report(
                rows,
                bullish=args.bullish,
                bearish=args.bearish,
                horizon_fields=fields,
                macro_bundle=macro_bundle,
            )
            if len(picks) < len(fields):
                extra = _picks_from_long_picks(
                    saved,
                    bullish=args.bullish,
                    bearish=args.bearish,
                    rows_by_ticker={str(r.get("ticker", "")).upper(): r for r in rows if r.get("ticker")},
                    horizon_fields=fields,
                )
                have = {p.label for p in picks}
                picks.extend(p for p in extra if p.label not in have)
            if picks:
                meta = f"{alt_path.name} @ {str(alt.get('generated_at_utc',''))[:19]}Z (fallback)"
                eligible_n = len(_eligible_rows(rows))
                if not args.json:
                    print(f"[family-forecast] Using fallback report {alt_path.name} (latest was empty).")
    if not picks:
        print("\n[family-forecast] No horizon picks in report (run paper sim after code update).")
        return 1

    if args.json:
        print(
            json.dumps(
                {
                    "as_of": datetime.now(timezone.utc).isoformat(),
                    "report": report_path.name,
                    "report_age_hours": round(age_h, 2),
                    "report_quality": q,
                    "stale": stale_warn,
                    "market_bull_bear": report.get("market_bull_bear"),
                    "best_per_horizon": [asdict(p) for p in picks],
                    "industry_ai_enabled": os.getenv("USE_INDUSTRY_AI", "true").lower() in ("1", "true", "yes"),
                },
                indent=2,
            )
        )
        return 0

    _print_picks(picks, meta, report, horizon_fields=fields)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
