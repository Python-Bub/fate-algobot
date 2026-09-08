"""Pre-close overnight deleverage — keep a core book, cut margin bleed.

Overnight "losses before we open" were mostly mark-to-market on a 1.5–3×
levered book through post/pre quotes (almost zero outside-RTH fills). This
module trims gross deploy into an overnight-safe band near the RTH close
without wiping intentional multi-day holdings.
"""

from __future__ import annotations

import os
from typing import Any


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def overnight_trim_enabled() -> bool:
    return _env_bool("FORTRESS_OVERNIGHT_TRIM", True)


def overnight_max_deploy_frac() -> float:
    # Target overnight gross / equity (not BP). Keep a real book, kill leverage.
    return max(0.15, min(1.0, _env_float("FORTRESS_OVERNIGHT_MAX_DEPLOY_FRAC", 0.55)))


def preclose_trim_minutes() -> float:
    return max(5.0, _env_float("FORTRESS_PRECLOSE_TRIM_MINUTES", 25.0))


def in_preclose_window() -> bool:
    """True when we should start *trimming* for overnight (sells / deleverage).

    Also true in post/pre if still over the overnight cap — that's when the
    MTM bleed shows up as 'lost money before we even start'.
    Emergency: any RTH afternoon with deploy way above the overnight cap.
    """
    try:
        from analytics.market_session import Session, current_session, minutes_to_rth_close, now_et

        sess = current_session()
        if sess == Session.REGULAR:
            mins = minutes_to_rth_close()
            if mins is not None and 0.0 <= float(mins) <= preclose_trim_minutes():
                return True
            # Emergency deleverage window (default from 14:00 ET onward).
            start_h = int(_env_float("FORTRESS_OVERNIGHT_TRIM_FROM_HOUR", 14.0))
            if now_et().hour >= start_h:
                return True
            return False
        # After hours: still allow one-shot deleverage while exits can fill.
        if sess in (Session.POST_MARKET, Session.PRE_MARKET):
            # Premarket dumps on a thin tape are how overnight holds get wrecked.
            # Delever at RTH close, not at 6am ET.
            return False
        return False
    except Exception:
        return False


def in_overnight_buy_block_window() -> bool:
    """True only when *new buys* should be blocked for overnight deleverage.

    Critical: do NOT reuse the afternoon trim window (14:00+) for buy blocks —
    that starved RTH entries all afternoon while deploy sat above the overnight
    cap. Buys block only in the final preclose minutes; extended sessions are
    opt-in via FORTRESS_OVERNIGHT_BLOCK_BUYS_EXTENDED (default false so pre/post
    can still enter when under the overnight deploy cap).
    """
    try:
        from analytics.market_session import Session, current_session, minutes_to_rth_close

        sess = current_session()
        if sess == Session.REGULAR:
            mins = minutes_to_rth_close()
            block_m = max(5.0, _env_float("FORTRESS_OVERNIGHT_BUY_BLOCK_MINUTES", 25.0))
            return mins is not None and 0.0 <= float(mins) <= block_m
        if sess in (Session.POST_MARKET, Session.PRE_MARKET):
            return _env_bool("FORTRESS_OVERNIGHT_BLOCK_BUYS_EXTENDED", False)
        return False
    except Exception:
        return False


def rank_trim_candidates(positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Worst first: losers, then smallest conviction / largest absolute risk."""
    scored: list[tuple[float, dict[str, Any]]] = []
    for p in positions:
        try:
            qty = float(p.get("qty") or 0)
            if qty <= 0:
                continue
            mv = abs(float(p.get("market_value") or 0))
            upl = float(p.get("unrealized_pl") or 0)
            upl_pct = float(p.get("unrealized_plpc") or 0)
            # Prefer trimming losers and large legs.
            score = (-upl_pct * 1000.0) + (mv * 0.0001) - (upl * 0.01)
            scored.append((score, p))
        except (TypeError, ValueError):
            continue
    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored]


def plan_overnight_trim(
    *,
    equity: float,
    positions: list[dict[str, Any]],
    max_deploy_frac: float | None = None,
) -> list[str]:
    """Return symbols to fully close (in order) to get under overnight deploy cap."""
    if equity <= 0:
        return []
    cap = (max_deploy_frac if max_deploy_frac is not None else overnight_max_deploy_frac()) * equity
    gross = 0.0
    for p in positions:
        try:
            if float(p.get("qty") or 0) > 0:
                gross += abs(float(p.get("market_value") or 0))
        except (TypeError, ValueError):
            continue
    if gross <= cap:
        return []
    need = gross - cap
    out: list[str] = []
    freed = 0.0
    for p in rank_trim_candidates(positions):
        if freed >= need:
            break
        sym = str(p.get("symbol") or "").replace("/", "-").upper()
        if not sym:
            continue
        mv = abs(float(p.get("market_value") or 0))
        out.append(sym)
        freed += mv
    return out


def maybe_overnight_risk_off(*, log: Any = None) -> dict[str, Any]:
    """Trim open longs near RTH close when overnight leverage is too high.

    Returns a small status dict for logging / tests.
    """
    if not overnight_trim_enabled():
        return {"action": "skip", "reason": "disabled"}
    if not in_preclose_window():
        return {"action": "skip", "reason": "outside_preclose"}

    try:
        from alpaca_broker import (
            cancel_open_orders,
            close_position_alpaca,
            get_account,
            list_positions,
        )
    except Exception as e:
        return {"action": "error", "reason": f"broker_import:{e}"}

    try:
        acct = get_account() or {}
        equity = float(acct.get("equity") or acct.get("portfolio_value") or 0)
        positions = [p for p in (list_positions() or []) if float(p.get("qty") or 0) > 0]
    except Exception as e:
        return {"action": "error", "reason": str(e)}

    if equity <= 0 or not positions:
        return {"action": "skip", "reason": "no_book", "equity": equity}

    gross = sum(abs(float(p.get("market_value") or 0)) for p in positions)
    frac = gross / equity if equity else 0.0
    cap_frac = overnight_max_deploy_frac()
    if frac <= cap_frac + 1e-6:
        return {
            "action": "ok",
            "reason": "under_cap",
            "deploy_frac": frac,
            "cap_frac": cap_frac,
        }

    to_close = plan_overnight_trim(equity=equity, positions=positions, max_deploy_frac=cap_frac)
    # Cancel working buys that fight sells (wash-trade / re-leverage).
    for sym in to_close:
        try:
            # Never wipe HFT/micro resting orders while trimming overnight risk.
            cancel_open_orders(sym, skip_hft=True)
        except Exception:
            pass
    closed: list[str] = []
    for sym in to_close:
        try:
            if close_position_alpaca(sym):
                closed.append(sym)
                if log is not None:
                    log.info(
                        "[OVERNIGHT] trim %s — deploy %.0f%% > overnight cap %.0f%%",
                        sym,
                        100 * frac,
                        100 * cap_frac,
                    )
        except Exception as e:
            if log is not None:
                log.warning("[OVERNIGHT] trim failed %s: %s", sym, e)

    return {
        "action": "trimmed",
        "deploy_frac": frac,
        "cap_frac": cap_frac,
        "closed": closed,
        "planned": to_close,
    }


def block_new_buys_for_overnight() -> tuple[bool, str]:
    """Block new buys only in true preclose / extended — not all afternoon RTH."""
    if not overnight_trim_enabled():
        return False, "off"
    if not in_overnight_buy_block_window():
        return False, "outside_buy_block_window"
    try:
        from alpaca_broker import get_account, list_positions

        acct = get_account() or {}
        equity = float(acct.get("equity") or acct.get("portfolio_value") or 0)
        if equity <= 0:
            return False, "no_equity"
        gross = sum(
            abs(float(p.get("market_value") or 0))
            for p in (list_positions() or [])
            if float(p.get("qty") or 0) > 0
        )
        frac = gross / equity
        cap = overnight_max_deploy_frac()
        if frac > cap:
            return True, f"overnight_trim deploy={frac:.0%}>cap={cap:.0%}"
    except Exception as e:
        return False, f"check_err:{e}"
    return False, "under_cap"
