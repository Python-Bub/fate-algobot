"""Single buying-power calculator for every sleeve.

Overnight fortress uses **cash / equity gap at 1.0×** — never 4× PDT margin held
overnight. Same-day HFT / day-trade / micro-scalp may use day-trade buying power
and must flatten before the close.

This module is the only place that decides how much money is still idle and how
large a clip should be. Sleeves must not invent $2,500 hard caps or divide the
book by a 500-name phantom slot count.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_PATH = ROOT / "data" / "ops" / "buying_power.json"

try:
    from data_platform.runtime_env import load_runtime_env

    load_runtime_env()
except Exception:
    pass


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _i(name: str, default: int) -> int:
    try:
        return int(float(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


def _b(name: str, default: bool = True) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _session_is_weekend() -> bool:
    """Sat/Sun ET — Alpaca last_equity is still Friday close."""
    try:
        from analytics.day_trade_risk import session_et_date

        return date.fromisoformat(str(session_et_date())[:10]).weekday() >= 5
    except Exception:
        return False


def overnight_leverage() -> float:
    """Gross overnight book as a fraction of equity. Hard-capped at 1.0."""
    return min(1.0, max(0.25, _f("MAX_GROSS_LEVERAGE", 1.0)))


def overnight_target_frac() -> float:
    return min(
        overnight_leverage(),
        _f("FORTRESS_TARGET_DEPLOY_FRAC", 1.0),
        _f("FORTRESS_MAX_GROSS_FRAC", 1.0),
    )


def equity_single_cap(equity: float, *, crypto: bool = False) -> float:
    if crypto:
        frac = _f("FORTRESS_CRYPTO_MAX_SINGLE_FRAC", 0.18)
    else:
        frac = min(_f("FORTRESS_MAX_SINGLE_FRAC", 0.10), _f("MAX_SINGLE_ASSET_FRAC", 0.12))
    return max(0.0, float(equity) * frac * 0.995)


def sizing_slots() -> int:
    """How many overnight names we actually size against (not the 500 placeholder)."""
    pos = _i("FORTRESS_MAX_POSITIONS", 24)
    live = _i("MAX_LIVE_SYMBOLS", 40)
    top = _i("FORTRESS_TOP_BUYS_PER_PASS", 16)
    cands = [n for n in (pos, live, top) if 0 < n <= 80]
    if not cands:
        return 24
    return max(8, min(cands))


def order_hard_max_usd() -> float:
    """Explicit per-ticket clamp. 0 = no clamp (use single-name equity cap)."""
    hard = _f("HARD_MAX_ORDER_NOTIONAL", 0.0)
    if hard > 0:
        return hard
    return _f("MAX_ORDER_NOTIONAL", 0.0)


def go_live_cap_usd() -> float:
    return _f("FORTRESS_GO_LIVE_MAX_NOTIONAL", 0.0)


def clip_ceiling_usd(equity: float, *, crypto: bool = False) -> float:
    """Max dollars one buy ticket may be. Single-name cap unless an explicit hard max is set."""
    cap = equity_single_cap(equity, crypto=crypto)
    hard = order_hard_max_usd()
    go = go_live_cap_usd()
    if hard > 0:
        cap = min(cap, hard)
    if go > 0:
        cap = min(cap, go)
    return max(0.0, cap)


@dataclass
class BuyingPowerPlan:
    ts_utc: str
    equity: float
    cash: float
    long_mv: float
    buying_power: float
    day_buying_power: float
    overnight_target: float
    overnight_gap: float
    overnight_budget: float
    overnight_slots: int
    overnight_clip: float
    overnight_full: bool
    single_cap: float
    hft_day_budget: float
    hft_clip: float
    day_trade_budget: float
    day_trade_clip: float
    micro_scalp_budget: float
    micro_scalp_clip: float
    leftover_cash: float
    leftover_day_bp: float
    notes: list[str]
    last_equity: float = 0.0
    daily_pnl: float = 0.0
    regt_buying_power: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["overnight_target_frac"] = overnight_target_frac()
        d["sizing_slots"] = sizing_slots()
        d["source"] = "GET /v2/account"
        return d


def _num(acct: dict, *keys: str) -> float:
    for k in keys:
        try:
            v = acct.get(k)
            if v is not None and float(v) > 0:
                return float(v)
        except (TypeError, ValueError):
            continue
    return 0.0


def _num0(acct: dict, *keys: str) -> float:
    """Like _num but keeps a real zero (cash can be 0.00)."""
    for k in keys:
        try:
            v = acct.get(k)
            if v is None or v == "":
                continue
            return float(v)
        except (TypeError, ValueError):
            continue
    return 0.0


def parse_v2_account(acct: dict | None) -> dict[str, float]:
    """GET /v2/account figures — cash, equity, buying_power.

    Overnight sizes from **cash** / equity. Same-day sleeves size from
    **buying_power** (Alpaca's live margin figure). `daytrading_buying_power`
    was removed 2026-07-06; if a stale payload still has it, we only use it as
    a fallback alias for buying_power.
    """
    acct = acct or {}
    equity = _num(acct, "equity", "last_equity") or 1.0
    last_equity = _num(acct, "last_equity") or equity
    cash = _num0(acct, "cash")
    bp = _num(acct, "buying_power")
    day_bp = _num(acct, "buying_power", "daytrading_buying_power", "last_daytrading_buying_power")
    regt = _num(acct, "regt_buying_power") or bp
    crypto_bp = _num(acct, "non_marginable_buying_power", "crypto_buying_power")
    long_mv = abs(_num0(acct, "long_market_value"))
    return {
        "equity": equity,
        "last_equity": last_equity,
        "daily_pnl": equity - last_equity,
        "cash": cash,
        "buying_power": bp,
        "day_buying_power": day_bp,
        "regt_buying_power": regt,
        "crypto_buying_power": crypto_bp,
        "long_market_value": long_mv,
    }


def hold_is_green(gain: float | None, *, min_gain: float | None = None) -> bool:
    """True to add size. New/unknown holds are allowed; red names are not."""
    if gain is None:
        return True
    floor = min_gain if min_gain is not None else _f("FORTRESS_MIN_ADD_GAIN", 0.0)
    if _b("FORTRESS_WINNERS_ONLY", True):
        return float(gain) > floor
    return float(gain) >= -1e-12


def long_market_value(positions: list[dict] | None) -> float:
    total = 0.0
    for p in positions or []:
        try:
            if float(p.get("qty") or 0) <= 0:
                continue
            total += abs(float(p.get("market_value") or 0))
        except (TypeError, ValueError):
            continue
    return total


def plan_from_account(
    acct: dict | None,
    positions: list[dict] | None = None,
    *,
    persist: bool = False,
) -> BuyingPowerPlan:
    acct = acct or {}
    fig = parse_v2_account(acct)
    equity = fig["equity"]
    cash = max(0.0, fig["cash"])
    bp = fig["buying_power"]
    dtbp = fig["day_buying_power"] or bp
    long_mv = long_market_value(positions)
    if long_mv <= 0:
        long_mv = fig["long_market_value"]
    inferred_cash = max(0.0, equity - long_mv)
    if cash <= 1.0 and inferred_cash > cash:
        cash = inferred_cash

    target_frac = overnight_target_frac()
    overnight_target = equity * target_frac
    slack = _f("FORTRESS_IDLE_FILL_SLACK", 0.03)
    overnight_gap = max(0.0, overnight_target - long_mv)
    cash_reserve = max(0.0, _f("FORTRESS_CASH_RESERVE_USD", 0.0))
    overnight_budget = min(overnight_gap, max(0.0, cash - cash_reserve))
    # Reg T buying power is the extra we can still hold overnight. The 4× figure
    # stays with same-day HFT. Only an explicit regt_buying_power field counts —
    # missing it must not fall through to the full intraday buying_power.
    regt_spend = 0.0
    if _b("FORTRESS_DEPLOY_REGT", True):
        raw_regt = acct.get("regt_buying_power")
        try:
            regt_spend = float(raw_regt) if raw_regt not in (None, "") else 0.0
        except (TypeError, ValueError):
            regt_spend = 0.0
    if regt_spend > 0:
        target_frac = max(target_frac, min(2.0, _f("FORTRESS_REGT_TARGET_FRAC", 2.0)))
        overnight_target = equity * target_frac
        overnight_gap = max(0.0, overnight_target - long_mv)
        legal = max(max(0.0, cash - cash_reserve), regt_spend)
        cap_bp = bp if bp > 0 else legal
        overnight_budget = min(overnight_gap, legal, cap_bp)
    overnight_full = overnight_gap <= slack * equity + 50.0

    slots = sizing_slots()
    n_held = sum(1 for p in (positions or []) if float(p.get("qty") or 0) > 0)
    slots_left = max(1, slots - min(n_held, slots - 1))
    single = equity_single_cap(equity)
    # Fewer, fully-funded clips — not equity/500.
    half = max(_f("MIN_ORDER_NOTIONAL", 200.0), single * 0.45)
    if overnight_budget >= half:
        n_clips = max(1, min(slots_left, int(math.ceil(overnight_budget / half))))
        overnight_clip = min(clip_ceiling_usd(equity), overnight_budget / n_clips)
    else:
        n_clips = 1
        overnight_clip = min(clip_ceiling_usd(equity), overnight_budget)

    notes: list[str] = []
    if overnight_budget > 50:
        notes.append(f"overnight_cash_idle ${overnight_budget:.0f} → {n_clips} clips @ ${overnight_clip:.0f}")
    if overnight_full:
        notes.append("overnight_book_full_1x")
    else:
        notes.append(f"overnight_gap ${overnight_gap:.0f} of ${overnight_target:.0f}")

    hft_frac = _f("HFT_BP_USE_FRAC", 0.85)
    hft_reserve = _f("HFT_BP_RESERVE_USD", 200.0)
    hft_slots = max(1, _i("HFT_MAX_CONCURRENT_SLOTS", 16))
    # Same-day DTBP only. If cash is still idle, HFT must not 4× that cash overnight.
    day_pool = max(0.0, dtbp * hft_frac - hft_reserve)
    if not overnight_full and not _b("HFT_USE_DTBP", True):
        day_pool = 0.0
        notes.append("hft_paused_until_overnight_cash_deployed")
    elif not overnight_full:
        notes.append("hft_dtbp_overlay_flatten_eod")
    hft_day_budget = day_pool
    hft_floor = _f("HFT_MIN_ORDER_NOTIONAL", 200.0)
    hft_cap = _f("HFT_MAX_ORDER_NOTIONAL", 0.0)
    if hft_cap <= 0:
        # Pace-first leftover BP: 200/min recycles; do not park 10% equity per clip.
        hft_cap = min(single, max(hft_floor * 4.0, day_pool / max(hft_slots, 20)))
    hft_clip = max(hft_floor, min(hft_cap, hft_day_budget / hft_slots)) if hft_day_budget >= hft_floor else 0.0

    dt_frac = _f("DAY_TRADE_BP_USE_FRAC", 0.25)
    day_trade_budget = max(0.0, day_pool * dt_frac) if overnight_full or _b("DAY_TRADE_MODE", True) else 0.0
    dt_cap = _f("DAY_TRADE_MAX_NOTIONAL", 0.0)
    if dt_cap <= 0:
        dt_cap = single
    day_trade_clip = min(dt_cap, day_trade_budget) if day_trade_budget >= _f("MIN_ORDER_NOTIONAL", 200) else 0.0

    ms_frac = _f("MICRO_SCALP_BP_USE_FRAC", 0.15)
    micro_scalp_budget = max(0.0, day_pool * ms_frac)
    ms_cap = _f("MICRO_SCALP_NOTIONAL", 0.0)
    if ms_cap <= 0:
        ms_cap = min(single, 2_500.0)
    micro_scalp_clip = min(ms_cap, micro_scalp_budget)

    leftover_day = max(0.0, dtbp - overnight_budget)
    if fig["daily_pnl"] > 0:
        notes.append(f"account_green_today ${fig['daily_pnl']:.0f}")
    last_eq = fig["last_equity"] or equity
    pnl_pct = (equity - last_eq) / max(last_eq, 1e-9)
    profit_lock = _f("DAY_TRADE_DAILY_PROFIT_PCT", 0.015)
    red_eps = _f("DAILY_RED_EPS_PCT", 0.0003)
    no_new = False
    if _session_is_weekend():
        notes.append("weekend_skip_inherited_last_equity_pnl")
    else:
        if _b("DAILY_RED_NO_NEW_ENTRIES", True) and pnl_pct <= -red_eps:
            no_new = True
            notes.append(f"daily_red_no_new_entries {100 * pnl_pct:.2f}%")
        if profit_lock > 0 and pnl_pct >= profit_lock:
            no_new = True
            notes.append(f"daily_profit_lock {100 * pnl_pct:.2f}%")
    if no_new:
        hft_clip = 0.0
        hft_day_budget = 0.0
        day_trade_clip = 0.0
        day_trade_budget = 0.0
        micro_scalp_clip = 0.0
        micro_scalp_budget = 0.0
    plan = BuyingPowerPlan(
        ts_utc=datetime.now(timezone.utc).isoformat(),
        equity=equity,
        cash=cash,
        long_mv=long_mv,
        buying_power=bp,
        day_buying_power=dtbp,
        overnight_target=overnight_target,
        overnight_gap=overnight_gap,
        overnight_budget=overnight_budget,
        overnight_slots=n_clips,
        overnight_clip=overnight_clip,
        overnight_full=overnight_full,
        single_cap=single,
        hft_day_budget=hft_day_budget,
        hft_clip=hft_clip,
        day_trade_budget=day_trade_budget,
        day_trade_clip=day_trade_clip,
        micro_scalp_budget=micro_scalp_budget,
        micro_scalp_clip=micro_scalp_clip,
        leftover_cash=overnight_budget,
        leftover_day_bp=leftover_day,
        notes=notes,
        last_equity=fig["last_equity"],
        daily_pnl=fig["daily_pnl"],
        regt_buying_power=fig["regt_buying_power"],
    )
    if persist:
        persist_plan(plan)
    return plan


def persist_plan(plan: BuyingPowerPlan) -> Path:
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(json.dumps(plan.to_dict(), indent=2), encoding="utf-8")
    return SNAPSHOT_PATH


def load_plan() -> dict[str, Any] | None:
    if not SNAPSHOT_PATH.is_file():
        return None
    try:
        return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def refresh_and_persist() -> BuyingPowerPlan:
    acct: dict = {}
    positions: list[dict] = []
    try:
        from alpaca_broker import get_account, list_positions

        acct = get_account() or {}
        positions = list_positions() or []
    except Exception:
        pass
    return plan_from_account(acct, positions, persist=True)


def fortress_ticket_usd(
    *,
    equity: float,
    existing_mv: float,
    leftover_budget: float,
    crypto: bool = False,
) -> float:
    """One fortress buy: fill idle overnight cash up to the single-name cap."""
    floor = _f("MIN_ORDER_NOTIONAL", 200.0)
    room = max(0.0, equity_single_cap(equity, crypto=crypto) - max(0.0, existing_mv))
    cap = clip_ceiling_usd(equity, crypto=crypto)
    n = min(room, cap, max(0.0, leftover_budget))
    if n < floor:
        return 0.0
    return n
