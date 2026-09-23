"""Day-trade risk: 1% rule, daily loss cap, profit target, position sizing."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, timezone

from utils import log


@dataclass(frozen=True)
class RiskDecision:
    ok: bool
    reason: str
    qty: int = 0
    stop_px: float = 0.0
    target_px: float = 0.0


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _b(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.lower() in ("1", "true", "yes")


def session_et_date() -> str:
    """Alpaca session date (America/New_York), not the paper VM's UTC clock."""
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    except Exception:
        return date.today().isoformat()


def session_start_equity() -> float:
    try:
        from alpaca_broker import get_account

        acct = get_account() or {}
        return float(acct.get("equity") or acct.get("last_equity") or 0)
    except Exception:
        return 0.0


def _state_path():
    from pathlib import Path

    override = os.getenv("DAY_TRADE_SESSION_PATH", "").strip()
    if override:
        p = Path(override)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    p = Path(__file__).resolve().parents[1] / "data" / "intel" / "day_trade_session.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_session() -> dict:
    import json

    p = _state_path()
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_session(data: dict) -> None:
    import json

    _state_path().write_text(json.dumps(data, indent=2), encoding="utf-8")


def _is_weekend_et(day: str | None = None) -> bool:
    raw = str(day or session_et_date() or "")
    try:
        return date.fromisoformat(raw[:10]).weekday() >= 5
    except Exception:
        return False


def _before_cash_open_et() -> bool:
    """True from midnight until 04:00 ET, before the new session can trade."""
    try:
        from zoneinfo import ZoneInfo

        now = datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        return False
    return now.hour < 4


def ensure_session_anchor(equity: float, last_equity: float | None = None) -> float:
    """Anchor today's P&L at prior close (`last_equity`) so overnight marks count.

    Saturday/Sunday must not inherit Friday's close — crypto weekend marks would
    look like a red US session and freeze leftover-cash fills.
    """
    today = session_et_date()
    st = _load_session()
    if st.get("date") != today or not st.get("start_equity"):
        start = float(last_equity or 0)
        if _is_weekend_et(today):
            start = float(equity or 0) or start
        elif _before_cash_open_et() and start > 0 and float(equity or 0) > 0:
            # Alpaca last_equity lags the ET date roll. Anchoring Tuesday at
            # Monday's stale prior close re-locks yesterday's gain before the open.
            gap = (float(equity) - start) / start
            if abs(gap) >= _f("DAILY_RED_EPS_PCT", 0.0003):
                start = float(equity)
        if start <= 0:
            try:
                from alpaca_broker import get_account

                acct = get_account() or {}
                start = float(acct.get("last_equity") or 0)
            except Exception:
                start = 0.0
        if start <= 0:
            start = float(equity or 0)
        st = {
            "date": today,
            "start_equity": start,
            "halted": False,
            "halt_reason": "",
            "weekend_rebased": _is_weekend_et(today),
        }
        _save_session(st)
    return float(st.get("start_equity") or equity)


def clear_trading_halt() -> None:
    """Resume day-trade buys (e.g. new session or manual unpause)."""
    st = _load_session()
    st["halted"] = False
    st["halt_reason"] = ""
    st.pop("halted_at", None)
    _save_session(st)
    log.info("[DAY_TRADE] halt cleared — buys enabled")


def halt_trading(reason: str) -> None:
    st = _load_session()
    st["halted"] = True
    st["halt_reason"] = reason
    st["halted_at"] = datetime.now(timezone.utc).isoformat()
    _save_session(st)
    log.warning("[DAY_TRADE] halted — %s", reason)


def trading_halted() -> tuple[bool, str]:
    st = _load_session()
    today = session_et_date()
    # Stale halt from a prior ET session must not block forever.
    if st.get("date") and str(st.get("date")) != today:
        st = {"date": today, "start_equity": 0, "halted": False, "halt_reason": ""}
        _save_session(st)
        log.info("[DAY_TRADE] new session %s — cleared halt + start_equity anchor", today)
        return False, ""
    if st.get("halted"):
        reason = str(st.get("halt_reason") or "halted")
        target = _f("SESSION_EQUITY_TARGET_USD", 0)
        if target <= 0 and "profit target" in reason.lower() and "daily profit" not in reason.lower():
            st["halted"] = False
            st["halt_reason"] = ""
            _save_session(st)
            return False, ""
        return True, reason
    return False, ""


def is_trading_halted() -> bool:
    halted, _why = trading_halted()
    return halted


def check_daily_limits(equity: float, last_equity: float | None = None) -> tuple[bool, str]:
    """Stop new buys when red, at -0.2% max loss, or at the +1.5% lock. Exits stay on."""
    try:
        eq = float(equity or 0)
    except (TypeError, ValueError):
        eq = 0.0
    if eq < 100.0:
        log.warning("[DAY_TRADE] skip daily limits — equity snapshot missing (%.2f)", eq)
        return True, ""
    start = ensure_session_anchor(eq, last_equity=last_equity)
    if start <= 0:
        return True, ""
    st_pre = _load_session()
    if (
        _is_weekend_et()
        and not st_pre.get("weekend_rebased")
        and eq >= 100.0
        and start > 0
        and (eq - start) / start <= -_f("DAILY_RED_EPS_PCT", 0.0003)
    ):
        log.info(
            "[DAY_TRADE] weekend rebase start %.2f → %.2f (skip inherited Friday close)",
            start,
            eq,
        )
        st_w = dict(st_pre)
        st_w["start_equity"] = eq
        st_w["halted"] = False
        st_w["halt_reason"] = ""
        st_w["weekend_rebased"] = True
        st_w.pop("halted_at", None)
        _save_session(st_w)
        start = eq
    pnl_pct = (eq - start) / start
    max_loss = _f("DAY_TRADE_MAX_DAILY_LOSS_PCT", 0.002)
    profit_lock = _f("DAY_TRADE_DAILY_PROFIT_PCT", 0.015)
    red_eps = _f("DAILY_RED_EPS_PCT", 0.0003)
    st = _load_session()
    reason = str(st.get("halt_reason") or "")

    if profit_lock > 0 and pnl_pct >= profit_lock:
        halt_trading(f"daily profit lock {100 * pnl_pct:.2f}% (target {100 * profit_lock:.1f}%)")
        return False, "daily-profit-pct"

    # Drop a stale/false max-loss halt once live equity is no longer through the floor.
    if reason.startswith("max daily loss") and pnl_pct > -max_loss:
        clear_trading_halt()
        reason = ""

    if pnl_pct <= -max_loss:
        halt_trading(f"max daily loss {100 * pnl_pct:.2f}%")
        return False, "max-daily-loss"

    # Transient red: block new entries, but allow a resume if the mark recovers.
    if reason.startswith("daily red") and pnl_pct > -red_eps:
        clear_trading_halt()
        reason = ""

    target = _f("SESSION_EQUITY_TARGET_USD", 0)
    if target > 0 and eq >= target:
        halt_trading(f"profit target ${target:,.0f} hit")
        return False, "profit-target"

    if _b("DAILY_RED_NO_NEW_ENTRIES", True) and pnl_pct <= -red_eps:
        halt_trading(f"daily red {100 * pnl_pct:.2f}% — no new entries")
        return False, "daily-red"
    return True, ""


def size_position(
    equity: float,
    entry_px: float,
    stop_px: float,
    *,
    max_qty: int | None = None,
) -> RiskDecision:
    if entry_px <= 0:
        return RiskDecision(False, "bad-entry")
    risk_pct = _f("DAY_TRADE_RISK_PER_TRADE_PCT", 0.01)
    risk_usd = max(50.0, equity * risk_pct)
    stop_dist = abs(entry_px - stop_px)
    if stop_dist < entry_px * 0.0005:
        stop_dist = entry_px * _f("DAY_TRADE_DEFAULT_STOP_PCT", 0.004)
        stop_px = entry_px - stop_dist
    qty = int(risk_usd / stop_dist)
    cap = max_qty or int(_f("DAY_TRADE_MAX_SHARES", 400))
    qty = max(1, min(qty, cap))
    # Dollar cap: 1% stop on $72k equity used to size 389 WMT (~$45k). Risk-$ ≠ notional.
    hard_max = _f("HARD_MAX_ORDER_NOTIONAL", 0.0)
    dt_max = _f("DAY_TRADE_MAX_NOTIONAL", 0.0)
    try:
        from analytics.buying_power import clip_ceiling_usd, load_plan

        snap = load_plan() or {}
        calc_clip = float(snap.get("day_trade_clip") or 0) or clip_ceiling_usd(equity)
    except Exception:
        calc_clip = equity * min(
            _f("MAX_SINGLE_ASSET_FRAC", 0.10),
            _f("FORTRESS_MAX_SINGLE_FRAC", 0.10),
        )
    if hard_max > 0 and dt_max > 0:
        hard_max = min(hard_max, dt_max)
    elif hard_max <= 0:
        hard_max = dt_max
    notional_cap = min(hard_max, calc_clip) if hard_max > 0 else calc_clip
    if notional_cap > 0 and entry_px > notional_cap * 1.02:
        return RiskDecision(False, "name-too-expensive-for-cap")
    if notional_cap > 0:
        qty = max(1, min(qty, int(notional_cap / max(entry_px, 1e-9))))
    rr = _f("DAY_TRADE_RISK_REWARD", 2.0)
    target_px = entry_px + rr * stop_dist
    return RiskDecision(True, "ok", qty=qty, stop_px=stop_px, target_px=target_px)
