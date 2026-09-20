#!/usr/bin/env python3
"""
Fortress live loop: heartbeat, kill-switch, regime, XGB prob gate, sentiment block,
volume confirm, MTF align, equity sparkline, optional broker execution (Alpaca or IBKR).
"""

from __future__ import annotations

import argparse
import os
import time

from dotenv import load_dotenv

load_dotenv()
# deploy_scale.env last-wins over .env (order pace, deploy, overnight caps).
_deploy = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "deploy_scale.env")
if os.path.isfile(_deploy):
    load_dotenv(_deploy, override=True)

from data_platform.market_prices import configure_process_prices

configure_process_prices()

from config import IBKR_HOST, IBKR_PORT
from equity_terminal_chart import print_equity_panel
from feature_engineering import build_features
from heartbeat_monitor import start_heartbeat_daemon, is_reduced_risk
from kill_switch import is_halted, register_equity_snapshot
from ml_model import predict_row_details, predict_row_horizon
from multi_source_data import cross_verify_close
from multi_timeframe import mtf_buy_ok
from regime_detector import simple_regime_from_spy
from risk_manager import OpenLeg, RiskManager
from sentiment_pipeline import block_long_on_sentiment, composite_sentiment
from feature_store import volume_confirmed
from trade_journal import log_trade
from fortress_universe import load_fortress_scan_list


def _call_with_timeout(fn, timeout_sec: float, *args, **kwargs):
    """Best-effort timeout for hung Yahoo/Polygon/Finnhub I/O.

    Critical: must shutdown(wait=False). A `with ThreadPoolExecutor` block calls
    shutdown(wait=True) on exit — after TimeoutError that blocks forever on the
    stuck worker (Finnhub 'no route to host'), freezing the whole fortress pass.
    """
    if timeout_sec <= 0:
        return fn(*args, **kwargs)
    from concurrent.futures import ThreadPoolExecutor
    from concurrent.futures import TimeoutError as FuturesTimeout

    pool = ThreadPoolExecutor(max_workers=1)
    try:
        fut = pool.submit(fn, *args, **kwargs)
        try:
            return fut.result(timeout=timeout_sec)
        except FuturesTimeout as e:
            fut.cancel()
            raise TimeoutError(
                f"{getattr(fn, '__name__', 'call')} exceeded {timeout_sec:.0f}s"
            ) from e
    finally:
        try:
            pool.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            # py<3.9 cancel_futures
            pool.shutdown(wait=False)


def _load_playbook_tickers() -> list[str]:
    path = os.getenv("MONDAY_PLAYBOOK_PATH", "data/monday_playbook.json")
    if not os.path.isfile(path):
        return []
    try:
        import json
        from pathlib import Path

        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        out: list[str] = []
        for p in doc.get("preorders") or []:
            t = str(p.get("ticker") or "").upper()
            if t and t not in out:
                out.append(t)
        return out
    except Exception:
        return []
from fortress_portfolio import (
    can_add_position,
    close_all_short_positions,
    fortress_order_notional,
    position_snapshot,
    sync_risk_manager_from_alpaca,
)
from utils import log
from runtime.latency_monitor import LatencyMonitor
from runtime.signal_bus import SignalBus
from self_modify.policy_agent import GuardedPolicyAgent, get_runtime_param
from multi_algo_fusion import fused_decision
from compliance_guard import pretrade_check

import pandas as pd


def _spy_df() -> pd.DataFrame:
    from data_platform.market_prices import fetch_period

    spy = fetch_period("SPY", period="1y", interval="1d")
    if spy is None or spy.empty:
        return pd.DataFrame()
    if isinstance(spy.columns, pd.MultiIndex):
        spy.columns = [c[0] if isinstance(c, tuple) else c for c in spy.columns]
    return spy


def _fortress_lite_intel() -> bool:
    return os.getenv("FORTRESS_LITE_INTEL", "false").lower() in ("1", "true", "yes")


def _intel_news_factors(ticker: str) -> tuple[float, float]:
    nf_f, tf_f = 0.0, 0.0
    # Lite still uses fast lexicon news (1d/5d must see headlines). Skip slow transcripts/LLM.
    try:
        from intel.news_factor_engine import score_symbol_news_factors

        nf_f = float(score_symbol_news_factors(ticker).get("final_factor", 0.0))
    except Exception:
        pass
    if _fortress_lite_intel():
        return nf_f, 0.0
    if os.getenv("USE_INTEL_FACTORS", "true").lower() not in ("1", "true", "yes"):
        return nf_f, tf_f
    try:
        from intel.transcript_factor_engine import score_symbol_transcripts

        tf_f = float(score_symbol_transcripts(ticker).get("final_factor", 0.0))
    except Exception:
        pass
    return nf_f, tf_f


def _fortress_blend_sentiment(ticker: str) -> tuple[float, dict]:
    """Composite sentiment + social/Cramer overlay. Lite skips slow news_ai/Polygon."""
    intel: dict = {}
    sent = 0.0
    lite = _fortress_lite_intel()
    # Lite: skip news_ai/LLM (90s+/ticker). Social/Cramer overlay still runs below.
    if not lite:
        try:
            from sentiment_pipeline import composite_sentiment

            sent = float(composite_sentiment(ticker))
        except Exception:
            sent = 0.0
        try:
            from sentiment_pipeline import get_symbol_news_intel

            intel = get_symbol_news_intel(ticker)
        except Exception:
            intel = {}
        if os.getenv("USE_INTEL_FACTORS", "true").lower() in ("1", "true", "yes"):
            try:
                from intel.news_factor_engine import score_symbol_news_factors
                from intel.transcript_factor_engine import score_symbol_transcripts

                nf = score_symbol_news_factors(ticker)
                tf = score_symbol_transcripts(ticker)
                nf_f = float(nf.get("final_factor", 0.0))
                tf_f = float(tf.get("final_factor", 0.0))
                intel_mix = 0.65 * nf_f + 0.35 * tf_f
                if os.getenv("HEAVY_NEWS_INTEL", "false").lower() in ("1", "true", "yes"):
                    w_news = float(os.getenv("FORTRESS_NEWS_WEIGHT", "0.55"))
                    sent = (1.0 - w_news) * sent + w_news * intel_mix
                else:
                    sent = 0.55 * sent + 0.30 * nf_f + 0.15 * tf_f
            except Exception:
                pass
    if lite:
        # 1d news still counts — lexicon headlines, not 90s news_ai.
        try:
            from intel.news_factor_engine import score_symbol_news_factors

            sent = float(score_symbol_news_factors(ticker).get("final_factor", 0.0))
        except Exception:
            sent = 0.0
    cramer_b = 0.0
    social_b = 0.0
    club_b = 0.0
    power_b = 0.0
    mem_b = 0.0
    try:
        from intel.cramer_picks import cramer_boost_for
        from intel.morning_club_intel import morning_club_block_long, morning_club_boost_for
        from intel.social_sentiment import social_boost_for

        cramer_b = float(cramer_boost_for(ticker))
        social_b = float(social_boost_for(ticker))
        club_b = float(morning_club_boost_for(ticker))
        if morning_club_block_long(ticker):
            club_b = min(club_b, -0.35)
    except Exception:
        pass
    try:
        from intel.power_people import power_people_boost_for

        power_b = float(power_people_boost_for(ticker))
    except Exception:
        pass
    try:
        from intel.algo_memory import memory_boost_for

        mem_b = float(memory_boost_for(ticker))
    except Exception:
        pass
    w_c = float(os.getenv("FORTRESS_CRAMER_BLEND", "0.12"))
    w_s = float(os.getenv("FORTRESS_SOCIAL_BLEND", "0.08"))
    w_club = float(os.getenv("FORTRESS_MORNING_CLUB_BLEND", "0.95"))
    w_p = float(os.getenv("FORTRESS_POWER_PEOPLE_BLEND", "0.08"))
    w_m = float(os.getenv("FORTRESS_ALGO_MEMORY_BLEND", "0.04"))
    inst_b = 0.0
    web_b = 0.0
    w_i = 0.0
    w_w = 0.0
    if not lite:
        try:
            from intel.institutional_flow_signals import institutional_flow_factor

            inst_b = float(institutional_flow_factor(ticker))
        except Exception:
            pass
        w_i = float(os.getenv("FORTRESS_INSTITUTIONAL_BLEND", "0.35"))
        try:
            from intel.open_web_intel import open_web_boost_for

            web_b = float(open_web_boost_for(ticker))
        except Exception:
            pass
        w_w = float(os.getenv("FORTRESS_OPEN_WEB_BLEND", "0.30"))
    blended = max(-1.0, min(1.0, sent + w_c * cramer_b + w_s * social_b + w_i * inst_b + w_club * club_b + w_w * web_b + w_p * power_b + w_m * mem_b))
    try:
        from intel.morning_club_intel import load_latest, morning_club_block_long

        if morning_club_block_long(ticker):
            blended = min(blended, -0.15)
        doc = load_latest()
        info = (doc.get("tickers") or {}).get(ticker.upper()) or {}
        if info.get("good_news_score", 0) > 0.55:
            blended = min(1.0, blended + 0.06 * float(info["good_news_score"]))
        if info.get("bad_news_score", 0) > 0.55:
            blended = max(-1.0, blended - 0.08 * float(info["bad_news_score"]))
    except Exception:
        pass
    if intel.get("boost_long") and intel.get("good_news_score", 0) > 0.5:
        blended = min(1.0, blended + float(os.getenv("FORTRESS_AI_GOOD_NEWS_BOOST", "0.08")))
    elif intel.get("block_long") or intel.get("narrative") == "bad_news":
        blended = max(-1.0, blended - float(os.getenv("FORTRESS_AI_BAD_NEWS_PENALTY", "0.12")))
    return blended, intel


def _accuracy_mode() -> bool:
    return os.getenv("FORTRESS_ACCURACY_MODE", "true").lower() in ("1", "true", "yes")


def _news_supports_buy(nf_f: float, sent: float) -> bool:
    min_news = float(os.getenv("FORTRESS_MIN_NEWS_FACTOR", "0.02"))
    min_sent = float(os.getenv("FORTRESS_MIN_SENT", "0.04"))
    if _accuracy_mode():
        return nf_f >= min_news and sent >= min_sent
    return nf_f >= min_news or sent >= min_sent


def _accuracy_buy_extra(
    *,
    pred: int,
    p_adj: float,
    nf_f: float,
    sent: float,
    vol_ok: bool,
    mtf_ok: bool,
    daily_bull: bool,
) -> bool:
    """Stricter conjunctive gates when FORTRESS_ACCURACY_MODE=true."""
    if not _accuracy_mode():
        return True
    if _gates_relaxed():
        return True
    if pred != 1:
        return False
    if not vol_ok:
        return False
    if not daily_bull:
        return False
    if not mtf_ok:
        return False
    if nf_f < float(os.getenv("FORTRESS_ACCURACY_MIN_NEWS", "0.04")):
        return False
    if sent < float(os.getenv("FORTRESS_ACCURACY_MIN_SENT", "0.05")):
        return False
    return True


def _p_up_adjusted(p_up: float, nf_f: float) -> float:
    """nf_f is sentiment intensity [-1,1]. Apply as log-odds evidence, not extra P(up)."""
    from intel.metric_semantics import sentiment_rank_impulse
    from analytics.vector_math import apply_logit_tilt, delta_p_to_delta_ell

    cap = float(os.getenv("FORTRESS_NEWS_MAX_P_IMPULSE", "0.015"))
    scale = float(os.getenv("FORTRESS_NEWS_P_IMPULSE_SCALE", "0.02"))
    impulse = sentiment_rank_impulse(float(nf_f), scale=scale, cap=cap)
    return apply_logit_tilt(float(p_up), delta_p_to_delta_ell(float(p_up), impulse))


def _buy_confidence_score(
    *,
    p_adj: float,
    exec_c: float,
    sent: float,
    nf_f: float,
    top100: bool,
    hf_boost: float = 0.0,
    ticker: str | None = None,
    row=None,
    mom_5d: float = 0.0,
    rs_spy: float = 1.0,
    hmm_market_score: float = 0.0,
    closes=None,
    bench_closes=None,
) -> float:
    """Ranking score — delegates to unified rank pipeline when enabled."""
    try:
        from analytics.rank_pipeline import fortress_buy_score, use_unified_rank

        if use_unified_rank():
            return fortress_buy_score(
                p_adj=p_adj,
                exec_c=exec_c,
                sent=sent,
                nf_f=nf_f,
                top100=top100,
                hf_boost=hf_boost,
                ticker=ticker,
                row=row,
                mom_5d=mom_5d,
                rs_spy=rs_spy,
                hmm_market_score=hmm_market_score,
                closes=closes,
                bench_closes=bench_closes,
            )
    except Exception:
        pass
    edge = max(0.0, float(p_adj) - 0.5) * 2.0
    rank_w = float(os.getenv("FORTRESS_NEWS_RANK_W", "0.12"))
    sent_imp = max(-0.10, min(0.10, float(sent) * 0.08))
    news_imp = max(-0.10, min(0.10, float(nf_f) * 0.10))
    w_edge = float(os.getenv("FORTRESS_W_EDGE", "0.75"))
    w_exec = float(os.getenv("FORTRESS_W_EXEC", "0.27"))
    w_sent = float(os.getenv("FORTRESS_W_SENT", "0.10"))
    score = w_edge * edge + w_exec * float(exec_c) + w_sent * sent_imp + rank_w * news_imp
    score += float(os.getenv("RANK_W_HEDGE_FUND", "1.0")) * float(hf_boost)
    if top100:
        score += float(os.getenv("FORTRESS_TOP100_RANK_BONUS", "0.03"))
    return float(score)


def _share_price_ok(price: float) -> bool:
    """Optional band for share price (e.g. only cheaper names)."""
    if price <= 0:
        return False
    mx = os.getenv("FORTRESS_MAX_SHARE_PRICE", "").strip()
    mn = os.getenv("FORTRESS_MIN_SHARE_PRICE", "").strip()
    if mx:
        if price > float(mx):
            return False
    if mn:
        if price < float(mn):
            return False
    return True


def _position_unrealized_gain(pos: dict, price: float) -> float | None:
    """Refuse garbage cost basis (Alpaca has reported entry<0 and 175%+ 'gains')."""
    entry = float(pos.get("avg_entry_price") or 0)
    if entry <= 0:
        return None
    px = float(price or 0)
    from_px = ((px - entry) / entry) if px > 0 else None
    uplpc = pos.get("unrealized_plpc")
    if uplpc is None:
        return from_px
    try:
        g = float(uplpc)
    except (TypeError, ValueError):
        return from_px
    # Phantom 100%+ TPs on flipped shorts / bad avg cost — prefer price/entry, else skip.
    if abs(g) > 0.50:
        if from_px is not None and abs(from_px) <= 0.50:
            return from_px
        if from_px is not None and abs(from_px) + 1e-9 < abs(g):
            return from_px
        return None
    return g


def _position_age_minutes(ticker: str) -> float | None:
    """Minutes since position opened (Alpaca fill time preferred; constraints as fallback)."""
    sym = ticker.strip().upper()
    # 1) Prefer most recent filled BUY for this symbol (authoritative).
    try:
        from alpaca_broker import get_position
        import os
        import requests
        from datetime import datetime, timezone

        pos = get_position(sym)
        if pos and float(pos.get("qty") or 0) != 0:
            key = os.getenv("ALPACA_API_KEY")
            sec = os.getenv("ALPACA_SECRET_KEY") or os.getenv("ALPACA_API_SECRET")
            base = (os.getenv("ALPACA_BASE_URL") or "https://paper-api.alpaca.markets").rstrip("/")
            if key and sec:
                r = requests.get(
                    f"{base}/v2/orders",
                    headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec},
                    params={
                        "status": "closed",
                        "symbols": sym,
                        "side": "buy",
                        "limit": 5,
                        "direction": "desc",
                    },
                    timeout=12,
                )
                if r.ok:
                    for o in r.json() or []:
                        if str(o.get("status")) != "filled":
                            continue
                        ts = o.get("filled_at") or o.get("submitted_at") or o.get("created_at")
                        if not ts:
                            continue
                        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 60.0)
            # Open position but no fill history — protect as fresh.
            return 0.0
    except Exception:
        pass
    # 2) Local constraints — ignore stale opened_at that predates a clear re-entry.
    try:
        from intel.trade_constraints import get_constraints
        from datetime import datetime, timezone

        meta = get_constraints(sym) or {}
        opened = meta.get("opened_at_utc") or meta.get("saved_at_utc")
        if opened:
            dt = datetime.fromisoformat(str(opened).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            age = max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 60.0)
            # Stale constraint files (weeks/months old) must not force EXIT_TIMEOUT on new fills.
            timeout_min = float(os.getenv("FORTRESS_EXIT_TIMEOUT_MIN", os.getenv("EXIT_TIMEOUT_MIN", "4320")) or 4320)
            if timeout_min > 0 and age >= timeout_min:
                return 0.0
            return age
    except Exception:
        pass
    return None


def _min_hold_minutes() -> float:
    return float(os.getenv("FORTRESS_MIN_HOLD_MINUTES", "0"))


def _respect_min_hold(ticker: str, *, allow_stop: bool = False) -> bool:
    """True when exits/signal-sells are allowed for this holding."""
    mins = _min_hold_minutes()
    if mins <= 0:
        return True
    age = _position_age_minutes(ticker)
    if age is None:
        return True
    if age >= mins:
        return True
    return allow_stop and age >= mins * 0.25


def _sell_session_ok() -> tuple[bool, str]:
    """Avoid overnight thrash of canceled Alpaca sells (AAPL spam)."""
    try:
        from analytics.market_session import orders_allowed

        return orders_allowed("sell")
    except Exception:
        return True, "session_check_skipped"


def _maybe_exit_alpaca(
    ticker: str,
    price: float,
    *,
    use_real: bool,
    broker: str,
    rm: RiskManager,
    p_adj: float | None = None,
    pred: int | None = None,
    signal_want_sell: bool = False,
    better_candidate_waiting: bool = False,
) -> bool:
    """Take-profit / stop-loss / sympathy-trap time exit on open Alpaca long."""
    if not use_real or broker != "alpaca":
        return False
    _p_adj = 0.55 if p_adj is None else float(p_adj)
    try:
        from intel.trade_constraints import should_force_exit, take_profit_pct_for

        force, force_reason = should_force_exit(ticker)
        ignore_sym = os.getenv("FORTRESS_IGNORE_SYMPATHY_RISK", "false").lower() in ("1", "true", "yes")
        if force and ignore_sym and (
            "sympathy" in force_reason.lower() or "earnings" in force_reason.lower()
        ):
            force = False
        if force and not _respect_min_hold(ticker, allow_stop=True):
            force = False
        if force:
            from alpaca_broker import close_position_alpaca, get_position

            pos = get_position(ticker)
            if pos and float(pos.get("qty") or 0) > 0:
                log.warning("[FORTRESS] SYMPATHY_EXIT %s — %s", ticker, force_reason)
                if close_position_alpaca(ticker):
                    rm.legs.pop(ticker, None)
                    rm.legs.pop(ticker.upper(), None)
                    return True
    except Exception as e:
        log.debug("[FORTRESS] sympathy exit check %s: %s", ticker, e)

    default_tp = take_profit_pct_for(ticker, float(os.getenv("FORTRESS_TAKE_PROFIT_PCT", "0.015")))
    try:
        from analytics.profit_cushion_gate import fortress_take_profit_pct

        tp = fortress_take_profit_pct(ticker, default_tp)
    except Exception:
        tp = default_tp
    sl = float(os.getenv("FORTRESS_STOP_LOSS_PCT", "0.025"))
    base_sl = sl
    # Earnings-aware + downward-pressure stop tighten (overnight hold stays ON)
    try:
        from intel.historical_events import holdings_earnings_plan

        _eplan = holdings_earnings_plan(ticker, is_holding=True)
        if _eplan.get("near_event") and _eplan.get("stop_loss_pct"):
            sl = min(sl, float(_eplan["stop_loss_pct"]))
            if _eplan.get("on_radar"):
                log.info(
                    "[FORTRESS] earnings radar %s next=%s dte=%s stop→%.3f%% — %s",
                    ticker,
                    _eplan.get("next_date"),
                    _eplan.get("days_to"),
                    100 * sl,
                    _eplan.get("plan"),
                )
    except Exception:
        pass
    try:
        from intel.downward_pressure import exit_adjustments

        _adj = exit_adjustments(ticker)
        if float(_adj.get("tighten_exit") or 0) > 0:
            # Keep the thesis stop. Pressure already blocks new buys/add-ons.
            # Shrinking SL to ~1.7% dumped TSLA/AAPL-class holds on noise.
            log.info(
                "[FORTRESS] downward-pressure hold %s score=%.2f — no add; stop stays %.3f%%",
                ticker,
                float(_adj.get("pressure_score") or 0),
                100 * sl,
            )
    except Exception:
        pass
    # Floor ultra-tight stops — 0.75% radar cuts caused QCOM cancel/reissue thrash.
    floor = float(os.getenv("FORTRESS_STOP_TIGHTEN_FLOOR_FRAC", "0.55")) * base_sl
    if sl < floor:
        sl = floor
    try:
        from alpaca_broker import close_position_alpaca, get_position

        pos = get_position(ticker)
        if not pos:
            return False
        if float(pos.get("qty") or 0) <= 0:
            return False
        gain = _position_unrealized_gain(pos, price)
        if gain is None:
            return False
        if not _respect_min_hold(ticker, allow_stop=gain <= -sl * 1.5):
            return False
        # Stagnant / time-stop: flatten when held too long with near-zero P&L.
        # Overnight path: skip (or use multi-day timeout) so core/swing book survives close.
        allow_overnight = os.getenv("FORTRESS_ALLOW_OVERNIGHT", "true").lower() in (
            "1",
            "true",
            "yes",
        )
        flatten_at_close = os.getenv("FLATTEN_AT_CLOSE", "false").lower() in (
            "1",
            "true",
            "yes",
        )
        timeout_min = float(os.getenv("FORTRESS_EXIT_TIMEOUT_MIN", "0") or 0)
        if timeout_min <= 0:
            timeout_min = float(os.getenv("EXIT_TIMEOUT_MIN", "0") or 0)
        if allow_overnight and not flatten_at_close:
            # Multi-day stagnant floor when overnight is intentional (was 75m → wiped book).
            overnight_floor = float(os.getenv("FORTRESS_OVERNIGHT_EXIT_TIMEOUT_MIN", "4320") or 4320)
            if timeout_min <= 0 or timeout_min < overnight_floor:
                timeout_min = overnight_floor
        stagnant_band = float(os.getenv("FORTRESS_STAGNANT_ABS_PCT", "0.004"))
        if timeout_min > 0 and abs(float(gain)) <= stagnant_band:
            age = _position_age_minutes(ticker)
            if age is not None and age >= timeout_min and _respect_min_hold(ticker, allow_stop=True):
                log.info(
                    "[FORTRESS] EXIT_TIMEOUT %s age=%.0fm gain=%.3f%% (band ±%.3f%%) — closing stagnant",
                    ticker,
                    age,
                    100 * float(gain),
                    100 * stagnant_band,
                )
                ok_sell, why_sell = _sell_session_ok()
                if not ok_sell:
                    log.info("[FORTRESS] EXIT_TIMEOUT defer %s — %s", ticker, why_sell)
                    return False
                if close_position_alpaca(ticker):
                    rm.legs.pop(ticker, None)
                    rm.legs.pop(ticker.upper(), None)
                    return True
        # Conviction exit engine: thesis death vs noise, TP, scale-out/rotate
        try:
            from analytics.conviction_exit import decide_exit, update_trade_quality

            age_m = _position_age_minutes(ticker)
            bars_proxy = None if age_m is None else max(1.0, float(age_m) / 5.0)
            _sess_gap = None
            try:
                from analytics.earnings_gap_guard import session_gap_from_pos

                _sess_gap = session_gap_from_pos(pos)
            except Exception:
                _sess_gap = None
            decision = decide_exit(
                ticker,
                p_adj=_p_adj,
                gain=float(gain),
                take_profit_pct=float(tp),
                stop_loss_pct=float(sl),
                pred=pred,
                better_candidate_waiting=better_candidate_waiting,
                signal_want_sell=signal_want_sell,
                bars_held=bars_proxy,
                session_gap=_sess_gap,
            )
            update_trade_quality(
                ticker,
                p_adj=_p_adj,
                gain=float(gain),
                action=decision.action,
                reason=decision.reason,
            )
            if decision.action in ("hold", "noise_hold"):
                if decision.action == "noise_hold":
                    log.info("[FORTRESS] NOISE_HOLD %s — %s", ticker, decision.reason)
                return False
            ok_sell, why_sell = _sell_session_ok()
            if not ok_sell:
                log.info(
                    "[FORTRESS] EXIT defer %s action=%s gain=%.3f%% — session %s",
                    ticker,
                    decision.action,
                    100 * float(gain),
                    why_sell,
                )
                return False
            if decision.action == "scale_out":
                pos_qty = abs(float(pos.get("qty") or 0))
                trim_qty = max(1, int(pos_qty * float(decision.trim_frac)))
                if trim_qty >= pos_qty:
                    trim_qty = max(1, int(pos_qty) - 1) if pos_qty >= 2 else int(pos_qty)
                log.info(
                    "[FORTRESS] SCALE_OUT %s trim=%s/%s — %s",
                    ticker,
                    trim_qty,
                    int(pos_qty),
                    decision.reason,
                )
                if close_position_alpaca(ticker, force=True, qty=float(trim_qty), head="fortress"):
                    return True
                return False
            log.info(
                "[FORTRESS] EXIT %s action=%s gain=%.3f%% — %s",
                ticker,
                decision.action,
                100 * float(gain),
                decision.reason,
            )
        except Exception as e:
            log.debug("[FORTRESS] conviction exit %s: %s", ticker, e)
            if gain >= tp:
                log.info(
                    "[FORTRESS] TAKE-PROFIT %s gain=%.3f%% (target %.3f%%) — closing",
                    ticker,
                    100 * gain,
                    100 * tp,
                )
            elif gain <= -sl:
                log.info(
                    "[FORTRESS] STOP-LOSS %s gain=%.3f%% (cut %.3f%%) — closing",
                    ticker,
                    100 * gain,
                    100 * sl,
                )
            else:
                return False
            ok_sell, why_sell = _sell_session_ok()
            if not ok_sell:
                log.info("[FORTRESS] EXIT defer %s — %s", ticker, why_sell)
                return False
        # force=True: marketable exit — wide paper NBBOs must not pin TP at phantom asks
        if close_position_alpaca(ticker, force=True):
            rm.legs.pop(ticker, None)
            rm.legs.pop(ticker.upper(), None)
            try:
                from analytics.jp_candle_rl import record_outcome

                record_outcome(ticker, float(gain))
            except Exception:
                pass
            try:
                from online_learning.trade_feedback import learn_from_realized_trade

                learn_from_realized_trade(
                    ticker,
                    "LONG",
                    float(gain),
                    source="fortress_exit",
                )
            except Exception:
                pass
            return True
    except Exception as e:
        log.debug("[FORTRESS] exit check %s: %s", ticker, e)
    return False


def _apply_earnings_gap_guard() -> list[str]:
    """First-tick print dump/size guard — does not wait for the 92-name crawl.

    WMT 2026-08-20 sat −9% through RTH because thesis-death ran after the
    feature/intel loop. Kill/trim here, before radar + scan list assembly.
    Does not flatten the book — only print-gap kills and pre-print excess.
    """
    watch: list[str] = []
    if os.getenv("EARNINGS_GAP_GUARD", "true").lower() not in ("1", "true", "yes", "on"):
        return watch
    try:
        from alpaca_broker import close_position_alpaca, get_account, list_positions
        from analytics.earnings_gap_guard import decide, session_gap_from_pos
        from intel.historical_events import holdings_earnings_plan
    except Exception as e:
        log.debug("[FORTRESS] earnings gap guard import: %s", e)
        return watch
    try:
        acct = get_account() or {}
        equity = float(acct.get("equity") or acct.get("last_equity") or 0)
        positions = list_positions() or []
    except Exception as e:
        log.warning("[FORTRESS] earnings gap guard snapshot: %s", e)
        return watch
    for p in positions:
        try:
            qty = float(p.get("qty") or 0)
        except (TypeError, ValueError):
            continue
        if qty <= 0:
            continue
        sym = str(p.get("symbol", "")).replace("/", "-").upper()
        if not sym:
            continue
        try:
            plan = holdings_earnings_plan(sym, is_holding=True)
        except Exception:
            plan = {}
        gap = session_gap_from_pos(p)
        mv = abs(float(p.get("market_value") or 0))
        try:
            gain = float(p.get("unrealized_plpc")) if p.get("unrealized_plpc") is not None else None
        except (TypeError, ValueError):
            gain = None
        dec = decide(
            dte=plan.get("days_to"),
            dse=plan.get("days_since"),
            hour=plan.get("hour") or plan.get("report_session"),
            gap=gap,
            gain_vs_entry=gain,
            mv=mv,
            equity=equity,
            fear_dump=bool(plan.get("fear_dump_watch")),
        )
        if dec.watch:
            watch.append(sym)
        if dec.kill:
            log.warning(
                "[FORTRESS] EARNINGS_GAP_KILL %s gap=%.2f%% vs_entry=%.2f%% dte=%s hour=%s — %s",
                sym,
                100 * float(gap or 0),
                100 * float(gain or 0),
                plan.get("days_to"),
                plan.get("hour") or plan.get("report_session"),
                dec.reason,
            )
            try:
                if close_position_alpaca(sym, force=True):
                    log.warning("[FORTRESS] EARNINGS_GAP_KILL submitted %s", sym)
            except Exception as e:
                log.warning("[FORTRESS] EARNINGS_GAP_KILL %s failed: %s", sym, e)
        elif dec.trim_frac > 0:
            sell_qty = qty * float(dec.trim_frac)
            if sell_qty < 1e-4:
                continue
            log.warning(
                "[FORTRESS] EARNINGS_PRE_TRIM %s sell=%.4f/%.4f frac=%.2f mv=$%.0f — %s",
                sym,
                sell_qty,
                qty,
                dec.trim_frac,
                mv,
                dec.reason,
            )
            try:
                close_position_alpaca(sym, force=True, qty=sell_qty)
            except Exception as e:
                log.warning("[FORTRESS] EARNINGS_PRE_TRIM %s failed: %s", sym, e)
    # Peer-print cascade (WMT −9% → COST) — same first tick, before the crawl.
    try:
        from analytics.earnings_gap_guard import session_gap_from_pos
        from analytics.event_ingenuity import contagion_for_book, save_book_gaps

        gaps: dict[str, float] = {}
        for p in positions:
            try:
                q = float(p.get("qty") or 0)
            except (TypeError, ValueError):
                continue
            if q <= 0:
                continue
            s = str(p.get("symbol", "")).replace("/", "-").upper()
            if not s:
                continue
            g = session_gap_from_pos(p)
            if g is not None:
                gaps[s] = float(g)
        save_book_gaps(gaps)
        for act in contagion_for_book(positions):
            s = str(act.get("symbol") or "")
            if act.get("watch") and s and s not in watch:
                watch.append(s)
            if act.get("kill"):
                log.warning(
                    "[FORTRESS] PEER_CASCADE_KILL %s own=%.2f%% peer=%.2f%% — %s",
                    s,
                    100 * float(act.get("own_gap") or 0),
                    100 * float(act.get("worst_peer") or 0),
                    act.get("reason"),
                )
                try:
                    if close_position_alpaca(s, force=True):
                        log.warning("[FORTRESS] PEER_CASCADE_KILL submitted %s", s)
                except Exception as e:
                    log.warning("[FORTRESS] PEER_CASCADE_KILL %s failed: %s", s, e)
            elif float(act.get("trim_frac") or 0) > 0:
                q = float(act.get("qty") or 0)
                sell_qty = q * float(act["trim_frac"])
                if sell_qty < 1e-4:
                    continue
                log.warning(
                    "[FORTRESS] PEER_CASCADE_TRIM %s sell=%.4f/%.4f frac=%.2f — %s",
                    s,
                    sell_qty,
                    q,
                    act["trim_frac"],
                    act.get("reason"),
                )
                try:
                    close_position_alpaca(s, force=True, qty=sell_qty)
                except Exception as e:
                    log.warning("[FORTRESS] PEER_CASCADE_TRIM %s failed: %s", s, e)
    except Exception as e:
        log.debug("[FORTRESS] peer cascade: %s", e)
    return watch


def _scan_alpaca_exits(*, use_real: bool, broker: str, rm: RiskManager) -> None:
    """Exit all open paper positions: stop/TP, losers, and weak held names."""
    if not use_real or broker != "alpaca":
        return
    try:
        from alpaca_broker import list_positions
        from alt_assets import is_tradeable_instrument

        for pos in list_positions():
            sym = str(pos.get("symbol", "")).replace("/", "-").upper()
            if not sym or not is_tradeable_instrument(sym):
                continue
            if os.getenv("FORTRESS_CRYPTO_SESSION_ONLY", "false").lower() in (
                "1",
                "true",
                "yes",
            ):
                try:
                    from crypto_universe import is_crypto_symbol

                    if not is_crypto_symbol(sym):
                        continue
                except Exception:
                    continue
            px = float(pos.get("current_price") or pos.get("avg_entry_price") or 0)
            if px > 0:
                try:
                    from alpaca_broker import reprice_working_sells

                    reprice_working_sells(sym)
                except Exception:
                    pass
                _maybe_exit_alpaca(sym, px, use_real=use_real, broker=broker, rm=rm)
        try:
            from alpaca_broker import cancel_stale_unfillable_buys

            n_buy = cancel_stale_unfillable_buys()
            if n_buy:
                log.info("[FORTRESS] cancelled %d stale/unfillable buy(s)", n_buy)
        except Exception:
            pass
        # Only run hygiene liquidates when aggressive — overnight holds must not be
        # wiped by a soft loser cut that always ran regardless of the flag.
        if os.getenv("PAPER_HYGIENE_AGGRESSIVE", "false").lower() in ("1", "true", "yes"):
            from fortress_portfolio import liquidate_losing_positions

            n = liquidate_losing_positions()
            if n:
                log.warning("[FORTRESS] hygiene cut %d losing position(s)", n)
    except Exception as e:
        log.debug("[FORTRESS] position exit scan: %s", e)


def _gates_relaxed() -> bool:
    return os.getenv("FORTRESS_RELAX_GATES", "false").lower() in ("1", "true", "yes")


def _sell_threshold() -> float:
    return float(os.getenv("FORTRESS_SELL_MAX_P", "0.52"))


def _alpaca_sell_qty(ticker: str, fallback_qty: int) -> int:
    try:
        from alpaca_broker import get_position

        pos = get_position(ticker)
        if pos:
            q = float(pos.get("qty") or 0)
            if q > 0:
                return max(1, int(q))
    except Exception:
        pass
    return max(1, fallback_qty)


def run_fortress_pass(args) -> None:
    try:
        from analytics.sleeve_weights import apply_sleeve_env

        applied = apply_sleeve_env("fortress")
        from utils import log as _log

        _log.info("[FORTRESS] sleeve=fortress weights_locked keys=%s", sorted(applied)[:8])
    except Exception:
        pass

    if os.getenv("FORTRESS_HEARTBEAT", "true").lower() in ("1", "true", "yes"):
        start_heartbeat_daemon()

    from analytics.market_session import (
        Session,
        current_session,
        exchange_is_open,
        orders_allowed,
        session_summary,
    )

    broker = os.getenv("BROKER", "alpaca").strip().lower()
    use_real = os.getenv("USE_REAL_MONEY", "false").lower() in ("1", "true", "yes")

    sess = session_summary()
    buy_ok, _ = orders_allowed("buy")
    exit_ok, _ = orders_allowed("sell")
    crypto_buy_ok = False
    try:
        crypto_buy_ok, _ = orders_allowed("buy", symbol="BTC/USD")
    except Exception:
        crypto_buy_ok = False
    eq_open, eq_why = False, "unknown"
    try:
        eq_open, eq_why = exchange_is_open(for_hft=False)
    except Exception:
        eq_open, eq_why = False, "clock_error"
    us_closed = (not eq_open) or current_session() == Session.CLOSED
    # overnight_cash_deploy can make buy_ok true on Saturday; still scan coins only.
    if crypto_buy_ok and us_closed:
        os.environ["FORTRESS_CRYPTO_SESSION_ONLY"] = "true"
        # FinBERT+Chronos OOM'd the 16GB paper box and killed the scan (exit 137).
        # Weekend leftover fill still uses XGB + idle-cash into held crypto.
        os.environ["FORTRESS_LITE_INTEL"] = "true"
        os.environ["FORTRESS_PASS_MAX_SEC"] = os.getenv("FORTRESS_CRYPTO_PASS_MAX_SEC", "240")
        buy_ok = True
        log.info(
            "[FORTRESS] US equity closed (%s) — crypto 24/7 buys, lite intel",
            eq_why,
        )
    else:
        os.environ["FORTRESS_CRYPTO_SESSION_ONLY"] = "false"
    try:
        from analytics.live_rank_sign import invert_p_up_enabled

        _inv = invert_p_up_enabled()
        log.info(
            "[FORTRESS] live-rank invert_new_buys=%s (exits use raw p_adj) buy_ok=%s exit_ok=%s",
            _inv,
            buy_ok,
            exit_ok,
        )
    except Exception:
        pass
    held_count = 0
    _gap_watch: list[str] = []
    if use_real and broker == "alpaca":
        try:
            from alpaca_broker import list_positions

            held_count = sum(1 for p in list_positions() if float(p.get("qty") or 0) > 0)
        except Exception:
            pass
        # Before earnings radar / 92-name crawl — WMT sat through RTH waiting on intel.
        if held_count > 0:
            try:
                _gap_watch = _apply_earnings_gap_guard()
                if _gap_watch:
                    log.info(
                        "[FORTRESS] earnings gap-watch first: %s",
                        ",".join(_gap_watch[:16]),
                    )
            except Exception as e:
                log.warning("[FORTRESS] earnings gap guard: %s", e)

    allow_overnight = os.getenv("FORTRESS_ALLOW_OVERNIGHT", "true").lower() in ("1", "true", "yes")
    flatten_at_close = os.getenv("FLATTEN_AT_CLOSE", "false").lower() in ("1", "true", "yes")
    if os.getenv("USE_UNIQUE_PLAYBOOK", "true").lower() in ("1", "true", "yes"):
        try:
            from intel.unique_style_playbook import apply_playbook_env_defaults, load_playbook

            applied_env = apply_playbook_env_defaults()
            pb = load_playbook()
            if pb.get("name"):
                log.info("[FORTRESS] unique playbook=%s env_defaults=%s", pb.get("name"), applied_env or "none")
            allow_overnight = os.getenv("FORTRESS_ALLOW_OVERNIGHT", "true").lower() in ("1", "true", "yes")
            flatten_at_close = os.getenv("FLATTEN_AT_CLOSE", "false").lower() in ("1", "true", "yes")
        except Exception as e:
            log.debug("[FORTRESS] unique playbook: %s", e)
    if allow_overnight and not flatten_at_close:
        log.info(
            "[FORTRESS] overnight hold ON (FORTRESS_ALLOW_OVERNIGHT=true FLATTEN_AT_CLOSE=false) — "
            "core book survives close; TP/SL/risk kills still active"
        )
    try:
        from intel.historical_events import refresh_earnings_radar

        radar = refresh_earnings_radar(None)
        for row in radar.get("holdings") or []:
            if row.get("on_radar"):
                log.info(
                    "[FORTRESS][EVENTS] radar %s next=%s dte=%s near=%s stop=%.3f%%",
                    row.get("symbol"),
                    row.get("next_date"),
                    row.get("days_to"),
                    row.get("near_event"),
                    100 * float(row.get("stop_loss_pct") or 0),
                )
    except Exception as e:
        log.debug("[FORTRESS] earnings radar: %s", e)
    try:
        from analytics.custom_stock_groups import coverage_report

        cov = coverage_report(None)
        log.info(
            "[FORTRESS] custom groups meaningful=%s/%s (%.1f%%)",
            cov.get("meaningful"),
            cov.get("n"),
            float(cov.get("meaningful_pct") or 0),
        )
    except Exception as e:
        log.debug("[FORTRESS] custom groups: %s", e)

    exit_only = (not buy_ok) and (exit_ok or held_count > 0)
    intel_prep = False
    try:
        from analytics.market_session import intel_window_open

        intel_prep = intel_window_open()[0] and not buy_ok and not exit_ok
    except Exception:
        pass

    if not buy_ok and not exit_ok and held_count == 0 and not intel_prep:
        log.info(
            "[FORTRESS] session=%s — idle until %s (mode=%s start=%s)",
            sess.get("session"),
            sess.get("next_open_et", "?"),
            sess.get("trade_session_mode"),
            sess.get("trade_start_et") or os.getenv("FORTRESS_TRADE_START_ET", "09:00"),
        )
        # Stay alive through closed sessions so daemon_loop does not thrash every 30s.
        try:
            from datetime import datetime
            from zoneinfo import ZoneInfo

            nxt_s = sess.get("next_open_et")
            sleep_s = float(os.getenv("FORTRESS_CLOSED_SLEEP_SEC", "600"))
            if nxt_s:
                nxt = datetime.fromisoformat(str(nxt_s))
                now = datetime.now(ZoneInfo("America/New_York"))
                if nxt.tzinfo is None:
                    nxt = nxt.replace(tzinfo=ZoneInfo("America/New_York"))
                delta = (nxt - now).total_seconds()
                if delta > 0:
                    # Cap so we still refresh env/intel periodically.
                    cap = float(os.getenv("FORTRESS_CLOSED_SLEEP_CAP_SEC", "900"))
                    sleep_s = max(60.0, min(delta, cap))
            log.info("[FORTRESS] closed-session sleep %.0fs", sleep_s)
            time.sleep(sleep_s)
        except Exception:
            time.sleep(float(os.getenv("FORTRESS_CLOSED_SLEEP_SEC", "600")))
        return

    if exit_only and not exit_ok and held_count > 0:
        log.info(
            "[FORTRESS] session=%s — exit-only for %d holding(s) (closes queue until %s)",
            sess.get("session"),
            held_count,
            sess.get("next_open_et", "?"),
        )
    elif intel_prep:
        log.info(
            "[FORTRESS] session=%s — 6 AM intel prep (news/LLM warm; buys wait until %s ET)",
            sess.get("session"),
            sess.get("trade_start_et") or os.getenv("FORTRESS_TRADE_START_ET", "09:00"),
        )
    elif not buy_ok and exit_ok:
        log.info(
            "[FORTRESS] buys blocked (%s) — exit scan only until %s ET",
            sess.get("buy_reason"),
            sess.get("trade_start_et") or "?",
        )
    ib = None
    if use_real and broker == "ibkr":
        from ibkr_executor import connect_ib

        ib = connect_ib()

    min_p = float(
        get_runtime_param(
            "MIN_MODEL_CONFIDENCE",
            float(os.getenv("MIN_MODEL_CONFIDENCE", os.getenv("BUY_THRESHOLD", "0.62"))),
        )
    )
    scan_cap = int(args.max_symbols)
    # One Alpaca snapshot for scan-cap + later recap (extra GETs were 429ing the fill path).
    _book_dep: float | None = None
    _book_pos: list = []
    # Underdeployed books: shrink scan so we reach buy execution before PASS_MAX_SEC.
    if use_real and broker == "alpaca":
        try:
            from alpaca_broker import get_account, list_positions

            _acct = get_account() or {}
            _eq = float(_acct.get("equity") or 0)
            _book_pos = list_positions() or []
            _mv = sum(abs(float(p.get("market_value") or 0)) for p in _book_pos)
            from analytics.underdeploy_scan import deploy_frac_from_snapshot

            dep = deploy_frac_from_snapshot(_eq, _mv)
            _book_dep = dep
            under = float(os.getenv("FORTRESS_UNDERDEPLOY_FRAC", "0.55"))
            if dep < under and os.getenv("FORTRESS_SCAN_WHOLE_DB", "false").lower() not in (
                "1",
                "true",
                "yes",
            ):
                # Keep ≥100 so top100 stays in the loaded list; recap cuts the pass.
                small = max(100, int(os.getenv("FORTRESS_UNDERDEPLOY_MAX_SYMBOLS", "48")))
                if small < scan_cap:
                    log.info(
                        "[FORTRESS] underdeployed %.0f%% — scan cap %d → %d for faster buys",
                        100 * dep,
                        scan_cap,
                        small,
                    )
                    scan_cap = small
        except Exception:
            pass
    _sh: list[str] = []
    playbook: list[str] = []
    _extra: list[str] = []
    _force_env: list[str] = []
    syms = load_fortress_scan_list(scan_cap, shuffle_rest=args.shuffle)
    if os.getenv("FORTRESS_CRYPTO_SESSION_ONLY", "false").lower() in ("1", "true", "yes"):
        try:
            from analytics.crypto_alloc import overnight_crypto_scan

            syms = overnight_crypto_scan()
            log.info("[FORTRESS] crypto-session scan %d symbol(s)", len(syms))
        except Exception:
            pass
    _crypto_session = os.getenv("FORTRESS_CRYPTO_SESSION_ONLY", "false").lower() in (
        "1",
        "true",
        "yes",
    )
    try:
        from analytics.sheldon_head import sheldon_priority_tickers

        _sh = sheldon_priority_tickers()
        if _sh and not _crypto_session:
            syms = list(dict.fromkeys(_sh + list(syms)))
            log.info("[FORTRESS] sheldon head force-scan %d ticker(s)", len(_sh))
    except Exception:
        pass
    playbook = _load_playbook_tickers()
    if playbook and not _crypto_session:
        syms = list(dict.fromkeys(playbook + list(syms)))
        log.info("[FORTRESS] monday playbook: %d preorder ticker(s) prioritized", len(playbook))
    # Earnings radar: STICK TO prediction — force-scan names we flagged (e.g. SBUX day-of).
    try:
        from intel.historical_events import refresh_earnings_radar

        radar = refresh_earnings_radar(None)
        earn_pri: list[str] = []
        for row in radar.get("holdings") or []:
            sym = str(row.get("symbol") or "").upper()
            if not sym:
                continue
            if row.get("encourage_pre_momentum") or row.get("stick_to_prediction"):
                earn_pri.append(sym)
        if earn_pri:
            syms = list(dict.fromkeys(earn_pri + list(syms)))
            log.info(
                "[FORTRESS] earnings STICK priority: %s",
                ",".join(earn_pri[:20]),
            )
    except Exception as e:
        log.debug("[FORTRESS] earnings priority: %s", e)
    # Explicit FORCE symbols (high-conviction UP watch — e.g. BX when predicted up).
    _force_env = [
        x.strip().upper()
        for x in os.getenv("FORTRESS_FORCE_BUY_SYMBOLS", "").split(",")
        if x.strip()
    ]
    if _force_env:
        syms = list(dict.fromkeys(_force_env + list(syms)))
        log.info("[FORTRESS] FORCE BUY scan priority: %s", ",".join(_force_env[:20]))
    try:
        from pathlib import Path as _P

        _use_watch = os.getenv("FORTRESS_USE_FORCE_WATCH", "false").lower() in (
            "1",
            "true",
            "yes",
        )
        _fw = _P("data/ops/force_buy_watch.json")
        if _use_watch and _fw.is_file():
            import json as _json

            _doc = _json.loads(_fw.read_text(encoding="utf-8"))
            _extra = [
                str(s).strip().upper()
                for s in (_doc.get("symbols") or _doc.get("force") or [])
                if str(s).strip()
            ]
            if _extra:
                syms = list(dict.fromkeys(_extra + list(syms)))
                log.info("[FORTRESS] force_buy_watch: %s", ",".join(_extra[:20]))
    except Exception as e:
        log.debug("[FORTRESS] force_buy_watch: %s", e)
    try:
        from analytics.water_theme import enabled as _water_on, water_scan_symbols

        if _water_on() and not _crypto_session:
            _water = water_scan_symbols()
            if _water:
                syms = list(dict.fromkeys(_water + list(syms)))
                log.info("[FORTRESS] water theme first: %s", ",".join(_water[:16]))
    except Exception as e:
        log.debug("[FORTRESS] water theme: %s", e)
    # Always scan open holdings so stop/TP/signal-sell runs every pass (not only hash-rotated names).
    if use_real and broker == "alpaca":
        try:
            from alpaca_broker import list_positions

            held: list[str] = []
            pos_now = _book_pos or list_positions() or []
            for p in pos_now:
                if float(p.get("qty") or 0) <= 0:
                    continue
                raw = str(p.get("symbol", "") or "")
                try:
                    from crypto_universe import is_crypto_symbol, yahoo_symbol

                    if is_crypto_symbol(raw):
                        sym = yahoo_symbol(raw)
                    elif os.getenv("FORTRESS_CRYPTO_SESSION_ONLY", "false").lower() in (
                        "1",
                        "true",
                        "yes",
                    ):
                        continue
                    else:
                        sym = raw.replace("/", "-").upper()
                except Exception:
                    if os.getenv("FORTRESS_CRYPTO_SESSION_ONLY", "false").lower() in (
                        "1",
                        "true",
                        "yes",
                    ):
                        continue
                    sym = raw.replace("/", "-").upper()
                if sym:
                    held.append(sym)
            if held:
                syms = list(dict.fromkeys(held + list(syms)))
                log.info("[FORTRESS] exit scan priority: %d open holding(s) merged into pass", len(held))
            # Cash idle: do NOT scan 500 prepended names. Score NEW tickers first.
            try:
                from analytics.underdeploy_scan import order_scan_for_fill

                _tgt = float(os.getenv("FORTRESS_TARGET_DEPLOY_FRAC", "1.0"))
                # Missing/429 equity snapshot ⇒ fail open and fill idle cash.
                _dep = 0.0 if _book_dep is None else float(_book_dep)
                if _dep > 1.5:
                    _dep = 0.0
                os.environ["DOWNPRESS_SOFT_OK_WHEN_UNDERDEPLOY"] = (
                    "true" if _dep < _tgt - 0.05 else "false"
                )
                if _dep < _tgt - 0.05:
                    before = len(syms)
                    fresh_cap = max(12, int(os.getenv("FORTRESS_UNDERDEPLOY_MAX_SYMBOLS", "48")))
                    prefer: list[str] = []
                    try:
                        from fortress_universe import load_top100_symbols

                        prefer = list(load_top100_symbols() or [])
                    except Exception:
                        pass
                    reserve: list[str] = []
                    try:
                        from alt_assets import alt_scan_symbols

                        reserve.extend(alt_scan_symbols())
                    except Exception:
                        pass
                    try:
                        from analytics.day_movers import today_liquid_gainers

                        reserve.extend(today_liquid_gainers(limit=12))
                    except Exception:
                        pass
                    deprior: list[str] = []
                    try:
                        from analytics.live_rank_sign import invert_p_up_enabled

                        # Fade: keep liquid names first. Do not bury META/MSFT behind microcaps.
                        if invert_p_up_enabled():
                            deprior = [s for s in list(_sh) if s not in set(prefer)]
                    except Exception:
                        pass
                    syms = order_scan_for_fill(
                        syms,
                        held,
                        fresh_cap=fresh_cap,
                        prefer=prefer,
                        deprioritize=deprior,
                        reserve=reserve,
                    )
                    log.info(
                        "[FORTRESS] underdeploy %.0f%%/%.0f%% — recap %d → %d (crypto/movers reserved, top100, holds%s)",
                        100 * _dep,
                        100 * _tgt,
                        before,
                        len(syms),
                        f", micro-deprior={len(deprior)}" if deprior else "",
                    )
            except Exception as e:
                log.warning("[FORTRESS] underdeploy recap failed: %s", e)
        except Exception as e:
            log.debug("[FORTRESS] held-symbol merge: %s", e)

    # Idle cash: unique NEW names, slightly easier dual floor (not invert).
    if use_real and broker == "alpaca" and _book_dep is not None:
        try:
            _tgt_fill = float(os.getenv("FORTRESS_TARGET_DEPLOY_FRAC", "1.0"))
            if float(_book_dep) < _tgt_fill - 0.05:
                fill_min = float(os.getenv("FORTRESS_FILL_MIN_CONF", "0.52"))
                if fill_min < min_p:
                    log.info(
                        "[FORTRESS] underdeploy fill min_conf %.2f → %.2f (unique names, idle cash)",
                        min_p,
                        fill_min,
                    )
                    min_p = fill_min
                if os.getenv("FORTRESS_RELAX_GATES_ON_FILL", "true").lower() in ("1", "true", "yes"):
                    os.environ["FORTRESS_RELAX_GATES"] = "true"
                cur_exec = float(os.getenv("MIN_EXECUTION_CONFIDENCE", "0.62") or 0.62)
                if fill_min < cur_exec:
                    os.environ["MIN_EXECUTION_CONFIDENCE"] = str(fill_min)
                try:
                    fill_math = float(os.getenv("FORTRESS_FILL_MATH_FLOOR", "0.50"))
                    cur_math = float(os.getenv("MATH_P_UP_FLOOR", "0.55") or 0.55)
                    if fill_math < cur_math:
                        os.environ["MATH_P_UP_FLOOR"] = str(fill_math)
                except (TypeError, ValueError):
                    pass
                try:
                    tick_t = float(os.getenv("FORTRESS_TICK_TIMEOUT_SEC", "25") or 25)
                    if tick_t < 20:
                        os.environ["FORTRESS_TICK_TIMEOUT_SEC"] = "25"
                        log.info(
                            "[FORTRESS] underdeploy tick timeout %.0fs → 25s (do not skip liquid names)",
                            tick_t,
                        )
                except (TypeError, ValueError):
                    os.environ["FORTRESS_TICK_TIMEOUT_SEC"] = "25"
        except Exception as e:
            log.debug("[FORTRESS] underdeploy fill min: %s", e)

    # After all priority merges: when buys are blocked, only scan holdings so the
    # pass finishes (stop/TP) instead of hanging on 50+ feature builds overnight.
    if (not buy_ok) and use_real and broker == "alpaca":
        try:
            from alpaca_broker import list_positions

            held_only = [
                str(p.get("symbol", "")).replace("/", "-").upper()
                for p in list_positions()
                if float(p.get("qty") or 0) > 0
            ]
            if held_only:
                before = len(syms)
                syms = list(dict.fromkeys(held_only))
                log.info(
                    "[FORTRESS] exit-only trim %d → %d (held only; buys blocked until open)",
                    before,
                    len(syms),
                )
        except Exception:
            pass
    # Print-window / fear-dump holdings tick 1..n even when underdeploy recap
    # put fresh names first (WMT was buried behind the 92-name crawl).
    if use_real and broker == "alpaca":
        try:
            from analytics.earnings_gap_guard import prioritize_print_window_holdings

            held_now = [
                str(p.get("symbol", "")).replace("/", "-").upper()
                for p in (_book_pos or [])
                if float(p.get("qty") or 0) > 0
            ]
            if not held_now:
                from alpaca_broker import list_positions as _lp_gap

                held_now = [
                    str(p.get("symbol", "")).replace("/", "-").upper()
                    for p in (_lp_gap() or [])
                    if float(p.get("qty") or 0) > 0
                ]
            watch_now = list(_gap_watch or [])
            if held_now:
                syms = prioritize_print_window_holdings(syms, held_now, watch_now)
                if watch_now:
                    log.info(
                        "[FORTRESS] print-window holdings first: %s",
                        ",".join(watch_now[:16]),
                    )
            try:
                from alt_assets import crypto_yahoo_symbols

                coins = [s.strip().upper() for s in crypto_yahoo_symbols() if s.strip()]
                movers: list[str] = []
                try:
                    from analytics.day_movers import today_liquid_gainers

                    movers = today_liquid_gainers(limit=8)
                except Exception:
                    movers = []
                head = [str(s).strip().upper() for s in (watch_now or []) if str(s).strip()]
                boost = [s for s in coins + movers if s and s not in set(head)]
                rest = [s for s in syms if s not in set(head) and s not in set(boost)]
                if boost:
                    syms = list(dict.fromkeys(head + boost + rest))
                    log.info(
                        "[FORTRESS] crypto/mover scan next (%d): %s",
                        len(boost),
                        ",".join(boost[:12]),
                    )
            except Exception:
                pass
        except Exception as e:
            log.debug("[FORTRESS] print-window scan order: %s", e)

    if os.getenv("FORTRESS_CRYPTO_SESSION_ONLY", "false").lower() in ("1", "true", "yes"):
        try:
            from analytics.crypto_alloc import overnight_crypto_scan
            from crypto_universe import is_crypto_symbol, yahoo_symbol

            coins = overnight_crypto_scan()
            held_c: list[str] = []
            for p in (_book_pos or []):
                if float(p.get("qty") or 0) <= 0:
                    continue
                raw = str(p.get("symbol") or "")
                if is_crypto_symbol(raw):
                    held_c.append(yahoo_symbol(raw))
            before = len(syms)
            syms = list(dict.fromkeys(held_c + coins))
            log.info(
                "[FORTRESS] crypto-session final scan %d → %d (coins only; equity exits via hygiene)",
                before,
                len(syms),
            )
        except Exception as e:
            log.debug("[FORTRESS] crypto-session final scan: %s", e)

    spy = _spy_df()
    if isinstance(spy.columns, pd.MultiIndex):
        spy.columns = [c[0] for c in spy.columns]
    regime = simple_regime_from_spy(spy)

    from analytics.market_regime_score import analyze_bull_bear_market

    market_bull_bear = analyze_bull_bear_market(regime, None, 0.0)
    log.info(
        "[FORTRESS] market %s score=%.2f",
        market_bull_bear.get("bull_bear_label"),
        float(market_bull_bear.get("bull_bear_score", 0.0)),
    )

    rm = RiskManager(equity=0.0)
    portfolio_ctx: dict = {}
    if use_real and broker == "alpaca":
        portfolio_ctx = sync_risk_manager_from_alpaca(rm)
        if rm.equity <= 1.0:
            try:
                from risk_manager import MonthlyEquityState as _MES

                st = _MES.load()
            except Exception:
                st = None
            if st and st.start_equity > 1.0:
                rm.equity = float(st.start_equity)
            else:
                # Last resort only — monthly_drawdown_ok ignores the exact PAPER_EQUITY dummy.
                rm.equity = float(os.getenv("PAPER_EQUITY", "100000"))
        try:
            from analytics.day_trade_risk import check_daily_limits, trading_halted
            from alpaca_broker import get_account as _ga_halt

            _acct_halt = _ga_halt() or {}
            live_eq = float(_acct_halt.get("equity") or rm.equity or 0)
            last_eq = float(_acct_halt.get("last_equity") or 0)
            check_daily_limits(live_eq if live_eq >= 100.0 else float(rm.equity), last_equity=last_eq)
            halted, halt_why = trading_halted()
            if halted:
                log.warning("[FORTRESS] BUY HALT — %s (exits/hygiene still allowed)", halt_why)
        except Exception:
            halted, halt_why = False, ""
    else:
        rm.equity = float(os.getenv("PAPER_EQUITY", "100000"))
        halted, halt_why = False, ""
    equity_curve: list[float] = [rm.equity]
    lat = LatencyMonitor()
    bus = SignalBus()
    policy = GuardedPolicyAgent()
    p_hist: list[float] = []
    if use_real and broker == "alpaca" and os.getenv("FORTRESS_LONG_ONLY", "true").lower() in (
        "1",
        "true",
        "yes",
    ):
        n = close_all_short_positions()
        if n:
            log.info("[FORTRESS] flattened %d short position(s)", n)
        try:
            from fortress_portfolio import trim_overweight_singles

            n_trim = trim_overweight_singles()
            if n_trim:
                log.warning("[FORTRESS] trimmed %d overweight single(s) back to equity cap", n_trim)
                portfolio_ctx = sync_risk_manager_from_alpaca(rm)
        except Exception as e:
            log.debug("[FORTRESS] overweight trim: %s", e)
    # Pre-close: cut overnight leverage (post/pre MTM was the "lose before open" bleed).
    if use_real and broker == "alpaca":
        try:
            from analytics.overnight_risk import maybe_overnight_risk_off

            _ovn = maybe_overnight_risk_off(log=log)
            if _ovn.get("action") == "trimmed" and _ovn.get("closed"):
                portfolio_ctx = sync_risk_manager_from_alpaca(rm)
                log.info(
                    "[FORTRESS] overnight risk-off closed=%s deploy_was=%.0f%% cap=%.0f%%",
                    ",".join(_ovn.get("closed") or []),
                    100 * float(_ovn.get("deploy_frac") or 0),
                    100 * float(_ovn.get("cap_frac") or 0),
                )
        except Exception as e:
            log.debug("[FORTRESS] overnight risk-off: %s", e)
    _scan_alpaca_exits(use_real=use_real, broker=broker, rm=rm)
    if use_real and broker == "alpaca":
        portfolio_ctx = sync_risk_manager_from_alpaca(rm)
        try:
            from analytics.profit_cushion_gate import refresh_profit_gate

            refresh_profit_gate()
        except Exception as e:
            log.debug("[FORTRESS] profit gate refresh: %s", e)
    # Do not clamp through HORIZON_TOP_K — that is ranking default (top couple per
    # timeframe), not the idle-cash fill size. Unique names deploy leftover equity.
    top_buys_per_pass = max(
        1,
        int(os.getenv("FORTRESS_TOP_BUYS_PER_PASS", os.getenv("HORIZON_TOP_K", "3")) or 3),
    )
    buy_candidates: list[dict] = []
    scanned = 0
    scan_t0 = time.monotonic()
    pass_max_sec = float(os.getenv("FORTRESS_PASS_MAX_SEC", "900") or 0)
    weekend_hold_fill = False
    if (
        use_real
        and broker == "alpaca"
        and os.getenv("FORTRESS_CRYPTO_SESSION_ONLY", "false").lower() in ("1", "true", "yes")
    ):
        try:
            from alpaca_broker import list_positions as _lp_we
            from fortress_portfolio import allocate_idle_cash_split, deploy_budget_usd, idle_cash_fill_active

            ctx = portfolio_ctx or {}
            if idle_cash_fill_active(ctx):
                bud = deploy_budget_usd(ctx)
                leftover = float(bud.get("budget") or 0)
                min_n = float(os.getenv("MIN_ORDER_NOTIONAL", "100") or 100)
                pos_idle = _lp_we() or []
                extra = allocate_idle_cash_split(
                    leftover,
                    positions=pos_idle,
                    equity=float(bud.get("equity") or rm.equity or 0),
                    max_single_usd=float(bud.get("max_single_usd") or 0),
                    min_n=min_n,
                    already={},
                    banned={
                        x.strip().upper()
                        for x in os.getenv(
                            "FORTRESS_BAN_INDEX_ETFS",
                            "SPY,QQQ,IWM,DIA,VOO,VTI,SOXX,XLK,XLF,XLE",
                        ).split(",")
                        if x.strip()
                    },
                )
                by_sym = {
                    str(p.get("symbol") or "").replace("/", "-").upper(): p
                    for p in pos_idle
                    if float(p.get("qty") or 0) > 0
                }
                for t, n_add in extra.items():
                    tu = str(t).replace("/", "-").upper()
                    p = by_sym.get(tu) or {}
                    px = float(p.get("current_price") or p.get("avg_entry_price") or 0)
                    if px <= 0 or float(n_add) < min_n:
                        continue
                    gain = p.get("unrealized_plpc")
                    try:
                        gain_f = float(gain) if gain is not None else 0.0
                    except (TypeError, ValueError):
                        gain_f = 0.0
                    buy_candidates.append(
                        {
                            "ticker": tu,
                            "p_up": 0.58,
                            "p_adj": 0.58,
                            "p_entry": 0.58,
                            "exec_c": 0.62,
                            "sent": 0.0,
                            "nf_f": 0.0,
                            "top100": False,
                            "px": px,
                            "scale": 1.0,
                            "row": None,
                            "existing_mv": abs(float(p.get("market_value") or 0)),
                            "existing_gain": gain_f,
                            "exited": False,
                            "score": 0.20,
                            "hf_boost": 0.0,
                            "hf_meta": {},
                            "jp_candle": {},
                            "force_priority": False,
                            "earnings_meta": {},
                            "conviction": 0.16,
                            "weekend_idle_n": float(n_add),
                        }
                    )
                if buy_candidates:
                    weekend_hold_fill = True
                    scanned = len(buy_candidates)
                    log.info(
                        "[FORTRESS] weekend idle-cash %d hold(s) $%.0f — skip slow coin ticks",
                        len(buy_candidates),
                        sum(float(c.get("weekend_idle_n") or 0) for c in buy_candidates),
                    )
        except Exception as e:
            log.warning("[FORTRESS] weekend idle-cash prefill: %s", e)
    bench_closes = None
    if spy is not None and not spy.empty and "Close" in spy.columns:
        bench_closes = spy["Close"].astype(float)

    def _pair_closes_loader(peer: str) -> pd.Series | None:
        try:
            end = pd.Timestamp.utcnow().strftime("%Y-%m-%d")
            start = (pd.Timestamp.utcnow() - pd.Timedelta(days=int(os.getenv("FORTRESS_FEATURE_LOOKBACK_DAYS", "400") or 400))).strftime("%Y-%m-%d")
            pdf = build_features(peer, start, end)
            if pdf.empty or "Close" not in pdf.columns:
                return None
            return pdf["Close"].astype(float)
        except Exception:
            return None

    regime_hf = float(market_bull_bear.get("bull_bear_score", 0.0))

    for t in syms:
        if weekend_hold_fill:
            break
        if os.getenv("FORTRESS_CRYPTO_SESSION_ONLY", "false").lower() in ("1", "true", "yes"):
            try:
                from crypto_universe import is_crypto_symbol

                if not is_crypto_symbol(t):
                    continue
            except Exception:
                continue
        if is_halted():
            log.error("[FORTRESS] Kill switch — stopping")
            break
        if pass_max_sec > 0 and (time.monotonic() - scan_t0) >= pass_max_sec:
            log.warning(
                "[FORTRESS] pass scan deadline %.0fs — executing %d buy candidates early (scanned=%d/%d)",
                pass_max_sec,
                len(buy_candidates),
                scanned,
                len(syms),
            )
            break

        try:
            log.info("[FORTRESS] tick start %s (%d/%d)", t, scanned + 1, len(syms))
            if os.getenv("FORTRESS_CROSSVERIFY", "false").lower() in ("1", "true", "yes"):
                _, integrity = cross_verify_close(t, "2023-01-01", None)
                if integrity.get("close_mismatch"):
                    log.warning("[FORTRESS] Data mismatch %s: %s", t, integrity["close_mismatch"])

            end = pd.Timestamp.utcnow().strftime("%Y-%m-%d")
            lookback = int(os.getenv("FORTRESS_FEATURE_LOOKBACK_DAYS", "400") or 400)
            start = (pd.Timestamp.utcnow() - pd.Timedelta(days=lookback)).strftime("%Y-%m-%d")
            tick_timeout = float(os.getenv("FORTRESS_TICK_TIMEOUT_SEC", "25") or 0)
            with lat.track("feature_build"):
                t_feat = t
                crypto_tick = False
                try:
                    from crypto_universe import is_crypto_symbol, yahoo_symbol

                    if is_crypto_symbol(t):
                        t_feat = yahoo_symbol(t)
                        crypto_tick = True
                except Exception:
                    t_feat = t
                if crypto_tick:
                    tick_timeout = max(
                        tick_timeout,
                        float(os.getenv("FORTRESS_CRYPTO_TICK_TIMEOUT_SEC", "90") or 90),
                    )
                try:
                    df = _call_with_timeout(build_features, tick_timeout, t_feat, start, end)
                except TimeoutError:
                    short_lb = min(
                        lookback,
                        int(os.getenv("FORTRESS_TICK_RETRY_LOOKBACK_DAYS", "90") or 90),
                    )
                    start2 = (pd.Timestamp.utcnow() - pd.Timedelta(days=short_lb)).strftime("%Y-%m-%d")
                    log.warning(
                        "[FORTRESS] tick timeout %s after %.0fs — retry lookback %dd",
                        t,
                        tick_timeout,
                        short_lb,
                    )
                    try:
                        df = _call_with_timeout(build_features, tick_timeout, t_feat, start2, end)
                    except TimeoutError:
                        log.warning("[FORTRESS] tick timeout %s retry failed — skip", t)
                        continue
            if df is None or getattr(df, "empty", True):
                continue

            intel_timeout = float(os.getenv("FORTRESS_INTEL_TIMEOUT_SEC", "12") or 0)
            try:
                nf_f, _tf_f = _call_with_timeout(_intel_news_factors, intel_timeout, t)
            except TimeoutError:
                log.warning("[FORTRESS] intel timeout %s — continue with neutral news", t)
                nf_f, _tf_f = 0.0, {}
            try:
                sent, news_intel = _call_with_timeout(_fortress_blend_sentiment, intel_timeout, t)
            except TimeoutError:
                log.warning("[FORTRESS] sentiment timeout %s — continue with neutral sent", t)
                sent, news_intel = 0.0, {}
            row, px = None, None
            try:
                from analytics.completed_bar import completed_daily_signal_row

                row, px = completed_daily_signal_row(df)
            except Exception:
                row = df.iloc[-1].copy()
                px = float(row["Close"])
            # Models train with sentiment features at 0; keep serve aligned and apply
            # live sentiment only via soft gates / score impulses (not fake lag slots).
            row["sentiment"] = 0.0
            row["lag_1_sentiment"] = 0.0
            row["lag_2_sentiment"] = 0.0
            row["lag_3_sentiment"] = 0.0

            path = os.path.join("models", f"{t}_model.pkl")
            if not _fortress_lite_intel() and not os.path.isfile(path):
                continue

            if not _share_price_ok(px):
                continue

            with lat.track("predict_row"):
                # Keep predict on the main thread (no ThreadPool). XGB/OMP + abandoned
                # timeout workers deadlocked the scan (libomp kmp_flag wait forever).
                pred_timeout = float(os.getenv("FORTRESS_PREDICT_TIMEOUT_SEC", "15") or 0)
                hpred = os.getenv("FORTRESS_PREDICT_HORIZON", "").strip()

                def _do_predict():
                    if hpred:
                        return predict_row_horizon(path, row, horizon=hpred)
                    return predict_row_details(path, row)

                try:
                    if _fortress_lite_intel():
                        mom = float(row.get("mom_20", 0.0) or 0.0)
                        ret = float(row.get("returns", 0.0) or 0.0)
                        p_up = float(max(0.05, min(0.95, 0.50 + 1.5 * mom + 0.5 * ret)))
                        pred = 1 if p_up >= 0.5 else 0
                        det = {
                            "p_up": p_up,
                            "pred": pred,
                            "p_short": 1.0 - p_up,
                            "p_long": p_up,
                        }
                        log.info(
                            "[FORTRESS] lite tick %s p_up=%.3f mom=%.3f",
                            t,
                            p_up,
                            mom,
                        )
                    else:
                        det = _do_predict()
                except Exception as e:
                    log.warning("[FORTRESS] predict failed %s: %s — skip", t, e)
                    continue
                if det.get("p_up") is None or det.get("head_missing"):
                    continue
                pred = int(det["pred"])
                p_up = float(det["p_up"])
                _ = pred_timeout  # reserved; see FORTRESS_LITE_INTEL / OMP_NUM_THREADS=1
            if os.getenv("USE_MULTI_ALGO_FUSION", "true").lower() in ("1", "true", "yes") and not _fortress_lite_intel():
                try:
                    fd = fused_decision(
                        ticker=t,
                        model_bundle_path=path,
                        row=row,
                        p_base=float(p_up),
                        min_conf=float(min_p),
                    )
                    p_up = float(fd["p_final"])
                    pred = 1 if p_up >= 0.5 else 0
                except Exception:
                    pass
            _ule_live = False
            try:
                from analytics.ultimate_learning_engine import enabled as _ule_enabled

                _ule_live = bool(_ule_enabled())
            except Exception:
                _ule_live = False
            _lstm_p_for_ule = None
            if os.getenv("BLEND_LSTM_INTO_META", "true").lower() in ("1", "true", "yes") and not _fortress_lite_intel():
                try:
                    from analytics.lstm_head import lstm_proba_up

                    sig_df = df.loc[: row.name] if getattr(row, "name", None) in df.index else df
                    lstm_p = lstm_proba_up(t, sig_df)
                    if lstm_p is not None:
                        _lstm_p_for_ule = float(lstm_p)
                        if not _ule_live:
                            blend_w = float(os.getenv("LSTM_BLEND_WEIGHT", "0.25"))
                            try:
                                from analytics.vector_math import logit_pair_blend

                                p_up = logit_pair_blend(float(p_up), float(lstm_p), blend_w)
                            except Exception:
                                p_up = float((1.0 - blend_w) * float(p_up) + blend_w * float(lstm_p))
                            pred = 1 if p_up >= 0.5 else 0
                except Exception:
                    pass
            try:
                from analytics.horizon_picks import horizon_independent as _tf_indep

                _blend_intra = not _tf_indep()
            except Exception:
                _blend_intra = True
            if _blend_intra:
                try:
                    from intraday.live_infer import blend_intraday_p, live_intraday_p_up

                    p_intra = live_intraday_p_up(t)
                    p_up, _ = blend_intraday_p(float(p_up), p_intra)
                    pred = 1 if p_up >= 0.5 else 0
                except Exception:
                    pass
            from fortress_universe import is_top100_equity

            top100 = is_top100_equity(t)
            if not _fortress_lite_intel() and os.getenv("USE_FOUNDATION_FORECAST", "true").lower() in (
                "1",
                "true",
                "yes",
            ):
                try:
                    from analytics.foundation_forecast import foundation_forecast_p
                    from analytics.signal_enhance import blend_foundation_safe

                    ff = foundation_forecast_p(t, df=df)
                    if ff:
                        p_up, _, _ = blend_foundation_safe(
                            float(p_up), float(ff["p_up"]), is_top100=top100
                        )
                        pred = 1 if p_up >= 0.5 else 0
                except Exception:
                    pass
            from analytics.execution_confidence import execution_confidence as _exec_conf_fn

            try:
                from analytics.horizon_picks import horizon_independent as _tf_indep_exec

                _pass_other_heads = not _tf_indep_exec()
            except Exception:
                _pass_other_heads = True
            _ps_exec = det.get("p_short") if _pass_other_heads else None
            _pl_exec = det.get("p_long") if _pass_other_heads else None
            exec_c_pre, _ = _exec_conf_fn(
                float(p_up),
                _ps_exec,
                _pl_exec,
            )
            # Heavier online adaptation from neural replay models.
            # When ULE is on, do NOT linear-blend here — ULE LEA-fuses neural as its own channel.
            _neural_p_for_ule = None
            if os.getenv("USE_NEURAL_ENSEMBLE", "true").lower() in ("1", "true", "yes") and not _fortress_lite_intel():
                try:
                    from online_learning.neural_ensemble import neural_ensemble_details

                    neural_state = {
                        "p_up_base": float(p_up),
                        "p_short_model": float(det.get("p_short", 1.0 - p_up)),
                        "p_long_model": float(det.get("p_long", p_up)),
                        "execution_confidence": float(exec_c_pre),
                        "sentiment_intensity": float(sent),
                        "sentiment": float(sent),
                        "news_factor": float(nf_f),
                        "transcript_factor": float(_tf_f),
                        "volume_ratio": float(row.get("volume_ratio", 1.0)),
                        "momentum_5d": float(row.get("mom_20", 0.0)),
                        "rs_spy": float(row.get("beta_proxy_60", 1.0)),
                        "dip_signal": float(max(0.0, -float(row.get("returns", 0.0)))),
                        "atr_14": float(row.get("atr_14", px * 0.02)),
                        "alpha_proxy_20": float(row.get("alpha_proxy_20", 0.0)),
                    }
                    nb = neural_ensemble_details(t, neural_state)
                    if nb and nb.get("ensemble_p_up") is not None:
                        _neural_p_for_ule = float(nb["ensemble_p_up"])
                        if not _ule_live:
                            nw = float(os.getenv("NEURAL_BLEND_WEIGHT", "0.45"))
                            if float(nb.get("disagreement_std", 0.0)) > float(os.getenv("NEURAL_MAX_DISAGREE_STD", "0.18")):
                                nw *= float(os.getenv("NEURAL_DISAGREE_MULT", "0.35"))
                            try:
                                from analytics.vector_math import logit_pair_blend

                                p_up = logit_pair_blend(float(p_up), float(nb["ensemble_p_up"]), nw)
                            except Exception:
                                p_up = float((1.0 - nw) * float(p_up) + nw * float(nb["ensemble_p_up"]))
                            pred = 1 if p_up >= 0.5 else 0
                except Exception:
                    pass
            if top100:
                try:
                    from analytics.vector_math import apply_logit_tilt, delta_p_to_delta_ell

                    boost = float(os.getenv("TOP100_FORTRESS_P_BOOST", "0.025"))
                    p_up = apply_logit_tilt(float(p_up), delta_p_to_delta_ell(float(p_up), boost))
                except Exception:
                    p_up = min(
                        0.99,
                        float(p_up) + float(os.getenv("TOP100_FORTRESS_P_BOOST", "0.025")),
                    )
            from analytics.execution_confidence import (
                execution_confidence,
                min_execution_confidence,
                passes_confidence_gates,
                use_execution_confidence_gate,
            )

            exec_c, _ = execution_confidence(
                p_up,
                det.get("p_short") if _pass_other_heads else None,
                det.get("p_long") if _pass_other_heads else None,
            )
            min_p_sym = min_p
            cortex_meta: dict = {}
            try:
                from cortex.integrate import cortex_decision

                cortex_meta = cortex_decision(
                    {"symbol": t, "rsi_14": float(row.get("rsi_14", 50) or 50), "neural_p_up": float(p_up)}
                )
                min_p_sym = max(0.50, float(min_p_sym) - float(cortex_meta.get("buy_bias", 0.0)))
            except Exception:
                pass
            min_exec = float(min_execution_confidence())
            crowd_meta: dict = {}
            if os.getenv("USE_CROWD_BEHAVIOR", "true").lower() in ("1", "true", "yes"):
                try:
                    from analytics.crowd_behavior import apply_investor_context
                    from intel.social_sentiment import social_sentiment_score

                    soc = social_sentiment_score(t)
                    crowd_meta = apply_investor_context(
                        float(p_up),
                        float(exec_c),
                        symbol=t,
                        intended_side="buy",
                        news_sentiment=float(sent),
                        news_factor=float(nf_f),
                        social_score=float(soc.get("score", 0.0)),
                        social_bull_share=float(soc.get("bull_share", 0.5)),
                        volume_ratio=float(row.get("volume_ratio", 1.0)),
                        vix=float(regime.vix),
                        min_exec_base=min_exec,
                        fetch_after_hours=os.getenv("FORTRESS_AFTER_HOURS", "true").lower()
                        in ("1", "true", "yes"),
                    )
                    # ULE owns p* fusion — keep crowd as pressure evidence only
                    if not _ule_live:
                        p_up = float(crowd_meta["p_up"])
                        pred = 1 if p_up >= 0.5 else 0
                    exec_c = float(crowd_meta["execution_confidence"])
                    min_exec = float(crowd_meta["min_exec_effective"])
                except Exception as e:
                    log.debug("[CROWD] fortress %s skipped: %s", t, e)
            _bb_score = None
            try:
                from analytics.market_regime_score import apply_bull_bear_to_exec, apply_bull_bear_to_p_up
                from analytics.probability_calibrate import calibrate_probability

                if isinstance(market_bull_bear, dict):
                    _bb_score = market_bull_bear.get("bull_bear_score", market_bull_bear.get("score"))
                elif market_bull_bear is not None:
                    try:
                        _bb_score = float(market_bull_bear)
                    except (TypeError, ValueError):
                        _bb_score = None
                if not _ule_live:
                    p_up, _ = apply_bull_bear_to_p_up(float(p_up), market_bull_bear)
                    exec_c, _ = apply_bull_bear_to_exec(float(exec_c), market_bull_bear)
                    cal = calibrate_probability(p_up)
                    p_up = float(cal["calibrated"])
                    pred = 1 if p_up >= 0.5 else 0
                else:
                    # Still tighten exec for regime; p* comes from ULE
                    exec_c, _ = apply_bull_bear_to_exec(float(exec_c), market_bull_bear)
            except Exception:
                pass
            # Ultimate Learning Engine — sole learned LEA fuse
            try:
                from analytics.ultimate_learning_engine import apply_to_p_up as ule_apply, enabled as ule_on

                if ule_on():
                    p_up, _ule = ule_apply(
                        t,
                        float(p_up),
                        context={
                            "rsi_14": float(row.get("rsi_14", 50) or 50),
                            "news_factor": float(nf_f),
                            "crowd_pressure": float(crowd_meta.get("crowd_pressure", 0.0) or 0.0),
                            "neural_p_up": _neural_p_for_ule,
                            "lstm_p_up": _lstm_p_for_ule,
                            "bull_bear_score": _bb_score,
                            "p_up_base": float(p_up),
                            "p_short_model": float(det.get("p_short", 1.0 - p_up) or 0.5),
                            "p_long_model": float(det.get("p_long", p_up) or 0.5),
                            "execution_confidence": float(exec_c),
                            "mom_5d": float(row.get("mom_20", row.get("mom_5d", 0.0)) or 0.0),
                            "rs_spy": float(row.get("beta_proxy_60", row.get("rs_spy", 1.0)) or 1.0),
                            "row": row,
                            "sleeve": "fortress",
                        },
                    )
                    if _ule.get("applied"):
                        pred = 1 if p_up >= 0.5 else 0
                        log.debug(
                            "[ULE] %s p %.3f→%.3f active=%s",
                            t,
                            float(_ule.get("p_before") or 0),
                            float(p_up),
                            _ule.get("active"),
                        )
                    # Display/gate calibrate AFTER fusion (does not feed back into LEA)
                    try:
                        from analytics.probability_calibrate import calibrate_probability

                        p_up = float(calibrate_probability(p_up)["calibrated"])
                        pred = 1 if p_up >= 0.5 else 0
                    except Exception:
                        pass
                else:
                    raise RuntimeError("ule_off")
            except Exception:
                # Legacy path when ULE disabled
                try:
                    from analytics.hidden_pattern_anomaly import hidden_pattern_p_blend

                    p_up, _hp_meta = hidden_pattern_p_blend(t, float(p_up))
                    if _hp_meta.get("applied"):
                        pred = 1 if p_up >= 0.5 else 0
                except Exception:
                    pass
                try:
                    from self_modify.strategy_overlay import rank_tilt

                    rsi = float(row.get("rsi_14", 50) or 50)
                    tilt = rank_tilt(t, float(p_up), {"rsi_14": rsi})
                    try:
                        from analytics.vector_math import apply_logit_tilt, delta_p_to_delta_ell

                        p_up = apply_logit_tilt(float(p_up), delta_p_to_delta_ell(float(p_up), tilt))
                    except Exception:
                        p_up = max(0.0, min(1.0, float(p_up) + tilt))
                    pred = 1 if p_up >= 0.5 else 0
                except Exception:
                    pass
                try:
                    from cortex.integrate import cortex_rank_tilt

                    rsi = float(row.get("rsi_14", 50) or 50)
                    tilt = cortex_rank_tilt(t, float(p_up), {"rsi_14": rsi})
                    try:
                        from analytics.vector_math import apply_logit_tilt, delta_p_to_delta_ell

                        p_up = apply_logit_tilt(float(p_up), delta_p_to_delta_ell(float(p_up), tilt))
                    except Exception:
                        p_up = max(0.0, min(1.0, float(p_up) + tilt))
                    pred = 1 if p_up >= 0.5 else 0
                except Exception:
                    pass
            try:
                from analytics.the_algorithm import refine_live

                p_up, _algo = refine_live(
                    t,
                    float(p_up),
                    row=row,
                    sent=float(sent),
                    nf=float(nf_f),
                )
                pred = 1 if p_up >= 0.5 else 0
                if _algo.get("skip_buy"):
                    log.info("[ALGO] skip BUY %s — %s", t, _algo.get("why"))
            except Exception:
                pass
            p_adj = _p_up_adjusted(p_up, nf_f)
            _is_crypto = False
            try:
                from crypto_universe import is_crypto_symbol

                _is_crypto = is_crypto_symbol(t)
            except Exception:
                _is_crypto = False
            if _is_crypto:
                try:
                    from analytics.crypto_math import overlay_equity_p, score_crypto

                    cs = score_crypto(t)
                    mix = float(os.getenv("FORTRESS_CRYPTO_MATH_MIX", "0.80") or 0.80)
                    p_eq = float(p_adj)
                    p_adj = overlay_equity_p(p_eq, float(cs.p_up), mix)
                    log.info(
                        "[FORTRESS] crypto_math overlay %s eq=%.3f math=%.3f mix=%.2f → %.3f",
                        t,
                        p_eq,
                        float(cs.p_up),
                        mix,
                        float(p_adj),
                    )
                except Exception as e:
                    log.debug("[FORTRESS] crypto_math overlay %s: %s", t, e)
            # Fade 1d heads on NEW buys only. Never invert exits — that dumped ORCL.
            # Crypto uses its own drivers — do not apply equity midday invert.
            p_entry = p_adj
            if not _is_crypto:
                try:
                    from analytics.live_rank_sign import apply_live_sign

                    p_entry = apply_live_sign(p_adj)
                except Exception:
                    p_entry = p_adj
            pred_entry = 1 if float(p_entry) >= 0.5 else 0
            # Live p for certainty of *this* 1d sleeve. Other horizons do not veto.
            try:
                _live_exec, _ = _exec_conf_fn(
                    float(p_entry),
                    det.get("p_short") if _pass_other_heads else None,
                    det.get("p_long") if _pass_other_heads else None,
                )
                exec_c = float(_live_exec)
            except Exception:
                pass
            try:
                from analytics.live_rank_sign import entry_confidence_ok

                conf_ok = entry_confidence_ok(p_entry, exec_c, min_p_sym, min_exec)
            except Exception:
                conf_ok = (
                    passes_confidence_gates(p_entry, exec_c, min_p_sym, min_exec)
                    if use_execution_confidence_gate()
                    else (p_entry >= min_p_sym)
                )
            bus.publish(
                "fortress_score",
                t,
                {
                    "p_up": float(p_up),
                    "p_adj": float(p_adj),
                    "p_entry": float(p_entry),
                    "pred_entry": int(pred_entry),
                    "news_factor": float(nf_f),
                    "pred": int(pred),
                    "execution_confidence": float(exec_c),
                    "crowd_pressure": float(crowd_meta.get("crowd_pressure", 0.0)),
                    "expected_crowd_action": str(crowd_meta.get("expected_crowd_action", "")),
                    "cortex_tick": cortex_meta.get("tick"),
                    "cortex_laws": cortex_meta.get("laws"),
                    "cortex_buy_bias": cortex_meta.get("buy_bias"),
                    "cortex_rank_tilt": cortex_meta.get("rank_tilt"),
                },
            )
            p_hist.append(float(p_adj))
            scale = regime.position_scale
            try:
                from fortress_portfolio import idle_cash_fill_active as _idle_fill

                if is_reduced_risk() and not _idle_fill(portfolio_ctx):
                    scale *= 0.5
            except Exception:
                if is_reduced_risk():
                    scale *= 0.5

            vol_mult = float(os.getenv("VOLUME_CONFIRM_MULT", "1.0"))
            vol_ok = volume_confirmed(row, mult=vol_mult)
            daily_bull = bool(int(row.get("daily_bull_trend", 0)))
            mtf_ok = mtf_buy_ok(daily_bull, t, rsi_oversold=float(os.getenv("MTF_RSI_MAX", "35")))
            relax_all = _gates_relaxed()
            news_ok = True if relax_all else _news_supports_buy(nf_f, sent)
            if news_intel.get("block_long") or news_intel.get("narrative") == "bad_news":
                news_ok = False

            want_buy = conf_ok and news_ok and not block_long_on_sentiment(sent, symbol=t)
            if crowd_meta.get("crowd_block_fomo"):
                want_buy = False
            want_buy = want_buy and (vol_ok or relax_all) and (mtf_ok or relax_all)
            if want_buy:
                try:
                    from analytics.day_movers import skip_post_print_chase

                    _ret1 = None
                    _mom5 = None
                    try:
                        if "Close" in df.columns and len(df) >= 2:
                            _c = df["Close"].astype(float)
                            _ret1 = float(_c.iloc[-1] / _c.iloc[-2] - 1.0)
                        if "Close" in df.columns and len(df) >= 6:
                            _c = df["Close"].astype(float)
                            _mom5 = float(_c.iloc[-1] / _c.iloc[-6] - 1.0)
                    except Exception:
                        pass
                    _ex, _ex_why = skip_post_print_chase(t, ret_1d=_ret1, mom_5d=_mom5)
                    if _ex:
                        want_buy = False
                        log.info("[FORTRESS] skip chase %s — %s (do not buy the post-print rip)", t, _ex_why)
                except Exception:
                    pass
            if want_buy and not _is_crypto:
                try:
                    from analytics.proven_online import tight_pick

                    _mom = float(row.get("mom_20") or row.get("returns") or 0.0)
                    _hmm = 0.0
                    if isinstance(market_bull_bear, dict):
                        _hmm = float(market_bull_bear.get("bull_bear_score") or 0.0)
                    tp = tight_pick(
                        t,
                        p_up=float(p_entry),
                        exec_c=float(exec_c),
                        mom_5d=_mom,
                        rs_spy=1.0 if _mom >= 0 else 0.99,
                        hmm=_hmm,
                        row=row,
                        sleeve="fortress",
                    )
                    if not tp.get("ok"):
                        want_buy = False
                        log.info(
                            "[FORTRESS] TIGHT_PICK skip %s p=%.3f agree=%s/%s hedge=%.3f chase=%s",
                            t,
                            float(p_entry),
                            tp.get("agree"),
                            tp.get("need"),
                            float(tp.get("p_cal") or 0.5),
                            tp.get("chase"),
                        )
                except Exception as e:
                    log.debug("[FORTRESS] tight_pick %s: %s", t, e)
            candle_meta: dict = {}
            jp_hard_skip = False
            if os.getenv("FORTRESS_USE_JP_CANDLES", "true").lower() in ("1", "true", "yes"):
                try:
                    candle_df = df
                    if (not _fortress_lite_intel()) and os.getenv("DAY_TRADE_USE_YAHOO", "true").lower() in (
                        "1",
                        "true",
                        "yes",
                    ):
                        try:
                            from analytics.day_trade_yahoo import fetch_yahoo_bars

                            ydf = fetch_yahoo_bars(t)
                            if ydf is not None and len(ydf) >= 10:
                                candle_df = ydf
                        except Exception:
                            pass
                    use_multi = (not _fortress_lite_intel()) and os.getenv(
                        "FORTRESS_JP_MULTI_TF", "true"
                    ).lower() in ("1", "true", "yes")
                    if use_multi:
                        from analytics.jp_candle_intel import assess_advanced, apply_to_p_adj

                        intel = assess_advanced(t, candle_df)
                        candle_meta = intel.to_dict()
                        p_adj, want_buy, jp_log = apply_to_p_adj(p_adj, intel, want_buy=want_buy)
                        if jp_log.startswith("boost"):
                            log.info("[FORTRESS] jp-candle %s — %s trend=%+d", t, jp_log, intel.trend)
                        elif jp_log.startswith("bearish composite"):
                            jp_hard_skip = True
                            log.info("[FORTRESS] jp-candle skip BUY %s — %s", t, jp_log)
                        elif jp_log.startswith("weak bear"):
                            log.info("[FORTRESS] jp-candle %s — %s", t, jp_log)
                        elif jp_log and not want_buy:
                            jp_hard_skip = True
                            log.info("[FORTRESS] jp-candle skip BUY %s — %s", t, jp_log)
                    else:
                        from analytics.jp_candles import assess_candles_from_df

                        lookback = int(os.getenv("FORTRESS_JP_CANDLE_LOOKBACK", "6"))
                        ca = assess_candles_from_df(candle_df, lookback=lookback)
                        candle_meta = ca.to_dict()
                        boost = float(os.getenv("FORTRESS_JP_CANDLE_BOOST", "0.045"))
                        require_bull = os.getenv("FORTRESS_JP_CANDLE_REQUIRE_BULL", "false").lower() in (
                            "1",
                            "true",
                            "yes",
                        )
                        from analytics.jp_candle_intel import STRONG_BEAR_PATTERNS, WEAK_BEAR_PATTERNS

                        if ca.pattern in STRONG_BEAR_PATTERNS and ca.bias < 0 and not relax_all:
                            want_buy = False
                            jp_hard_skip = True
                            log.info("[FORTRESS] jp-candle skip BUY %s — %s (bearish)", t, ca.pattern)
                        elif ca.pattern in WEAK_BEAR_PATTERNS and ca.pattern != "DOJI" and ca.bias < 0:
                            p_adj = max(0.01, float(p_adj) - 0.015)
                            log.info("[FORTRESS] jp-candle %s — weak bear tilt (%s)", t, ca.pattern)
                        elif ca.bias > 0:
                            from analytics.jp_candle_rl import adjust_boost

                            boost, w = adjust_boost(boost, ca.pattern)
                            p_adj = min(0.99, float(p_adj) + boost)
                            log.info(
                                "[FORTRESS] jp-candle boost %s — %s bias=+%d trend=%+d rl×%.2f",
                                t,
                                ca.pattern,
                                ca.bias,
                                ca.trend,
                                w,
                            )
                        elif require_bull and not relax_all and ca.pattern not in ("DOJI", "NONE", ""):
                            want_buy = False
                            jp_hard_skip = True
                            log.info("[FORTRESS] jp-candle skip BUY %s — no bullish pattern", t)
                except Exception as e:
                    log.debug("[FORTRESS] jp-candle %s: %s", t, e)
            if not _is_crypto:
                want_buy = want_buy and _accuracy_buy_extra(
                    pred=pred,
                    p_adj=p_adj,
                    nf_f=nf_f,
                    sent=sent,
                    vol_ok=vol_ok,
                    mtf_ok=mtf_ok,
                    daily_bull=daily_bull,
                )
            hard_gate_block = False
            try:
                from intel.near_term_headwinds import blocks_playbook_buy

                blocked, hw_reasons = blocks_playbook_buy(t)
                ignore_sym = os.getenv("FORTRESS_IGNORE_SYMPATHY_RISK", "false").lower() in (
                    "1",
                    "true",
                    "yes",
                )
                if blocked and ignore_sym and hw_reasons:
                    if any(
                        "sympathy" in str(r).lower() or "earnings" in str(r).lower()
                        for r in hw_reasons
                    ):
                        blocked = False
                if blocked:
                    want_buy = False
                    hard_gate_block = True
                    log.info(
                        "[FORTRESS] headwind skip BUY %s — %s",
                        t,
                        (hw_reasons[0] if hw_reasons else "near-term block"),
                    )
            except Exception:
                pass
            # Hard math gate: commodity / sector / trend downward pressure (not paper-relaxed)
            try:
                from intel.downward_pressure import blocks_new_buy as _dp_block

                dp_blocked, dp_reason = _dp_block(t)
                if dp_blocked:
                    want_buy = False
                    hard_gate_block = True
                    log.info("[FORTRESS] downward-pressure skip BUY %s — %s", t, dp_reason)
            except Exception:
                pass
            try:
                from intel.algo_risk_filter import blocks_buy

                risk_blocked, risk_reason = blocks_buy(t)
                if risk_blocked and os.getenv("FORTRESS_IGNORE_SYMPATHY_RISK", "false").lower() in (
                    "1",
                    "true",
                    "yes",
                ):
                    if "sympathy" in str(risk_reason).lower() or "earnings in" in str(risk_reason).lower():
                        risk_blocked = False
                if risk_blocked:
                    want_buy = False
                    hard_gate_block = True
                    log.info("[FORTRESS] risk filter skip BUY %s — %s", t, risk_reason)
            except Exception:
                pass
            sell_p = _sell_threshold()
            disable_sig = os.getenv("FORTRESS_DISABLE_SIGNAL_EXIT", "false").lower() in ("1", "true", "yes")
            want_sell = (not disable_sig) and p_adj <= sell_p

            # --- FORCE STICK / high-conviction UP: watch-only → must-size buy ---
            # Soft gates (vol/mtf/jp) often blocked SBUX day-of and BX-like names while
            # index ETFs filled the book. Hard risk (index ban, single-name cap, BP) still applies.
            # Earnings STICK may override hard gates (day-of print); general PRED_FORCE does not.
            force_priority = False
            soft_blocked = not want_buy
            try:
                from pathlib import Path as _Hb

                _Hb("data").mkdir(parents=True, exist_ok=True)
                _Hb("data/fortress_heartbeat.txt").write_text(
                    f"{time.time():.3f} {t} p_adj={float(p_adj):.3f}\n",
                    encoding="utf-8",
                )
            except Exception:
                pass
            try:
                from intel.historical_events import holdings_earnings_plan as _hep_force

                _epf = _hep_force(t, is_holding=False)
                _stick_on = bool(
                    _epf.get("encourage_pre_momentum") or _epf.get("stick_to_prediction")
                )
                _stick_min = float(os.getenv("EARNINGS_STICK_MIN_P", "0.62"))
                _stick_force_on = os.getenv("EARNINGS_STICK_FORCE_BUY", "false").lower() in (
                    "1",
                    "true",
                    "yes",
                )
                try:
                    _stick_dte = int(_epf.get("days_to") if _epf.get("days_to") is not None else 99)
                except (TypeError, ValueError):
                    _stick_dte = 99
                _stick_max_dte = int(os.getenv("EARNINGS_STICK_FORCE_MAX_DTE", "1"))
                _dual_min = float(os.getenv("MIN_MODEL_CONFIDENCE", os.getenv("BUY_THRESHOLD", "0.62")))
                _gap_block = bool(_epf.get("print_released"))
                _gg = None
                if not _gap_block:
                    try:
                        from analytics.earnings_gap_guard import block_stick_buy, session_gap_from_pos
                        from alpaca_broker import get_position as _gp_gap

                        _posg = _gp_gap(t)
                        _gg = session_gap_from_pos(_posg) if _posg else None
                        _gap_block = block_stick_buy(
                            dte=_epf.get("days_to"),
                            dse=_epf.get("days_since"),
                            hour=_epf.get("hour") or _epf.get("report_session"),
                            gap=_gg,
                        )
                        if _gap_block:
                            log.info(
                                "[FORTRESS] STICK ADD BLOCKED %s — print out or red gap=%.2f%% dte=%s",
                                t,
                                100 * float(_gg or 0),
                                _epf.get("days_to"),
                            )
                    except Exception:
                        _gap_block = False
                if not _gap_block:
                    try:
                        from analytics.event_ingenuity import block_add_on_peer_dump

                        if block_add_on_peer_dump(t, _gg):
                            _gap_block = True
                            log.info(
                                "[FORTRESS] STICK ADD BLOCKED %s — peer print dump this session",
                                t,
                            )
                    except Exception:
                        pass
                if (
                    _stick_force_on
                    and _stick_on
                    and not _gap_block
                    and float(p_entry) >= max(_stick_min, _dual_min)
                    and int(pred_entry) == 1
                    and scale > 0
                    and not hard_gate_block
                    and not jp_hard_skip
                    and _stick_dte <= _stick_max_dte
                ):
                    if soft_blocked:
                        log.info(
                            "[FORTRESS] FORCE STICK BUY %s — earnings stick p_adj=%.3f dte=%s "
                            "(vol/mtf only; jp/downpress/dual still apply)",
                            t,
                            float(p_adj),
                            _epf.get("days_to"),
                        )
                    want_buy = True
                    force_priority = True
                # Default OFF — force-buys + 1% TP was the main churn bleed.
                _pred_force_on = os.getenv("PRED_FORCE_BUY", "false").lower() in (
                    "1",
                    "true",
                    "yes",
                )
                _pred_min = float(os.getenv("PRED_FORCE_MIN_P", "0.60"))
                _force_syms = {
                    x.strip().upper()
                    for x in os.getenv("FORTRESS_FORCE_BUY_SYMBOLS", "").split(",")
                    if x.strip()
                }
                if (
                    not force_priority
                    and _pred_force_on
                    and scale > 0
                    and int(pred_entry) == 1
                    and float(p_entry) >= _pred_min
                    and (conf_ok or t.upper() in _force_syms)
                    and not hard_gate_block
                    and not jp_hard_skip
                ):
                    if soft_blocked:
                        log.info(
                            "[FORTRESS] FORCE PRED BUY %s — high-conviction UP p_adj=%.3f "
                            "(must size; hard risk/caps still apply)",
                            t,
                            float(p_adj),
                        )
                    want_buy = True
                    force_priority = True
                if (
                    not force_priority
                    and t.upper() in _force_syms
                    and int(pred_entry) == 1
                    and float(p_entry) >= _stick_min
                    and not hard_gate_block
                    and not jp_hard_skip
                ):
                    want_buy = True
                    force_priority = True
                    if soft_blocked:
                        log.info(
                            "[FORTRESS] FORCE WATCH BUY %s — on FORTRESS_FORCE_BUY_SYMBOLS p_adj=%.3f",
                            t,
                            float(p_adj),
                        )
            except Exception as e:
                log.debug("[FORTRESS] force-stick %s: %s", t, e)

            existing_mv, existing_gain = (0.0, None)
            if use_real and broker == "alpaca":
                existing_mv, existing_gain = position_snapshot(t)
                if (
                    want_sell
                    and existing_gain is not None
                    and float(existing_gain) > 0
                    and os.getenv("FORTRESS_SIGNAL_EXIT_LOSERS_ONLY", "true").lower()
                    in ("1", "true", "yes")
                ):
                    want_sell = False
                try:
                    from fortress_portfolio import issuer_position_snapshot

                    iss_mv, _ = issuer_position_snapshot(t)
                    if want_buy and existing_mv <= 0 and iss_mv > 1.0:
                        log.info(
                            "[FORTRESS] skip BUY %s — same issuer already held $%.0f (GOOG/GOOGL class)",
                            t,
                            iss_mv,
                        )
                        want_buy = False
                except Exception:
                    pass
            if want_sell and existing_mv > 0 and not _respect_min_hold(t):
                want_sell = False
            # Strong premarket lean: don't soft-signal-sell through the open (hard stops still fire).
            if want_sell and existing_mv > 0:
                try:
                    from analytics.premarket_protect import should_protect_premarket_long

                    protect, why_p = should_protect_premarket_long(t)
                    if protect:
                        want_sell = False
                        log.info("[FORTRESS] premarket-protect skip soft sell %s — %s", t, why_p)
                except Exception:
                    pass

            # Thesis death: multi-signal confirmed permanent damage — not one noisy bar.
            if (
                use_real
                and broker == "alpaca"
                and existing_mv > 0
                and existing_gain is not None
                and _respect_min_hold(t, allow_stop=True)
            ):
                try:
                    from analytics.conviction_exit import thesis_death_confirmed
                    from alpaca_broker import close_position_alpaca

                    _td_gap = None
                    try:
                        from analytics.earnings_gap_guard import session_gap_from_pos
                        from alpaca_broker import get_position as _gp_td

                        _td_gap = session_gap_from_pos(_gp_td(t))
                    except Exception:
                        _td_gap = None
                    dead, why = thesis_death_confirmed(
                        t,
                        p_adj=float(p_adj),
                        gain=float(existing_gain),
                        pred=int(pred),
                        session_gap=_td_gap,
                    )
                    if dead:
                        log.warning(
                            "[FORTRESS] THESIS_DEATH %s gain=%.3f%% p_adj=%.3f — %s",
                            t,
                            100 * float(existing_gain),
                            float(p_adj),
                            why,
                        )
                        # Don't thrash canceled overnight sells — queue until session can fill.
                        try:
                            from analytics.market_session import orders_allowed

                            _exit_ok, _exit_why = orders_allowed("sell")
                        except Exception:
                            _exit_ok, _exit_why = True, "ok"
                        if not _exit_ok:
                            log.info(
                                "[FORTRESS] THESIS_DEATH defer %s until session open (%s)",
                                t,
                                _exit_why,
                            )
                        elif close_position_alpaca(t, force=True):
                            rm.legs.pop(t, None)
                            rm.legs.pop(t.upper(), None)
                            existing_mv, existing_gain = (0.0, None)
                except Exception as e:
                    log.debug("[FORTRESS] thesis death %s: %s", t, e)

            exited = _maybe_exit_alpaca(
                t,
                px,
                use_real=use_real,
                broker=broker,
                rm=rm,
                p_adj=float(p_adj),
                pred=int(pred),
                signal_want_sell=bool(want_sell),
                better_candidate_waiting=bool(
                    existing_mv > 0
                    and float(existing_gain or 0) > 0
                    and os.getenv("FORTRESS_ROTATE_ON_PROFIT", "true").lower()
                    in ("1", "true", "yes")
                ),
            )
            if exited:
                existing_mv, existing_gain = (0.0, None)
                if use_real and broker == "alpaca":
                    portfolio_ctx = sync_risk_manager_from_alpaca(rm)

            if not want_buy:
                log.info(
                    "[FORTRESS] no-buy %s p_adj=%.3f p_entry=%.3f pred_entry=%d conf=%s news=%s",
                    t,
                    float(p_adj),
                    float(p_entry),
                    int(pred_entry),
                    conf_ok,
                    news_ok,
                )

            if want_buy and scale > 0:
                try:
                    from analytics.premarket_protect import premarket_entry_size_mult

                    _am = float(premarket_entry_size_mult(t, for_hft=False))
                    if _am <= 0:
                        log.info("[FORTRESS] skip BUY %s — morning pre-sweet bleed zone", t)
                        continue
                    if abs(_am - 1.0) > 1e-6:
                        scale *= _am
                        log.info("[FORTRESS] morning size mult %s ×%.2f (phase tilt)", t, _am)
                except Exception:
                    pass
                _ban = {
                    x.strip().upper()
                    for x in os.getenv(
                        "FORTRESS_BAN_INDEX_ETFS",
                        "SPY,QQQ,IWM,DIA,VOO,VTI,SOXX,XLK,XLF,XLE",
                    ).split(",")
                    if x.strip()
                }
                if t.upper() in _ban and os.getenv("FORTRESS_BAN_INDEX_BUYS", "true").lower() in (
                    "1",
                    "true",
                    "yes",
                ):
                    log.info("[FORTRESS] skip BUY %s — banned index ETF (no SPY/QQQ/IWM favorites)", t)
                    continue
                try:
                    from universe_lifecycle.corporate_actions import is_dead_money

                    if is_dead_money(t):
                        log.info("[FORTRESS] skip BUY %s — dead money (cash takeout / listing ended)", t)
                        continue
                except Exception:
                    pass
                if not buy_ok:
                    continue
                try:
                    from analytics.overnight_risk import block_new_buys_for_overnight

                    _blk, _blk_why = block_new_buys_for_overnight()
                    if _blk:
                        log.info("[FORTRESS] skip BUY %s — %s", t, _blk_why)
                        continue
                except Exception:
                    pass
                hf_boost = 0.0
                hf_meta: dict = {}
                try:
                    from analytics.hedge_fund_stack import hedge_fund_rank_boost

                    hf = hedge_fund_rank_boost(
                        t,
                        row=row,
                        closes=df["Close"],
                        bench_closes=bench_closes,
                        regime_score=regime_hf,
                        pair_closes_loader=_pair_closes_loader,
                    )
                    hf_boost = float(hf.boost)
                    hf_meta = {
                        "boost": hf_boost,
                        "momentum": hf.momentum,
                        "stat_arb": hf.stat_arb,
                        "etf": hf.etf_dislocation,
                        "trend": hf.trend,
                    }
                except Exception as e:
                    log.debug("[FORTRESS] hedge_fund_stack %s: %s", t, e)
                base_score = _buy_confidence_score(
                    p_adj=float(p_adj),
                    exec_c=float(exec_c),
                    sent=float(sent),
                    nf_f=float(nf_f),
                    top100=bool(top100),
                    hf_boost=hf_boost,
                    ticker=t,
                    row=row,
                    mom_5d=float(row.get("mom_20", row.get("mom_5d", 0.0)) or 0.0),
                    rs_spy=float(row.get("beta_proxy_60", 1.0) or 1.0),
                    hmm_market_score=float(regime_hf or 0.0),
                    closes=df["Close"] if "Close" in df.columns else None,
                    bench_closes=bench_closes,
                )
                try:
                    from analytics.chart_structure import chart_structure_score

                    base_score += float(os.getenv("FORTRESS_CHART_STRUCTURE_W", "1.0")) * chart_structure_score(row)
                except Exception:
                    pass
                # Modular pipeline: features→models→normalized signal (mathematical blend).
                if os.getenv("FORTRESS_USE_PIPELINE_ORCHESTRATE", "true").lower() in (
                    "1",
                    "true",
                    "yes",
                ):
                    try:
                        from analytics.pipeline_orchestrate import aggregate_signal, model_ready

                        if not model_ready(t):
                            base_score *= float(os.getenv("PIPELINE_UNREADY_SCORE_MULT", "0.80"))
                        else:
                            pipe_score, pipe_meta = aggregate_signal(
                                t,
                                p_up=float(p_adj),
                                exec_conf=float(exec_c),
                                sent=float(sent),
                                row=row,
                                closes=df["Close"] if "Close" in df.columns else None,
                                top100=bool(top100),
                            )
                            if not pipe_meta.get("fallback"):
                                w = float(os.getenv("PIPELINE_RANK_BLEND", "0.35"))
                                base_score = (1.0 - w) * float(base_score) + w * float(pipe_score)
                    except Exception as e:
                        log.debug("[FORTRESS] pipeline_orchestrate %s: %s", t, e)
                _ep_meta: dict = {}
                try:
                    from analytics.catalyst_horizon import enrich_earnings_plan, earnings_rank_boost
                    from intel.historical_events import holdings_earnings_plan

                    _ep = enrich_earnings_plan(
                        holdings_earnings_plan(t, is_holding=False),
                        sleeve="fortress",
                    )
                    _ep_meta = {
                        "days_to": _ep.get("days_to"),
                        "in_earnings_window": bool(_ep.get("near_event")),
                        "near_event": bool(_ep.get("near_event")),
                        "encourage_pre_momentum": bool(_ep.get("encourage_pre_momentum")),
                        "stick_to_prediction": bool(_ep.get("stick_to_prediction")),
                        "catalyst_horizon_fit": float(_ep.get("catalyst_horizon_fit") or 1.0),
                        "aligned_size_mult": float(_ep.get("aligned_size_mult") or 1.0),
                        "sleeve": "fortress",
                    }
                    if _ep.get("encourage_pre_momentum") or _ep.get("stick_to_prediction"):
                        _eb, _em = earnings_rank_boost(
                            days_to=_ep.get("days_to"),
                            p_adj=float(p_adj),
                            sleeve="fortress",
                            stick=True,
                        )
                        _eb = float(_em.get("applied") or _eb)
                        if _eb > 0:
                            base_score += _eb
                        if _em.get("force_ok"):
                            force_priority = True
                            log.info(
                                "[FORTRESS] earnings STICK %s +%.3f fit=%.2f (p_adj=%.3f dte=%s) → FORCE",
                                t,
                                _eb,
                                float(_ep.get("catalyst_horizon_fit") or 0),
                                float(p_adj),
                                _ep.get("days_to"),
                            )
                except Exception:
                    pass
                if force_priority:
                    _pfb = float(os.getenv("PRED_FORCE_SCORE_BOOST", "0.41"))
                    base_score += _pfb
                    log.info(
                        "[FORTRESS] FORCE priority score %s +%.2f (total=%.3f)",
                        t,
                        _pfb,
                        base_score,
                    )
                # Connect structure + bottom-fisher into fortress ranking (same flags as paper).
                if os.getenv("USE_STRUCTURE_PATTERNS", "true").lower() in ("1", "true", "yes"):
                    try:
                        from analytics.structure_patterns import structure_rank_boost

                        ohlc = df[["Open", "High", "Low", "Close"]].astype(float) if all(
                            c in df.columns for c in ("Open", "High", "Low", "Close")
                        ) else None
                        if ohlc is not None and len(ohlc) >= 10:
                            s_boost, _s_meta = structure_rank_boost(ohlc)
                            base_score += float(s_boost)
                    except Exception:
                        pass
                if os.getenv("USE_BOTTOM_FISHER", "true").lower() in ("1", "true", "yes"):
                    try:
                        from bottom_fisher.integrate import bottom_fisher_score_boost

                        bf_boost, _bf_meta = bottom_fisher_score_boost(t)
                        base_score += float(bf_boost or 0.0)
                    except Exception:
                        pass
                if os.getenv("USE_VALUE_INVESTING", "true").lower() in ("1", "true", "yes"):
                    try:
                        from analytics.value_investing import value_investing_rank_boost

                        v_boost, _v_meta = value_investing_rank_boost(t)
                        base_score += float(v_boost or 0.0)
                    except Exception:
                        pass
                if os.getenv("USE_INVESTING_BOOK", "true").lower() in ("1", "true", "yes"):
                    try:
                        from investing.integrate import book_rank_boost

                        b_boost, _b_meta = book_rank_boost(t)
                        base_score += float(b_boost or 0.0)
                    except Exception:
                        pass
                if os.getenv("USE_UNIQUE_PLAYBOOK", "true").lower() in ("1", "true", "yes"):
                    try:
                        from intel.unique_style_playbook import unique_rank_boost

                        u_boost, _u_meta = unique_rank_boost(
                            t, metrics={"p_up": float(p_up)}
                        )
                        base_score += float(u_boost or 0.0)
                    except Exception:
                        pass
                if os.getenv("USE_SHELDON_HEAD", "true").lower() in ("1", "true", "yes"):
                    try:
                        from analytics.sheldon_head import sheldon_rank_boost

                        s_boost, _s_meta = sheldon_rank_boost(t)
                        base_score += float(s_boost or 0.0)
                    except Exception:
                        pass
                try:
                    from analytics.water_theme import space_rank_boost, water_rank_boost

                    w_boost, w_meta = water_rank_boost(t, p_up=float(p_adj), sleeve="fortress")
                    if abs(w_boost) > 1e-6:
                        base_score += float(w_boost)
                        log.info(
                            "[FORTRESS] water-datacenter %s +%.3f role=%s q=%.2f",
                            t,
                            w_boost,
                            w_meta.get("role"),
                            float(w_meta.get("quality") or 0),
                        )
                    sp_boost, _sp_meta = space_rank_boost(t, p_up=float(p_adj), sleeve="fortress")
                    base_score += float(sp_boost or 0.0)
                except Exception:
                    pass
                _use_ha = os.getenv("USE_HIDDEN_PATTERN_ANOMALY", "true").lower() in ("1", "true", "yes")
                _use_mi = os.getenv("USE_MARKET_IMBALANCE", "true").lower() in ("1", "true", "yes")
                if _use_ha or _use_mi:
                    try:
                        from analytics.hidden_pattern_anomaly import hidden_anomaly_rank_boost

                        a_boost, _a_meta = hidden_anomaly_rank_boost(t)
                        base_score += float(a_boost or 0.0)
                    except Exception:
                        pass
                if os.getenv("USE_CROSS_COMPANY_LINKS", "true").lower() in ("1", "true", "yes"):
                    try:
                        from analytics.cross_company_links import cross_company_rank_boost

                        c_boost, _c_meta = cross_company_rank_boost(t)
                        base_score += float(c_boost or 0.0)
                    except Exception:
                        pass
                buy_candidates.append(
                    {
                        "ticker": t,
                        "p_up": float(p_up),
                        "p_adj": float(p_adj),
                        "p_entry": float(p_entry),
                        "exec_c": float(exec_c),
                        "sent": float(sent),
                        "nf_f": float(nf_f),
                        "top100": bool(top100),
                        "px": float(px),
                        "scale": float(scale),
                        "row": row,
                        "existing_mv": float(existing_mv),
                        "existing_gain": existing_gain,
                        "exited": bool(exited),
                        "score": base_score,
                        "hf_boost": hf_boost,
                        "hf_meta": hf_meta,
                        "jp_candle": candle_meta,
                        "force_priority": bool(force_priority),
                        "earnings_meta": _ep_meta,
                        "conviction": float(abs(float(p_adj) - 0.5) * 2.0),
                    }
                )
            # Signal sells are handled only by _maybe_exit_alpaca (conviction noise_hold
            # must not be bypassed by a second unconditional close).

            register_equity_snapshot(rm.equity)
            equity_curve.append(rm.equity)

        except Exception:
            log.exception("[FORTRESS] tick %s", t)

        scanned += 1
        if scanned % 10 == 0:
            log.info("[FORTRESS] scan progress %d/%d buy_candidates=%d", scanned, len(syms), len(buy_candidates))

        time.sleep(float(os.getenv("LIVE_SLEEP_SEC", "0.05")))

    log.info(
        "[FORTRESS] pass scan complete scanned=%d buy_candidates=%d top_buys=%d",
        scanned,
        len(buy_candidates),
        top_buys_per_pass,
    )

    # Execute only the strongest N buys for this pass.
    if halted:
        log.warning("[FORTRESS] skipping buys this pass — %s", halt_why or "halted")
        buy_candidates = []
    held_syms: frozenset[str] = frozenset()
    ranked: list = []
    risk_scale = 1.0
    if buy_candidates:
        try:
            from analytics.trade_rotation import (
                apply_letter_penalty,
                apply_score_penalty,
                in_cooldown,
                record_trade,
                select_diversified_buys,
            )

            if use_real and broker == "alpaca":
                try:
                    from alpaca_broker import list_positions

                    held_syms = frozenset(
                        str(p.get("symbol", "")).replace("/", "-").upper()
                        for p in list_positions()
                        if float(p.get("qty") or 0) > 0
                    )
                except Exception:
                    pass

            for c in buy_candidates:
                t = str(c["ticker"])
                base = float(c.get("score", c.get("p_adj", 0.0)))
                try:
                    from analytics.portfolio_slots import fortress_promote_boost, promoted_symbols

                    base += fortress_promote_boost(t)
                    if t.upper() in promoted_symbols():
                        c["day_trade_promoted"] = True
                except Exception:
                    pass
                base = apply_score_penalty(t, base)
                base = apply_letter_penalty(t, base, held=held_syms)
                c["score"] = base
                c["cooldown"] = in_cooldown(t)
            try:
                from analytics.horizon_picks import directional_conviction, horizon_independent

                if horizon_independent():
                    for c in buy_candidates:
                        conv = directional_conviction(float(c.get("p_entry", c.get("p_adj", 0.5))))
                        c["conviction"] = conv
                        # This sleeve's 1d conviction first; other rank extras as a small tie-break.
                        c["score"] = float(conv) * 2.0 + 0.20 * float(c.get("score") or 0.0)
            except Exception:
                pass
            if os.getenv("TRADE_COOLDOWN_SKIP_BUYS", "true").lower() in ("1", "true", "yes"):
                if weekend_hold_fill:
                    log.info("[FORTRESS] weekend fill — keep cooldown holds")
                else:
                    buy_candidates = [c for c in buy_candidates if not c.get("cooldown")]
        except Exception:
            pass
        ranked = select_diversified_buys(buy_candidates, top_buys_per_pass, held=held_syms)
        if weekend_hold_fill and buy_candidates and not ranked:
            ranked = list(buy_candidates)
            log.warning("[FORTRESS] weekend fill — diversify dropped holds, using all %d", len(ranked))
        risk_scale = 1.0
        if use_real and broker == "alpaca":
            try:
                from alpaca_broker import list_positions
                from analytics.hedge_fund_stack import portfolio_risk_overlay

                pos = [
                    {
                        "symbol": p.get("symbol"),
                        "market_value": float(p.get("market_value") or 0),
                    }
                    for p in list_positions()
                ]
                # Prefer live Alpaca multiplier so 4× BP books are not zeroed at ~100% of equity.
                try:
                    from alpaca_broker import get_account

                    _acct = get_account() or {}
                    _mult = float(_acct.get("multiplier") or 0) or None
                except Exception:
                    _mult = None
                if _mult is None:
                    try:
                        _mult = float(getattr(rm, "multiplier", 0) or 0) or None
                    except Exception:
                        _mult = None
                ro = portfolio_risk_overlay(pos, float(rm.equity), multiplier=_mult)
                risk_scale = float(ro.get("scale", 1.0))
                if ro.get("warnings"):
                    log.info("[FORTRESS] risk overlay scale=%.2f %s", risk_scale, ro.get("warnings"))
            except Exception as e:
                log.debug("[FORTRESS] risk overlay: %s", e)

        # Leave working DAY buys on the book so fills can cross minutes.
        # Default: do not cancel offlist (cancel→same-ticket reissue). Opt-in sweeper
        # still keeps held names + resting buys in `keep`.
        if use_real and broker == "alpaca" and ranked:
            try:
                from alpaca_broker import cancel_buys_outside_keep, open_buy_orders

                keep = {str(c.get("ticker") or "").upper() for c in ranked if c.get("ticker")}
                keep |= {str(s).upper() for s in held_syms if s}
                try:
                    keep |= {
                        str(o.get("symbol") or "").replace("/", "-").upper()
                        for o in open_buy_orders()
                        if o.get("symbol")
                    }
                except Exception:
                    pass
                n_cancel = cancel_buys_outside_keep(keep, skip_hft=True)
                if n_cancel:
                    log.info("[FORTRESS] cancelled %d offlist buy(s); ranked working orders ride", n_cancel)
                    portfolio_ctx = sync_risk_manager_from_alpaca(rm)
            except Exception as e:
                log.debug("[FORTRESS] cancel offlist buys: %s", e)

        # Soft rotate: trim held index ETFs only when FORCE singles need cash (never wipe overnight book).
        if use_real and broker == "alpaca" and ranked:
            try:
                from fortress_portfolio import maybe_trim_index_etfs_for_force

                force_need = sum(
                    1
                    for c in ranked
                    if c.get("force_priority")
                    and float(c.get("existing_mv") or 0) <= 0
                )
                if force_need > 0:
                    trimmed = maybe_trim_index_etfs_for_force(
                        force_count=force_need,
                        equity=float(rm.equity or 0),
                    )
                    if trimmed:
                        portfolio_ctx = sync_risk_manager_from_alpaca(rm)
            except Exception as e:
                log.debug("[FORTRESS] index soft-trim: %s", e)

    # Cross-sectional vectorized sizing — deploy full equity target across ranked names
    # that still have room under the single-name equity cap (skip capped / ADD_ON-blocked).
    vec_notionals: dict[str, float] = {}
    for c in buy_candidates:
        n_we = float(c.get("weekend_idle_n") or 0)
        if n_we > 0:
            tu = str(c.get("ticker") or "").replace("/", "-").upper()
            if tu:
                vec_notionals[tu] = n_we
    use_vec = os.getenv("FORTRESS_USE_VECTORIZED_WEIGHTS", "true").lower() in (
        "1",
        "true",
        "yes",
    )
    if weekend_hold_fill and vec_notionals:
        use_vec = False
    if use_vec:
        try:
            from analytics.rank_pipeline import vectorized_target_weights
            from fortress_portfolio import deploy_budget_usd, idle_cash_fill_active

            if use_real and broker == "alpaca":
                portfolio_ctx = sync_risk_manager_from_alpaca(rm)
            ctx = portfolio_ctx or {
                "equity": rm.equity,
                "deployed_frac": 0.0,
                "buying_power": rm.equity,
                "gross_mv": 0.0,
                "multiplier": 1.0,
            }
            bud = deploy_budget_usd(ctx)
            eq = float(bud["equity"])
            budget = float(bud["budget"])
            max_single_usd = float(bud["max_single_usd"])
            allow_addon = os.getenv("FORTRESS_ALLOW_ADD_ON", "false").lower() in (
                "1",
                "true",
                "yes",
            )
            allow_dca = os.getenv("FORTRESS_ALLOW_DCA", "false").lower() in (
                "1",
                "true",
                "yes",
            )
            fill_idle = idle_cash_fill_active(ctx)
            min_n = float(os.getenv("MIN_ORDER_NOTIONAL", "100"))
            # Eligible = has equity-cap room and (new name OR add-on/DCA/idle-cash fill).
            eligible_idx: list[int] = []
            rooms: list[float] = []
            scores: list[float] = []
            for i, c in enumerate(ranked):
                held_mv = float(c.get("existing_mv") or 0.0)
                room_cap = max_single_usd
                try:
                    from crypto_universe import is_crypto_symbol
                    from analytics.crypto_alloc import crypto_single_cap_usd

                    if is_crypto_symbol(str(c.get("ticker") or "")):
                        room_cap = crypto_single_cap_usd(eq)
                except Exception:
                    pass
                room = max(0.0, room_cap - held_mv)
                if held_mv > 0 and not (allow_addon or allow_dca or fill_idle):
                    room = 0.0
                try:
                    gain = c.get("existing_gain")
                    from analytics.buying_power import hold_is_green

                    if held_mv > 0 and not hold_is_green(None if gain is None else float(gain)):
                        continue
                except (TypeError, ValueError):
                    pass
                if room < min_n:
                    continue
                eligible_idx.append(i)
                rooms.append(room)
                scores.append(float(c.get("score") or 0.0))
            # max_weight = fraction of leftover budget so one name can take the
            # equity single-cap, not 10% of leftover (that left cash idle).
            max_w = min(1.0, max_single_usd / max(budget, 1.0)) if budget > 0 else 1.0
            temp = float(os.getenv("FORTRESS_WEIGHT_TEMPERATURE", "1.0"))
            raw = (
                vectorized_target_weights(
                    scores,
                    total_capital=budget,
                    max_weight=max_w,
                    min_score=float(os.getenv("FORTRESS_VEC_MIN_SCORE", "0") or 0),
                    temperature=temp,
                )
                if eligible_idx and budget > 0
                else []
            )
            go_live_cap = float(os.getenv("FORTRESS_GO_LIVE_MAX_NOTIONAL", "0") or 0)
            hard_max = float(os.getenv("HARD_MAX_ORDER_NOTIONAL", "0") or 0)
            if hard_max <= 0 and go_live_cap <= 0:
                hard_max = 0.0  # calculator / equity single-cap is the clamp
            elif hard_max <= 0:
                hard_max = float(os.getenv("MAX_ORDER_NOTIONAL", "0") or 0)
            leftover = 0.0
            for j, idx in enumerate(eligible_idx):
                c = ranked[idx]
                n = float(raw[j]) * risk_scale if j < len(raw) else 0.0
                if os.getenv("USE_UNIQUE_PLAYBOOK", "true").lower() in ("1", "true", "yes"):
                    try:
                        from intel.unique_style_playbook import fortress_size_mult_from_playbook

                        n *= float(
                            fortress_size_mult_from_playbook(
                                {
                                    "p_up": float(c.get("p_up") or 0.5),
                                    **(c.get("earnings_meta") or {}),
                                }
                            )
                        )
                        # Max-equity when conviction + catalyst fit + calm risk
                        try:
                            from analytics.catalyst_horizon import max_equity_size_mult

                            _em = c.get("earnings_meta") or {}
                            n *= float(
                                max_equity_size_mult(
                                    p_adj=float(c.get("p_adj") or 0.5),
                                    exec_conf=float(c.get("exec_c") or 0.55),
                                    force_priority=bool(c.get("force_priority")),
                                    catalyst_fit=float(_em.get("catalyst_horizon_fit") or 1.0),
                                )
                            )
                        except Exception:
                            pass
                    except Exception:
                        pass
                if go_live_cap > 0:
                    n = min(n, go_live_cap)
                if hard_max > 0:
                    n = min(n, hard_max)
                room = rooms[j]
                if n > room:
                    leftover += n - room
                    n = room
                if n >= min_n:
                    vec_notionals[str(c["ticker"])] = n
                else:
                    leftover += max(0.0, n)
            # Sweep residual — still clipped to per-name equity cap AND hard_max.
            if leftover >= min_n and eligible_idx:
                for j, idx in enumerate(eligible_idx):
                    if leftover < min_n:
                        break
                    c = ranked[idx]
                    t = str(c["ticker"])
                    cur = float(vec_notionals.get(t) or 0.0)
                    room_left = max(0.0, rooms[j] - cur)
                    if hard_max > 0:
                        room_left = min(room_left, max(0.0, hard_max - cur))
                    if go_live_cap > 0:
                        room_left = min(room_left, max(0.0, go_live_cap - cur))
                    if room_left < min_n:
                        continue
                    add = min(leftover, room_left)
                    vec_notionals[t] = cur + add
                    leftover -= add
            allocated = sum(vec_notionals.values())
            idle_left = max(float(leftover), max(0.0, float(budget) - allocated))
            if idle_left >= min_n and idle_cash_fill_active(ctx):
                leftover = idle_left
                try:
                    from alpaca_broker import list_positions as _lp_idle
                    from fortress_portfolio import allocate_idle_cash_split

                    _ban = {
                        x.strip().upper()
                        for x in os.getenv(
                            "FORTRESS_BAN_INDEX_ETFS",
                            "SPY,QQQ,IWM,DIA,VOO,VTI,SOXX,XLK,XLF,XLE",
                        ).split(",")
                        if x.strip()
                    }
                    pos_idle = _lp_idle() or []
                    extra = allocate_idle_cash_split(
                        leftover,
                        positions=pos_idle,
                        equity=eq,
                        max_single_usd=max_single_usd,
                        min_n=min_n,
                        hard_max=hard_max if hard_max > 0 else go_live_cap,
                        already=vec_notionals,
                        banned=_ban,
                    )
                    scored = {
                        str(c.get("ticker") or "").upper()
                        for c in ranked
                        if float(c.get("score") or 0) > 0
                    }
                    held = set()
                    for p in pos_idle:
                        try:
                            if float(p.get("qty") or 0) <= 0:
                                continue
                        except (TypeError, ValueError):
                            continue
                        held.add(str(p.get("symbol") or "").replace("/", "-").upper())
                    kept_idle = 0.0
                    for t, n_add in extra.items():
                        tu = str(t).upper()
                        # Winners already in the book may take idle cash even if this
                        # pass did not re-score them. Skip only *new* zero-score dumps.
                        if tu not in scored and tu not in held:
                            log.info(
                                "[FORTRESS] idle skip %s $%.0f — no scored edge this pass",
                                tu,
                                float(n_add),
                            )
                            continue
                        vec_notionals[tu] = float(vec_notionals.get(tu) or 0.0) + float(n_add)
                        leftover -= float(n_add)
                        kept_idle += float(n_add)
                    if kept_idle > 0:
                        log.info(
                            "[FORTRESS] idle-cash fill scored names $%.0f (leftover now $%.0f)",
                            kept_idle,
                            leftover,
                        )
                except Exception as e:
                    log.warning("[FORTRESS] idle-cash hold fill: %s", e)
            log.info(
                "[FORTRESS] vectorized_target_weights budget=$%.0f eligible=%d/%d "
                "allocated=$%.0f leftover=$%.0f (deployed=$%.0f / target=$%.0f "
                "capacity=$%.0f bp=$%.0f max_single=$%.0f max_w=%.2f)",
                budget,
                len(eligible_idx),
                len(ranked),
                sum(vec_notionals.values()),
                leftover,
                bud["gross_mv"],
                bud["target_usd"],
                bud.get("total_capacity", bud["target_base"]),
                bud.get("buying_power", 0.0),
                max_single_usd,
                max_w,
            )
        except Exception as e:
            log.warning("[FORTRESS] vectorized weights failed — falling back to per-name sizing: %s", e)
            vec_notionals = {}

    if scanned <= 0:
        held_syms: set[str] = set()
        try:
            from alpaca_broker import list_positions as _lp_drop

            for p in _lp_drop() or []:
                try:
                    if float(p.get("qty") or 0) <= 0:
                        continue
                except (TypeError, ValueError):
                    continue
                held_syms.add(str(p.get("symbol") or "").replace("/", "-").upper())
        except Exception:
            pass
        if ranked or vec_notionals:
            log.warning(
                "[FORTRESS] keep held idle fills — scan scored 0 ticks (ranked=%d sized=%d held=%d)",
                len(ranked),
                len(vec_notionals),
                len(held_syms),
            )
        ranked = [
            c
            for c in ranked
            if str(c.get("ticker") or "").replace("/", "-").upper() in held_syms
        ]
        vec_notionals = {
            k: v
            for k, v in vec_notionals.items()
            if str(k).replace("/", "-").upper() in held_syms
        }

    try:
        from alpaca_broker import cancel_extra_working_buys

        n_dup = cancel_extra_working_buys()
        if n_dup:
            log.info("[FORTRESS] cancelled %d extra working buys (keep one per symbol)", n_dup)
    except Exception as e:
        log.debug("[FORTRESS] extra-buy sweep: %s", e)

    for rank, cand in enumerate(ranked, 1):
        t = str(cand["ticker"])
        px = float(cand["px"])
        existing_mv = float(cand["existing_mv"])
        allow_addon = os.getenv("FORTRESS_ALLOW_ADD_ON", "false").lower() in ("1", "true", "yes")
        allow_dca = os.getenv("FORTRESS_ALLOW_DCA", "false").lower() in ("1", "true", "yes")
        fill_idle = False
        try:
            from fortress_portfolio import idle_cash_fill_active as _idle_buy

            fill_idle = _idle_buy(portfolio_ctx)
        except Exception:
            fill_idle = False
        # Held names can still absorb idle cash up to the equity single-name cap.
        if existing_mv > 0 and not (allow_addon or allow_dca or fill_idle):
            log.info(
                "[FORTRESS] skip BUY %s — already held $%.0f (ADD_ON/DCA off)",
                t,
                existing_mv,
            )
            continue
        try:
            if float(cand.get("score") or 0) <= 0 and not cand.get("force_priority"):
                log.info(
                    "[FORTRESS] skip BUY %s — no rank score (refuse dummy p=0.55 cash dump)",
                    t,
                )
                continue
        except (TypeError, ValueError):
            continue
        try:
            from analytics.buying_power import hold_is_green as _hold_green

            _g_hold = cand.get("existing_gain")
            if existing_mv > 0 and not _hold_green(None if _g_hold is None else float(_g_hold)):
                log.info("[FORTRESS] skip BUY %s — not green (cut, do not add)", t)
                continue
        except (TypeError, ValueError):
            pass
        if use_real and broker == "alpaca":
            portfolio_ctx = sync_risk_manager_from_alpaca(rm)
        max_pos = int(float(os.getenv("FORTRESS_MAX_POSITIONS", "0") or 0))
        if max_pos <= 0 or max_pos > 80:
            try:
                from analytics.buying_power import sizing_slots

                max_pos = max(40, sizing_slots())
            except Exception:
                max_pos = 40
        pos_n = int((portfolio_ctx or {}).get("position_count") or 0)
        if existing_mv <= 0 and pos_n >= max_pos:
            log.info("[FORTRESS] skip BUY %s — at max positions (%d/%d)", t, pos_n, max_pos)
            continue
        if existing_mv <= 0:
            try:
                from analytics.portfolio_slots import can_open_head

                ok_slot, slot_reason = can_open_head("fortress", t)
                if not ok_slot:
                    log.info("[FORTRESS] skip BUY %s — %s", t, slot_reason)
                    continue
            except Exception:
                pass
        if t in vec_notionals:
            notional = float(vec_notionals[t])
        else:
            notional = fortress_order_notional(
                ticker=t,
                p_adj=float(cand["p_adj"]),
                scale=float(cand["scale"]),
                portfolio=portfolio_ctx or {"equity": rm.equity, "deployed_frac": 0.0, "buying_power": rm.equity},
                existing_mv=existing_mv,
                existing_gain=cand["existing_gain"],
            )
            rank_mult = max(
                0.60,
                float(os.getenv("FORTRESS_TOP_RANK_MULT_BASE", "1.25"))
                - (rank - 1) * float(os.getenv("FORTRESS_TOP_RANK_MULT_STEP", "0.07")),
            )
            notional *= rank_mult * risk_scale
        try:
            from crypto_universe import is_crypto_symbol
            from analytics.crypto_alloc import position_crypto_mv, size_crypto_notional

            if is_crypto_symbol(t):
                notional = size_crypto_notional(
                    float(notional),
                    equity=float((portfolio_ctx or {}).get("equity") or rm.equity),
                    cash=float((portfolio_ctx or {}).get("cash") or 0.0),
                    crypto_mv=position_crypto_mv((portfolio_ctx or {}).get("positions") or []),
                )
        except Exception:
            pass
        if os.getenv("AGI_CUSTOM_HOOKS_ENABLED", "true").lower() in ("1", "true", "yes"):
            try:
                from self_modify.custom_hooks import fortress_size_mult

                hook_ctx = dict(portfolio_ctx or {})
                hook_ctx.setdefault("deployed_frac", hook_ctx.get("deployed_frac", 0.0))
                notional *= float(fortress_size_mult(hook_ctx))
            except Exception:
                pass
        # Per-name cap = fraction of EQUITY (not 4x BP) — stops 96% QQQ books.
        eq_cap = float(rm.equity or (portfolio_ctx or {}).get("equity") or 100_000.0)
        use_bp_cap = os.getenv("FORTRESS_EXPOSURE_USE_BP", "true").lower() in (
            "1",
            "true",
            "yes",
        )
        single_use_eq = os.getenv("FORTRESS_SINGLE_CAP_USE_EQUITY", "true").lower() in (
            "1",
            "true",
            "yes",
        )
        _mult = float((portfolio_ctx or {}).get("multiplier") or 0.0)
        _capacity = eq_cap * _mult if _mult > 1.0 else max(
            eq_cap, float((portfolio_ctx or {}).get("buying_power") or eq_cap)
        )
        size_base = eq_cap if single_use_eq else (_capacity if use_bp_cap else eq_cap)
        max_single_frac = min(
            float(os.getenv("FORTRESS_MAX_SINGLE_FRAC", "0.09")),
            float(os.getenv("MAX_SINGLE_ASSET_FRAC", "0.12")),
        )
        max_single_usd = size_base * max_single_frac * 0.995
        try:
            from crypto_universe import is_crypto_symbol
            from analytics.crypto_alloc import crypto_single_cap_usd

            if is_crypto_symbol(t):
                max_single_usd = crypto_single_cap_usd(eq_cap)
        except Exception:
            pass
        hard_max_exec = float(os.getenv("HARD_MAX_ORDER_NOTIONAL", "0") or 0)
        if hard_max_exec <= 0:
            hard_max_exec = 0.0  # last-wins 0 = single-name equity cap only
        held_mv = existing_mv
        notional = min(notional, max(0.0, max_single_usd - held_mv))
        if hard_max_exec > 0:
            notional = min(notional, hard_max_exec)
        cash = float((portfolio_ctx or {}).get("cash") or 0.0)
        if os.getenv("FORTRESS_BLOCK_NEG_CASH_BUYS", "true").lower() in ("1", "true", "yes"):
            if cash < float(os.getenv("FORTRESS_MIN_CASH_TO_BUY", "250") or 250):
                log.info("[FORTRESS] skip BUY %s — cash $%.0f (margin bleed guard)", t, cash)
                continue
        if notional <= 0:
            log.info("[FORTRESS] skip BUY %s — single-name cap $%.0f (held $%.0f)", t, max_single_usd, held_mv)
            continue
        # Never open a 2nd clip into mega index ETFs if already in book (anti-same-stock).
        _index = {
            x.strip().upper()
            for x in os.getenv(
                "FORTRESS_NO_REBUY_SYMBOLS",
                "SPY,QQQ,IWM,DIA,VOO,VTI,SOXX,XLK,XLF,XLE",
            ).split(",")
            if x.strip()
        }
        if t.upper() in _index and held_mv > 0:
            log.info("[FORTRESS] skip BUY %s — index ETF already held (no rebuy)", t)
            continue
        # Belt-and-suspenders: ban again at execute (whitelist mistakes must not buy).
        _ban_exec = {
            x.strip().upper()
            for x in os.getenv(
                "FORTRESS_BAN_INDEX_ETFS",
                "SPY,QQQ,IWM,DIA,VOO,VTI,SOXX,XLK,XLF,XLE",
            ).split(",")
            if x.strip()
        }
        if t.upper() in _ban_exec and os.getenv("FORTRESS_BAN_INDEX_BUYS", "true").lower() in (
            "1",
            "true",
            "yes",
        ):
            log.info("[FORTRESS] skip BUY %s — banned index ETF at execute", t)
            continue
        try:
            from analytics.quant_risk import estimate_slippage_bps

            slip = estimate_slippage_bps(
                mid=px,
                notional=float(notional),
                vol_frac=float(cand.get("volatility") or cand.get("vol") or 0.02),
            )
            if not slip.ok and os.getenv("FORTRESS_SKIP_HIGH_SLIPPAGE", "true").lower() in (
                "1",
                "true",
                "yes",
            ):
                log.info(
                    "[FORTRESS] skip BUY %s — %s (%.1f bps)",
                    t,
                    slip.reason,
                    slip.expected_bps,
                )
                continue
            if slip.expected_bps >= float(os.getenv("SLIPPAGE_AUDIT_WARN_BPS", "25") or 25):
                log.info("[FORTRESS] slippage est %s ≈ %.1f bps", t, slip.expected_bps)
        except Exception:
            pass
        shares = float(notional) / max(px, 1e-9)
        if shares < 1.0 and use_real and broker == "ibkr":
            log.info(
                "[FORTRESS] skip BUY %s — notional $%.0f < 1 share @ $%.2f",
                t,
                notional,
                px,
            )
            continue
        qty = max(1, int(shares)) if shares >= 1.0 else max(shares, 1e-6)
        row = cand.get("row")
        atr = px * 0.02
        if row is not None:
            try:
                atr = float(row.get("atr_14", atr) or atr)
            except Exception:
                pass
        stop = px - float(atr) * float(os.getenv("ATR_STOP_MULT", "1.5")) * regime.stop_widen
        # Pre-trade concentration uses live equity (single-name % of equity).
        # Available capital / BP is enforced by sizing + Alpaca, not by faking equity=BP.
        cap_eq = float(rm.equity or (portfolio_ctx or {}).get("equity") or 0.0)
        c = pretrade_check(
            t,
            "BUY",
            qty=float(qty),
            notional=float(notional),
            is_short=False,
            equity=cap_eq,
        )
        if not c.ok:
            log.warning("[FORTRESS] compliance block BUY %s: %s", t, c.reason)
            continue
        if not can_add_position(rm, t, notional, px, stop, existing_mv):
            continue
        tag = f"BUY#{rank}" if existing_mv <= 0 else f"DCA#{rank}"
        _p_up = float(cand.get("p_up") or cand.get("p_adj") or 0.55)
        _p_adj = float(cand.get("p_adj") or _p_up)
        log.info(
            "[FORTRESS] %s %s $%.0f (~%.2f sh) p=%.3f adj=%.3f score=%.3f%s",
            tag,
            t,
            notional,
            float(qty),
            _p_up,
            _p_adj,
            float(cand.get("score") or 0.0),
            " [vec]" if t in vec_notionals else "",
        )
        order_ok = False
        if use_real and broker == "ibkr" and ib is not None:
            from execution_handler import place_limit_mid

            with lat.track("order_route"):
                place_limit_mid(ib, t, int(qty), "BUY", wait_sec=25.0, repost_sec=25.0)
            order_ok = True
        elif use_real and broker == "alpaca":
            trade_c: dict = {}
            try:
                from intel.algo_risk_filter import build_trade_constraints_from_risk, screen_buy_risk
                from intel.trade_constraints import save_constraints

                risk = screen_buy_risk(
                    t,
                    hold_days=int(os.getenv("FORTRESS_HOLD_DAYS", os.getenv("HOLD_DAYS_DEFAULT", "1"))),
                )
                trade_c = build_trade_constraints_from_risk(risk)
                if risk.get("warnings"):
                    for w in risk["warnings"]:
                        log.warning("[FORTRESS] %s", w)
                save_constraints(t, {**trade_c, "opened_at_utc": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()})
            except Exception as e:
                log.debug("[FORTRESS] trade constraints %s: %s", t, e)

            with lat.track("order_route"):
                try:
                    from alpaca_broker import pending_buy_order

                    if pending_buy_order(t):
                        log.info("[FORTRESS] skip BUY %s — duplicate open buy order", t)
                        continue
                    try:
                        from analytics.order_fingerprint import recently_cancelled, recently_submitted

                        if recently_cancelled(t, side="buy"):
                            log.info("[FORTRESS] skip BUY %s — same ticket was just cancelled", t)
                            continue
                        if recently_submitted(t, side="buy"):
                            log.info("[FORTRESS] skip BUY %s — buy just submitted", t)
                            continue
                    except Exception:
                        pass
                    if os.getenv("USE_IS_ZERO_EXEC", "false").lower() in ("1", "true", "yes"):
                        from alpaca_broker import place_is_zero_alpaca

                        order_ok = bool(
                            place_is_zero_alpaca(
                                t,
                                target_notional=notional,
                                action="BUY",
                                volatility=float(row.get("volatility", 0.02)),
                                volume_ratio=float(row.get("volume_ratio", 1.0)),
                            )
                        )
                    else:
                        from alpaca_broker import place_smart_buy_alpaca

                        order_ok = bool(
                            place_smart_buy_alpaca(
                                t,
                                notional,
                                constraints=trade_c,
                                fallback_px=float(px),
                            )
                        )
                except Exception as e:
                    log.warning("[FORTRESS] order failed %s: %s", t, e)
                    continue
            if not order_ok:
                log.warning("[FORTRESS] BUY not submitted %s — skipping leg/journal", t)
                continue
            try:
                from analytics.hidden_pattern_learn import snapshot_entry_pattern

                snapshot_entry_pattern(t, side="LONG")
            except Exception:
                pass
            try:
                from analytics.trade_rotation import record_trade

                record_trade(t, side="BUY", source="fortress")
            except Exception:
                pass
            try:
                from analytics.portfolio_slots import clear_promotion, register_symbol

                register_symbol(t, "fortress", qty=float(qty))
                if cand.get("day_trade_promoted"):
                    clear_promotion(t)
            except Exception:
                pass
            if cand.get("jp_candle"):
                try:
                    from analytics.jp_candle_rl import record_signal

                    jm = cand["jp_candle"]
                    record_signal(
                        t,
                        pattern=str(jm.get("pattern") or jm.get("effective_pattern") or "NONE"),
                        bias=int(jm.get("composite_bias") or jm.get("bias") or 0),
                        composite_bias=int(jm.get("composite_bias") or 0),
                        p_adj=float(cand["p_adj"]),
                    )
                except Exception:
                    pass
        elif not use_real:
            order_ok = True  # paper/dry track still books the sim leg
        if not order_ok:
            continue
        if existing_mv <= 0:
            rm.register_open(t, notional, px, stop)
        else:
            rm.legs[t] = OpenLeg(symbol=t, notional=existing_mv + notional, entry=px, stop=stop)
        log_trade(
            t,
            "BUY",
            qty,
            float(px),
            float(px),
            0.0,
            0.0,
            regime.name.value,
            regime.vix,
            float(cand.get("p_entry") or cand.get("p_up") or cand.get("p_adj") or 0.55),
            float(cand.get("sent") or 0.0),
            "fortress p_up=%s p_entry=%s exec=%s" % (
                cand.get("p_up"),
                cand.get("p_entry"),
                cand.get("exec_c"),
            ),
        )
        try:
            from trade_journal import log_decision

            log_decision(
                {
                    "symbol": t,
                    "side": "BUY",
                    "source": "fortress",
                    "notional": notional,
                    "px": px,
                    "p_up": cand.get("p_up"),
                    "p_entry": cand.get("p_entry"),
                    "p_adj": cand.get("p_adj"),
                    "exec_c": cand.get("exec_c"),
                    "score": cand.get("score"),
                    "sent": cand.get("sent"),
                    "order_ok": True,
                }
            )
        except Exception:
            pass

    if len(equity_curve) > 3:
        print_equity_panel("Fortress (paper track)", equity_curve)
    log.info("[FORTRESS] latency %s", lat.summary())
    if p_hist:
        hit_proxy = sum(1 for p in p_hist if p >= min_p) / max(len(p_hist), 1)
        sharpe_proxy = (sum(p_hist) / max(len(p_hist), 1)) - 0.5
        peak = max(equity_curve) if equity_curve else rm.equity
        drawdown = (rm.equity - peak) / peak if peak > 0 else 0.0
        deployed = float((portfolio_ctx or {}).get("deployed_frac") or 0.0)
        adapt = policy.observe_and_maybe_adapt(
            {
                "hit_rate": float(hit_proxy),
                "drawdown": float(drawdown),
                "sharpe_proxy": float(sharpe_proxy),
                "deployed_frac": float(deployed),
            }
        )
        if adapt.get("applied"):
            log.info("[FORTRESS] policy adapted %s", adapt.get("accepted"))

    if ib is not None and ib.isConnected():
        ib.disconnect()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-symbols", type=int, default=int(os.getenv("MAX_LIVE_SYMBOLS", "500")))
    ap.add_argument(
        "--shuffle",
        action=argparse.BooleanOptionalAction,
        default=os.getenv("FORTRESS_SHUFFLE", "true").lower() in ("1", "true", "yes"),
    )
    args = ap.parse_args()
    br = os.getenv("BROKER", "alpaca").strip().lower()
    if br == "ibkr":
        log.info(
            "[FORTRESS] broker=ibkr %s:%s min_conf=%.2f",
            IBKR_HOST,
            IBKR_PORT,
            float(os.getenv("MIN_MODEL_CONFIDENCE", "0.95")),
        )
    else:
        base = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
        log.info(
            "[FORTRESS] broker=alpaca base=%s min_conf=%.2f gate=%s relax=%s",
            base.rstrip("/"),
            float(get_runtime_param("MIN_MODEL_CONFIDENCE", float(os.getenv("MIN_MODEL_CONFIDENCE", "0.95")))),
            os.getenv("CONFIDENCE_GATE_MODE", "exec_only"),
            os.getenv("FORTRESS_RELAX_GATES", "false"),
        )
    hz = os.getenv("FORTRESS_PREDICT_HORIZON", "").strip()
    if hz:
        log.info(
            "[FORTRESS] FORTRESS_PREDICT_HORIZON=%s (uses that head from each bundle when present)",
            hz,
        )
    run_fortress_pass(args)


if __name__ == "__main__":
    main()
