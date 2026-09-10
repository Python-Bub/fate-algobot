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


def session_start_equity() -> float:
    try:
        from alpaca_broker import get_account

        acct = get_account() or {}
        return float(acct.get("equity") or acct.get("last_equity") or 0)
    except Exception:
        return 0.0


def _state_path():
    from pathlib import Path

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


def ensure_session_anchor(equity: float) -> float:
    """Return today's session-start equity (anchor for daily P&L)."""
    today = date.today().isoformat()
    st = _load_session()
    if st.get("date") != today or not st.get("start_equity"):
        st = {"date": today, "start_equity": equity, "halted": False, "halt_reason": ""}
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
    today = date.today().isoformat()
    # Stale halt from a prior calendar day must not block forever.
    # Also drop prior-day start_equity — keeping it skews today's loss % vs a stale anchor.
    if st.get("date") and str(st.get("date")) != today:
        st = {"date": today, "start_equity": 0, "halted": False, "halt_reason": ""}
        _save_session(st)
        log.info("[DAY_TRADE] new session %s — cleared halt + start_equity anchor", today)
        return False, ""
    if st.get("halted"):
        reason = str(st.get("halt_reason") or "halted")
        target = _f("SESSION_EQUITY_TARGET_USD", 0)
        if target <= 0 and "profit target" in reason.lower():
            st["halted"] = False
            st["halt_reason"] = ""
            _save_session(st)
            return False, ""
        return True, reason
    return False, ""


def check_daily_limits(equity: float) -> tuple[bool, str]:
    start = ensure_session_anchor(equity)
    if start <= 0:
        return True, ""
    pnl_pct = (equity - start) / start
    max_loss = _f("DAY_TRADE_MAX_DAILY_LOSS_PCT", 0.02)
    if pnl_pct <= -max_loss:
        halt_trading(f"max daily loss {100 * pnl_pct:.2f}%")
        return False, "max-daily-loss"
    target = _f("SESSION_EQUITY_TARGET_USD", 0)
    if target > 0 and equity >= target:
        halt_trading(f"profit target ${target:,.0f} hit")
        return False, "profit-target"
    min_target_pct = _f("DAY_TRADE_DAILY_PROFIT_PCT", 0)
    if min_target_pct > 0 and pnl_pct >= min_target_pct:
        halt_trading(f"daily profit {100 * pnl_pct:.2f}%")
        return False, "daily-profit-pct"
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
