"""Yahoo-candle day trading — top-100 scan, RL-ranked top-3 entries, mandatory cash-out."""

from __future__ import annotations

import json
import os
from dataclasses import replace as _dc_replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from analytics.day_trade_rank import RankedPick, rank_scan
from analytics.day_trade_risk import (
    RiskDecision,
    check_daily_limits,
    ensure_session_anchor,
    size_position,
    trading_halted,
)
from analytics.day_trade_setups import SetupScan, scan_setups
from analytics.day_trade_yahoo import fetch_yahoo_bars, persist_bars, session_vwap
from analytics.jp_candle_rl import record_outcome, record_signal
from utils import log

ROOT = Path(__file__).resolve().parents[1]
SIGNAL_PATH = ROOT / "data" / "intel" / "day_trade_signals.json"
RANK_PATH = ROOT / "data" / "intel" / "day_trade_rankings.json"
ENTRY_PATH = ROOT / "data" / "intel" / "day_trade_entries.json"
ROTATE_PATH = ROOT / "data" / "intel" / "day_trade_rotate.json"


def _min_entry_score() -> float:
    return float(os.getenv("DAY_TRADE_MIN_SCORE", "0.38"))


def _min_exit_score() -> float:
    return float(os.getenv("DAY_TRADE_EXIT_SCORE", "-0.28"))


def _top_picks() -> int:
    return max(1, int(os.getenv("DAY_TRADE_TOP_PICKS", "3")))


def _max_concurrent() -> int:
    return max(1, int(os.getenv("DAY_TRADE_MAX_CONCURRENT", "3")))


def _load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _load_entries() -> dict[str, dict]:
    return _load_json(ENTRY_PATH).get("legs") or {}


def _save_entry(ticker: str, *, entry_px: float, target_px: float, stop_px: float, pattern: str) -> None:
    legs = _load_entries()
    legs[ticker.upper()] = {
        "entry_px": entry_px,
        "target_px": target_px,
        "stop_px": stop_px,
        "pattern": pattern,
        "opened_utc": datetime.now(timezone.utc).isoformat(),
    }
    _save_json(ENTRY_PATH, {"legs": legs})


def _clear_entry(ticker: str) -> None:
    legs = _load_entries()
    legs.pop(ticker.upper(), None)
    _save_json(ENTRY_PATH, {"legs": legs})


def _account_equity() -> float:
    from alpaca_broker import get_account

    return float((get_account() or {}).get("equity") or 0)


def _all_positions() -> list[dict]:
    from alpaca_broker import list_positions

    return [p for p in list_positions() if abs(float(p.get("qty") or 0)) > 0]


def _position(ticker: str) -> dict | None:
    sym = ticker.upper()
    for p in _all_positions():
        if str(p.get("symbol", "")).upper() == sym:
            return p
    return None


def analyze(ticker: str) -> SetupScan | None:
    df = fetch_yahoo_bars(ticker)
    if df is None or df.empty or len(df) < 10:
        return None
    persist_bars(ticker, df)
    return scan_setups(ticker, df, vwap=session_vwap(df))


def _update_rankings(pick: RankedPick) -> None:
    doc = _load_json(RANK_PATH)
    ranks = doc.get("ranks") or {}
    ranks[pick.ticker] = {**pick.to_dict(), "updated_utc": datetime.now(timezone.utc).isoformat()}
    doc["ranks"] = ranks
    doc["updated_utc"] = datetime.now(timezone.utc).isoformat()
    _save_json(RANK_PATH, doc)


def should_enter(pick: RankedPick) -> bool:
    scan = pick.scan
    min_sc = _min_entry_score()
    try:
        from intel.morning_club_intel import load_latest, morning_club_boost_for

        cb = morning_club_boost_for(pick.ticker)
        info = (load_latest().get("tickers") or {}).get(pick.ticker.upper()) or {}
        if info.get("catalyst") == "earnings" or cb >= 0.45:
            min_sc = max(0.28, min_sc - float(os.getenv("DAY_TRADE_CLUB_SCORE_RELAX", "0.08")))
    except Exception:
        pass
    # Daily Cramer tilt (day-trade sleeve weight — never HFT)
    try:
        from intel.cramer_picks import cramer_boost_for

        cw = float(os.getenv("DAY_TRADE_CRAMER_W", "0.12") or 0)
        if cw > 0 and float(cramer_boost_for(pick.ticker)) > 0.15:
            min_sc = max(0.28, min_sc - 0.04 * cw)
    except Exception:
        pass
    if pick.score < min_sc:
        return False
    if os.getenv("DAY_TRADE_REQUIRE_CANDLE", "true").lower() in ("1", "true", "yes"):
        if not any(x.startswith("candle_") for x in scan.bullish):
            if pick.score < _min_entry_score() + 0.10:
                return False
    return True


def should_exit(
    scan: SetupScan,
    entry_px: float,
    target_px: float,
    stop_px: float,
    opened_utc: str | None,
) -> tuple[bool, str]:
    px = scan.last_close
    if px <= 0:
        return False, ""

    max_profit = float(os.getenv("DAY_TRADE_MAX_POSITION_PROFIT_PCT", "0.008"))
    if entry_px > 0 and px >= entry_px * (1 + max_profit):
        return True, "max_profit"
    if target_px > 0 and px >= target_px:
        return True, "target_hit"
    scalp = float(os.getenv("DAY_TRADE_SCALP_PROFIT_PCT", "0.0015"))
    if entry_px > 0 and px >= entry_px * (1 + scalp):
        return True, "scalp_green"
    if stop_px > 0 and px <= stop_px:
        return True, "stop_loss"

    protect = False
    try:
        from analytics.premarket_protect import should_protect_premarket_long

        sym = str(getattr(scan, "ticker", "") or "").upper()
        protect, _ = should_protect_premarket_long(sym)
    except Exception:
        protect = False

    # Strong premarket: skip fade/time-stop through open (hard stop + profit takes still fire).
    if scan.bias <= _min_exit_score():
        if protect:
            return False, "premarket_protect_bearish"
        return True, "bearish_setups"

    if opened_utc:
        try:
            opened = datetime.fromisoformat(opened_utc.replace("Z", "+00:00"))
            held_min = (datetime.now(timezone.utc) - opened).total_seconds() / 60.0
            if held_min >= float(os.getenv("DAY_TRADE_TIME_STOP_MIN", "45")):
                if protect:
                    return False, "premarket_protect_time"
                return True, "time_stop"
        except Exception:
            pass
    return False, ""


def _close_own_day_trade_legs(*, reason: str) -> int:
    """Close day-trade sleeve only — never fortress/swing/weekly/longterm inventory."""
    from alpaca_broker import close_position_alpaca

    closed = 0
    legs_meta = _load_entries()
    own_only = os.getenv("DAY_TRADE_EXIT_OWN_ONLY", "true").lower() in ("1", "true", "yes")
    for p in _all_positions():
        sym = str(p.get("symbol", "")).upper()
        qty = float(p.get("qty") or 0)
        if qty <= 0:
            continue
        if own_only and sym not in legs_meta:
            continue
        if close_position_alpaca(sym, force=True, head="day_trade"):
            closed += 1
            entry = float(p.get("avg_entry_price") or 0)
            cur = float(p.get("current_price") or entry)
            if entry > 0:
                record_outcome(sym, (cur - entry) / entry)
            _clear_entry(sym)
            try:
                from analytics.portfolio_slots import unregister_symbol

                unregister_symbol(sym)
            except Exception:
                pass
    if closed:
        log.warning("[DAY_TRADE] %s — closed %d own leg(s)", reason, closed)
    return closed


def _day_trade_sleeve_pnl_pct() -> tuple[float, float, float]:
    """Return (pnl_pct, unrealized_usd, cost_usd) for open day-trade entry legs only."""
    legs_meta = _load_entries()
    if not legs_meta:
        return 0.0, 0.0, 0.0
    cost = 0.0
    mtm = 0.0
    by_sym = {str(p.get("symbol", "")).upper(): p for p in _all_positions()}
    for sym, meta in legs_meta.items():
        p = by_sym.get(str(sym).upper())
        if not p:
            continue
        qty = float(p.get("qty") or 0)
        if qty <= 0:
            continue
        entry = float(meta.get("entry_px") or p.get("avg_entry_price") or 0)
        cur = float(p.get("current_price") or p.get("lastday_price") or entry)
        if entry <= 0 or cur <= 0:
            continue
        cost += entry * qty
        mtm += cur * qty
    if cost <= 0:
        return 0.0, 0.0, 0.0
    unreal = mtm - cost
    return unreal / cost, unreal, cost


def _close_day_trade_cash_out_legs(*, reason: str) -> int:
    """Bank winners only — never dump underwater day-trade legs on a cash-out trigger."""
    from alpaca_broker import close_position_alpaca

    closed = 0
    legs_meta = _load_entries()
    min_green = float(os.getenv("DAY_TRADE_CASH_OUT_MIN_GAIN_PCT", "0.004"))
    min_hold_m = float(os.getenv("DAY_TRADE_CASH_OUT_MIN_HOLD_MIN", "25"))
    for p in _all_positions():
        sym = str(p.get("symbol", "")).upper()
        qty = float(p.get("qty") or 0)
        if qty <= 0 or sym not in legs_meta:
            continue
        meta = legs_meta.get(sym) or {}
        entry = float(meta.get("entry_px") or p.get("avg_entry_price") or 0)
        cur = float(p.get("current_price") or entry)
        if entry <= 0:
            continue
        gain = (cur - entry) / entry
        if gain < min_green:
            log.info(
                "[DAY_TRADE] cash-out skip %s — gain=%.2f%% < min green %.2f%% (leave on stop)",
                sym,
                100 * gain,
                100 * min_green,
            )
            continue
        if min_hold_m > 0 and meta.get("opened_utc"):
            try:
                from datetime import datetime, timezone

                opened = datetime.fromisoformat(str(meta["opened_utc"]).replace("Z", "+00:00"))
                if opened.tzinfo is None:
                    opened = opened.replace(tzinfo=timezone.utc)
                age_m = (datetime.now(timezone.utc) - opened).total_seconds() / 60.0
                if age_m < min_hold_m:
                    log.info(
                        "[DAY_TRADE] cash-out skip %s — held %.0fm < %.0fm min",
                        sym,
                        age_m,
                        min_hold_m,
                    )
                    continue
            except Exception:
                pass
        if close_position_alpaca(sym, force=True, head="day_trade"):
            closed += 1
            record_outcome(sym, gain)
            _clear_entry(sym)
            try:
                from analytics.portfolio_slots import promote_day_trade_winner, unregister_symbol

                promote_day_trade_winner(sym, pnl_pct=gain, score=0.0)
            except Exception:
                try:
                    from analytics.portfolio_slots import unregister_symbol

                    unregister_symbol(sym)
                except Exception:
                    pass
    if closed:
        log.warning("[DAY_TRADE] %s — banked %d green leg(s)", reason, closed)
    return closed


def maybe_portfolio_cash_out(equity: float) -> bool:
    """Bank day-trade winners when *sleeve* MTM hits cash-out — not whole-account equity.

    Using account equity caused fortress/mark moves to dump day-trade legs (incl. ADI
    losers) and cut PLTR after ~14m. Cash-out now: sleeve PnL only, greens only, min hold.
    """
    cash_pct = float(os.getenv("DAY_TRADE_CASH_OUT_PCT", "0.012"))
    if cash_pct <= 0:
        return False
    use_sleeve = os.getenv("DAY_TRADE_CASH_OUT_SLEEVE_ONLY", "true").lower() in (
        "1",
        "true",
        "yes",
    )
    if use_sleeve:
        pnl_pct, unreal, cost = _day_trade_sleeve_pnl_pct()
        if cost <= 0 or pnl_pct < cash_pct:
            return False
        closed = _close_day_trade_cash_out_legs(
            reason=f"CASH OUT sleeve +{100 * pnl_pct:.2f}% (${unreal:+.0f} on ${cost:.0f})"
        )
        return closed > 0
    start = ensure_session_anchor(equity)
    if start <= 0:
        return False
    pnl_pct = (equity - start) / start
    if pnl_pct < cash_pct:
        return False
    closed = _close_day_trade_cash_out_legs(reason=f"CASH OUT session +{100 * pnl_pct:.2f}%")
    return closed > 0


def maybe_eod_flatten_own() -> bool:
    """Flatten day-trade legs near RTH close; leave overnight fortress/swing book alone."""
    if os.getenv("DAY_TRADE_FLATTEN_AT_CLOSE", "true").lower() not in ("1", "true", "yes"):
        return False
    try:
        from analytics.market_session import minutes_to_rth_close

        mins = minutes_to_rth_close()
    except Exception:
        return False
    if mins is None:
        return False
    window = float(os.getenv("DAY_TRADE_EOD_FLATTEN_MINUTES", "20") or 20)
    if mins > window:
        return False
    closed = _close_own_day_trade_legs(reason=f"EOD flatten ({mins:.0f}m to close)")
    return closed > 0


def manage_exits() -> list[dict[str, Any]]:
    """Exit day-trade legs only — never liquidate fortress/swing holds."""
    results: list[dict[str, Any]] = []
    legs_meta = _load_entries()
    own_only = os.getenv("DAY_TRADE_EXIT_OWN_ONLY", "true").lower() in ("1", "true", "yes")
    for p in _all_positions():
        sym = str(p.get("symbol", "")).upper()
        qty = float(p.get("qty") or 0)
        if qty <= 0:
            continue
        if own_only and sym not in legs_meta:
            # Fortress / weekly / longterm inventory — do not scalp-chop it
            continue
        meta = legs_meta.get(sym, {})
        scan = analyze(sym)
        if scan is None:
            continue
        entry = float(meta.get("entry_px") or p.get("avg_entry_price") or scan.last_close)
        target = float(meta.get("target_px") or entry * (1 + float(os.getenv("DAY_TRADE_MAX_POSITION_PROFIT_PCT", "0.008"))))
        stop = float(meta.get("stop_px") or entry * (1 - float(os.getenv("DAY_TRADE_DEFAULT_STOP_PCT", "0.004"))))
        exit_now, why = should_exit(scan, entry, target, stop, meta.get("opened_utc"))
        if not exit_now:
            results.append({"ticker": sym, "action": "hold", "bias": scan.bias})
            continue
        from alpaca_broker import close_position_alpaca

        if close_position_alpaca(sym, force=True, head="day_trade"):
            pnl = (scan.last_close - entry) / entry if entry > 0 else 0.0
            record_outcome(sym, pnl)
            _clear_entry(sym)
            if why in ("max_profit", "target_hit", "scalp_green") and pnl > 0:
                try:
                    from analytics.portfolio_slots import promote_day_trade_winner, unregister_symbol

                    promote_day_trade_winner(sym, pnl_pct=pnl, score=scan.bias)
                except Exception:
                    pass
            else:
                try:
                    from analytics.portfolio_slots import unregister_symbol

                    unregister_symbol(sym)
                except Exception:
                    pass
            log.warning("[DAY_TRADE] SELL %s — %s pnl=%+.2f%% score=%.2f", sym, why, 100 * pnl, scan.bias)
            results.append({"ticker": sym, "action": "sell", "reason": why, "pnl_pct": pnl})
        else:
            results.append({"ticker": sym, "action": "sell_failed"})
    return results


def _scan_batch() -> tuple[list[str], bool]:
    from analytics.model_scopes import day_trade_tickers

    all_syms = day_trade_tickers()
    if not all_syms:
        return [], False
    batch = max(1, int(os.getenv("DAY_TRADE_BATCH_SIZE", "20")))
    rot = _load_json(ROTATE_PATH)
    offset = int(rot.get("offset", 0))
    n = len(all_syms)
    start = offset % n
    chunk = [all_syms[(start + i) % n] for i in range(min(batch, n))]
    new_offset = (start + batch) % n
    full_sweep = new_offset <= start or batch >= n
    _save_json(ROTATE_PATH, {"offset": new_offset, "total": n, "last_batch": chunk})
    return chunk, full_sweep


def _ranked_top(limit: int | None = None) -> list[RankedPick]:
    doc = _load_json(RANK_PATH)
    rows = list((doc.get("ranks") or {}).values())
    rows.sort(key=lambda r: float(r.get("score", 0)), reverse=True)
    out: list[RankedPick] = []
    for row in rows[: limit or _top_picks()]:
        sym = str(row.get("ticker", "")).upper()
        if not sym:
            continue
        scan = analyze(sym)
        if scan is None:
            continue
        out.append(rank_scan(scan))
    out.sort(key=lambda p: p.score, reverse=True)
    return out


def try_top_entries(equity: float) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    held = {str(p.get("symbol", "")).upper() for p in _all_positions() if float(p.get("qty") or 0) > 0}
    slots = max(0, _max_concurrent() - len(held))
    if slots <= 0:
        return [{"action": "full", "held": len(held)}]

    picks = _ranked_top(limit=max(_top_picks() * 3, 10))
    picks = [p for p in picks if should_enter(p)][: min(slots, _top_picks())]

    if not picks:
        return [{"action": "no_picks"}]

    from alpaca_broker import get_mid_price, get_quote_bid_ask, submit_limit_order

    # Size off full equity × DAY_TRADE_RISK_PER_TRADE_PCT (not equity/80 → $50 floor toys).
    # Concurrent slots still cap how many names are open; risk_pct stays small (~0.25%).
    size_equity = equity
    if os.getenv("DAY_TRADE_SIZE_ON_FULL_EQUITY", "true").lower() in ("0", "false", "no"):
        size_equity = equity / max(_max_concurrent(), 1)
    for rank, pick in enumerate(picks, start=1):
        sym = pick.ticker
        if sym in held:
            continue
        try:
            from analytics.portfolio_slots import can_open_head

            ok_slot, slot_reason = can_open_head("day_trade", sym)
            if not ok_slot:
                results.append({"ticker": sym, "action": "slot_block", "reason": slot_reason})
                continue
        except Exception:
            pass
        try:
            from alpaca_broker import pending_buy_order

            if pending_buy_order(sym):
                results.append({"ticker": sym, "action": "skip_pending_buy"})
                continue
        except Exception:
            pass
        px = pick.scan.last_close
        stop_pct = float(os.getenv("DAY_TRADE_DEFAULT_STOP_PCT", "0.004"))
        gz_stop = float((pick.scan.details or {}).get("gainz_stop") or 0)
        gz_tgt = float((pick.scan.details or {}).get("gainz_target") or 0)
        stop_px = gz_stop if gz_stop > 0 else px * (1 - stop_pct)
        risk: RiskDecision = size_position(size_equity, px, stop_px)
        if gz_tgt > 0 and risk.ok:
            risk = _dc_replace(risk, target_px=gz_tgt)
        if not risk.ok or risk.qty < 1:
            results.append({"ticker": sym, "action": "risk_block", "rank": rank})
            continue
        pat = "NONE"
        for label in pick.scan.bullish:
            if label.startswith("candle_"):
                pat = label.replace("candle_", "").upper()
                break
        try:
            q = get_quote_bid_ask(sym)
            from analytics.limit_pricing import entry_limit_px

            if q:
                bid, ask = q
                lp = entry_limit_px("buy", bid, ask)
            else:
                lp = None
            if lp is None or lp <= 0:
                mid = get_mid_price(sym) or px
                lp = mid  # last resort at last close
            else:
                mid = (q[0] + q[1]) / 2.0 if q else px
            submit_limit_order(sym, risk.qty, "buy", lp)
            record_signal(sym, pattern=pat, bias=pick.scan.bias, composite_bias=1, p_adj=pick.score)
            _save_entry(sym, entry_px=lp, target_px=risk.target_px, stop_px=risk.stop_px, pattern=pat)
            try:
                from analytics.portfolio_slots import register_symbol

                register_symbol(sym, "day_trade", qty=float(risk.qty))
            except Exception:
                pass
            held.add(sym)
            log.warning(
                "[DAY_TRADE] BUY #%d %s qty=%d score=%.3f rl=%.2f setups=%s target=%.2f",
                rank,
                sym,
                risk.qty,
                pick.score,
                pick.rl_weight,
                ",".join(pick.scan.bullish[:4]),
                risk.target_px,
            )
            results.append(
                {
                    "ticker": sym,
                    "action": "buy",
                    "rank": rank,
                    "score": pick.score,
                    "qty": risk.qty,
                    "target": risk.target_px,
                }
            )
        except Exception as e:
            log.warning("[DAY_TRADE] buy %s failed: %s", sym, e)
            results.append({"ticker": sym, "action": "buy_failed", "error": str(e)})
    return results


def run_universe() -> dict[str, Any]:
    summary: dict[str, Any] = {"exits": [], "scans": 0, "entries": []}
    halted, reason = trading_halted()
    if halted:
        summary["action"] = "halted"
        summary["reason"] = reason
        return summary

    equity = _account_equity()
    if equity <= 0:
        summary["action"] = "no_account"
        return summary
    ensure_session_anchor(equity)
    ok, limit_reason = check_daily_limits(equity)
    if not ok:
        summary["action"] = "halted"
        summary["reason"] = limit_reason
        return summary

    if maybe_portfolio_cash_out(equity):
        summary["action"] = "cash_out"
        return summary

    if maybe_eod_flatten_own():
        summary["action"] = "eod_flatten"
        return summary

    summary["exits"] = manage_exits()

    batch, full_sweep = _scan_batch()
    for sym in batch:
        scan = analyze(sym)
        if scan is None:
            continue
        pick = rank_scan(scan)
        _update_rankings(pick)
        summary["scans"] = int(summary.get("scans", 0)) + 1

    if full_sweep or os.getenv("DAY_TRADE_ENTER_EVERY_CYCLE", "false").lower() in ("1", "true", "yes"):
        summary["entries"] = try_top_entries(equity)
        top = _ranked_top(limit=3)
        summary["top3"] = [p.to_dict() for p in top]
        if full_sweep:
            try:
                from intel.club_conviction_engine import refresh_dynamic_conviction

                summary["conviction"] = refresh_dynamic_conviction()
            except Exception:
                pass

    return summary
