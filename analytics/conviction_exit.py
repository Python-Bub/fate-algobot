"""Conviction sizing + sell/rotate decisions (noise vs thesis death).

Low risk / high confidence → larger buy-in (up to single-name cap).
High risk / low confidence → small buy-in.
Sell true thesis death with multi-signal confirmation — not one noisy bar.
Rotate after enough profit so capital can move to better names.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _b(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in ("1", "true", "yes")


@dataclass
class ExitDecision:
    action: str  # hold | scale_out | take_profit | thesis_death | signal_sell | noise_hold
    reason: str
    trim_frac: float = 1.0  # 1.0 = full close
    noise: bool = False


def conviction_size_mult(
    p_adj: float,
    *,
    exec_conf: float | None = None,
    risk_pressure: float | None = None,
    force_priority: bool = False,
) -> float:
    """
    Map conviction → notional multiplier in [min, max].
    High p_adj + high exec + low pressure → near max (fill toward single-name cap).
    Weak / risky → near min (small probe only).
    """
    lo = _f("FORTRESS_CONVICTION_SIZE_MIN", 0.35)
    hi = _f("FORTRESS_CONVICTION_SIZE_MAX", 1.0)
    # Map p_adj 0.52..0.72 → 0..1
    edge = max(0.0, min(1.0, (float(p_adj) - 0.52) / 0.20))
    conf = 0.55 if exec_conf is None else max(0.0, min(1.0, float(exec_conf)))
    # risk_pressure 0..1 shrinks size
    pressure = 0.0 if risk_pressure is None else max(0.0, min(1.0, float(risk_pressure)))
    raw = 0.55 * edge + 0.35 * conf + 0.10 * (1.0 - pressure)
    if force_priority:
        raw = max(raw, _f("FORTRESS_FORCE_CONVICTION_FLOOR", 0.75))
    # Steepen: weak ideas get crushed toward lo
    curved = raw ** _f("FORTRESS_CONVICTION_CURVE", 1.25)
    return lo + (hi - lo) * curved


def _pressure_score(symbol: str) -> float:
    try:
        from intel.downward_pressure import exit_adjustments

        adj = exit_adjustments(symbol)
        return float(adj.get("pressure_score") or 0.0)
    except Exception:
        return 0.0


def thesis_death_confirmed(
    symbol: str,
    *,
    p_adj: float,
    gain: float,
    pred: int | None = None,
    session_gap: float | None = None,
    now_et=None,
) -> tuple[bool, str]:
    """
    True complete-loss / thesis dead — multi-signal, not one red print.

    Requires loss beyond noise floor AND at least `need` confirming votes among:
    model sell, hard pressure, pred flip, earnings abort plan.

    Earnings print gap kill is a single decisive vote (WMT 2026-08-20): do not
    wait for pressure/model confirmation while a BMO dump is already live.
    """
    if not _b("FORTRESS_THESIS_DEATH_ENABLED", True):
        return False, "disabled"
    try:
        from analytics.earnings_gap_guard import should_kill_gap
        from intel.historical_events import holdings_earnings_plan

        plan = holdings_earnings_plan(symbol, is_holding=True)
        if should_kill_gap(
            dte=plan.get("days_to"),
            dse=plan.get("days_since"),
            hour=plan.get("hour") or plan.get("report_session"),
            gap=session_gap,
            gain_vs_entry=gain,
            now_et=now_et,
        ):
            return True, "earnings_gap_kill"
    except Exception:
        pass
    min_loss = _f("FORTRESS_THESIS_DEATH_MIN_LOSS", 0.012)  # -1.2% minimum
    if float(gain) > -min_loss:
        return False, "loss_within_noise_band"
    sell_p = _f("FORTRESS_SELL_MAX_P", 0.52)
    need = int(_f("FORTRESS_THESIS_DEATH_CONFIRM_N", 2))
    votes: list[str] = []
    if float(p_adj) <= sell_p:
        votes.append(f"model_sell_p={p_adj:.3f}")
    if pred is not None and int(pred) != 1:
        votes.append("pred_not_long")
    pressure = _pressure_score(symbol)
    if pressure >= _f("FORTRESS_THESIS_DEATH_PRESSURE", 0.70):
        votes.append(f"hard_pressure={pressure:.2f}")
    try:
        from intel.historical_events import holdings_earnings_plan

        plan = holdings_earnings_plan(symbol, is_holding=True)
        # CRITICAL: fear_dump + trim_bias are ONE earnings signal — counting both
        # satisfied need=2 while model stayed bullish (AAPL p_adj~0.61, −6% overnight spam).
        earn_vote = None
        severe = -_f("FORTRESS_EARNINGS_SEVERE_ABORT_LOSS", 0.045)
        abort = -_f("FORTRESS_EARNINGS_ABORT_LOSS", 0.02)
        model_weak = float(p_adj) <= sell_p or (pred is not None and int(pred) != 1)
        if plan.get("fear_dump_watch") and float(gain) <= abort:
            if model_weak or float(gain) <= severe:
                earn_vote = "earnings_fear_dump"
        elif (
            float(plan.get("trim_bias") or 0) >= 0.5
            and float(gain) < 0
            and (model_weak or float(gain) <= severe)
        ):
            earn_vote = "earnings_trim_bias"
        if earn_vote:
            votes.append(earn_vote)
    except Exception:
        pass
    # Earnings-only death requires severe loss — never kill a bullish model on post-print noise alone.
    non_earn = [v for v in votes if not str(v).startswith("earnings_")]
    if (
        len(votes) >= need
        and float(gain) <= -min_loss
        and (non_earn or float(gain) <= -_f("FORTRESS_EARNINGS_SEVERE_ABORT_LOSS", 0.045))
    ):
        return True, "+".join(votes)
    return False, f"votes={len(votes)}/{need} ({','.join(votes) or 'none'})"


def _trade_row(symbol: str) -> dict[str, Any]:
    """Last saved MFE / scale-out flag for an open name. Empty if we have not seen it."""
    from pathlib import Path
    import json

    path = Path(os.getenv("TRADE_QUALITY_PATH", "data/ops/trade_quality.json"))
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    row = (doc.get("trades") or {}).get(str(symbol or "").upper())
    return row if isinstance(row, dict) else {}


def decide_exit(
    symbol: str,
    *,
    p_adj: float,
    gain: float,
    take_profit_pct: float,
    stop_loss_pct: float,
    pred: int | None = None,
    better_candidate_waiting: bool = False,
    signal_want_sell: bool = False,
    bars_held: float | None = None,
    session_gap: float | None = None,
    now_et=None,
    session_pnl: float | None = None,
) -> ExitDecision:
    """Single decision for open long — priority: thesis death > stop > TP/rotate > signal."""
    # 1) Confirmed thesis death (not noise)
    dead, why = thesis_death_confirmed(
        symbol, p_adj=p_adj, gain=gain, pred=pred, session_gap=session_gap, now_et=now_et
    )
    if dead:
        return ExitDecision("thesis_death", why, trim_frac=1.0, noise=False)

    # 2) Hard stop (always honored — structural risk)
    if float(gain) <= -abs(float(stop_loss_pct)):
        return ExitDecision(
            "stop_loss",
            f"gain={gain:.4f}<=-sl={stop_loss_pct:.4f}",
            trim_frac=1.0,
        )

    # Model already says this long is wrong and the loss is real — don't wait for the wide stop.
    if float(gain) <= -_f("FORTRESS_EARLY_CUT_PCT", 0.012) and float(p_adj) < _f(
        "FORTRESS_EARLY_CUT_MAX_P", 0.48
    ):
        return ExitDecision(
            "stop_loss",
            f"early_cut gain={gain:.4f} p={float(p_adj):.3f}",
            trim_frac=1.0,
        )

    # Day is already red: cut open losers before they turn a small red into a large one.
    # Past the daily-loss line, every loser goes. Winners stay on the trail.
    if session_pnl is not None and float(session_pnl) <= -_f("FORTRESS_RED_DAY_SESSION_PCT", 0.005):
        deep = float(session_pnl) <= -_f("FORTRESS_RED_DAY_FLATTEN_PCT", 0.008)
        # A -0.3% gate left a book of -1% names unsold. That is the large day.
        red_cut = 0.0 if deep else _f("FORTRESS_RED_DAY_CUT_PCT", 0.0015)
        if float(gain) < 0 and float(gain) <= -abs(red_cut):
            return ExitDecision(
                "stop_loss",
                f"red_day_cut session={float(session_pnl):.4f} gain={gain:.4f}",
                trim_frac=1.0,
            )

    row = _trade_row(symbol)
    mfe = max(float(gain), float(row.get("mfe") or gain))
    arm = _f("FORTRESS_TRAIL_ARM", 0.012)
    # 3) Once a trade has been up, don't give it back into a loser, and don't
    #    sit through a deep pullback from the high. Full target still wins below.
    if mfe >= arm and float(gain) <= mfe - _f("FORTRESS_TRAIL_GIVEBACK", 0.007):
        return ExitDecision(
            "take_profit",
            f"trail mfe={mfe:.4f} gain={gain:.4f}",
            trim_frac=1.0,
        )
    if mfe >= arm and float(gain) <= _f("FORTRESS_BREAKEVEN_LOCK", 0.001):
        return ExitDecision(
            "take_profit",
            f"breakeven_lock mfe={mfe:.4f} gain={gain:.4f}",
            trim_frac=1.0,
        )

    # 4) Full take-profit
    if float(gain) >= abs(float(take_profit_pct)):
        return ExitDecision(
            "take_profit",
            f"gain={gain:.4f}>=tp={take_profit_pct:.4f}",
            trim_frac=1.0,
        )

    # 5) Scale-out once. Repeating it every pass chopped winners at the first green tick.
    scale_pct = _f("FORTRESS_SCALE_OUT_PCT", 0.008)  # +0.8%
    rotate_pct = _f("FORTRESS_ROTATE_MIN_GAIN", 0.006)
    if (
        float(gain) >= scale_pct
        and _b("FORTRESS_SCALE_OUT_ENABLED", True)
        and not row.get("scaled")
    ):
        frac = _f("FORTRESS_SCALE_OUT_FRAC", 0.50)
        return ExitDecision(
            "scale_out",
            f"scale_out gain={gain:.4f} trim={frac:.0%}",
            trim_frac=frac,
        )
    if (
        better_candidate_waiting
        and float(gain) >= rotate_pct
        and _b("FORTRESS_ROTATE_ON_PROFIT", True)
    ):
        frac = _f("FORTRESS_ROTATE_TRIM_FRAC", 0.40)
        return ExitDecision(
            "scale_out",
            f"rotate_for_better_name gain={gain:.4f}",
            trim_frac=frac,
        )

    # 5) Signal sell — noise filter (min hold bars / require model+pressure)
    if signal_want_sell:
        min_bars = _f("FORTRESS_SIGNAL_SELL_MIN_BARS", 3)
        if bars_held is not None and bars_held < min_bars:
            return ExitDecision(
                "noise_hold",
                f"signal_sell_too_early bars={bars_held:.1f}<{min_bars}",
                noise=True,
            )
        # Need model weak AND either mild pressure or pred flip — avoid lone flicker
        if _b("FORTRESS_SIGNAL_SELL_CONFIRM", True):
            pressure = _pressure_score(symbol)
            pred_bad = pred is not None and int(pred) != 1
            if float(p_adj) > _f("FORTRESS_SELL_MAX_P", 0.52) and not pred_bad:
                return ExitDecision("noise_hold", "p_adj_flicker_only", noise=True)
            if pressure < _f("FORTRESS_SIGNAL_SELL_MIN_PRESSURE", 0.35) and not pred_bad:
                if float(gain) > -_f("FORTRESS_SIGNAL_SELL_MIN_LOSS", 0.004):
                    return ExitDecision(
                        "noise_hold",
                        "weak_model_without_pressure_or_loss",
                        noise=True,
                    )
        return ExitDecision("signal_sell", f"confirmed_signal_sell p={p_adj:.3f}", trim_frac=1.0)

    return ExitDecision("hold", "no_exit", trim_frac=0.0)


def update_trade_quality(
    symbol: str,
    *,
    p_adj: float,
    gain: float | None,
    action: str,
    reason: str,
    entry_p: float | None = None,
    filled: bool = False,
) -> dict[str, Any]:
    """Persist rolling trade quality scorecard for open / recent names."""
    from pathlib import Path
    import json

    path = Path(os.getenv("TRADE_QUALITY_PATH", "data/ops/trade_quality.json"))
    path.parent.mkdir(parents=True, exist_ok=True)
    doc: dict[str, Any] = {"updated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "trades": {}}
    if path.is_file():
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    trades = doc.setdefault("trades", {})
    row = trades.get(symbol.upper(), {})
    g = float(gain) if gain is not None else None
    mfe = row.get("mfe")
    mae = row.get("mae")
    if g is not None:
        mfe = g if mfe is None else max(float(mfe), g)
        mae = g if mae is None else min(float(mae), g)
    # Quality: reward MFE, punish MAE, reward staying above entry thesis p
    quality = 0.5
    if mfe is not None and mae is not None:
        quality = max(0.0, min(1.0, 0.5 + float(mfe) * 8.0 + float(mae) * 4.0 + (float(p_adj) - 0.5)))
    row.update(
        {
            "symbol": symbol.upper(),
            "p_adj": float(p_adj),
            "gain": g,
            "mfe": mfe,
            "mae": mae,
            "quality": quality,
            "last_action": action,
            "last_reason": reason,
            "scaled": bool(row.get("scaled") or (action == "scale_out" and filled)),
            "entry_p": entry_p if entry_p is not None else row.get("entry_p"),
            "updated_utc": doc["updated_utc"],
        }
    )
    trades[symbol.upper()] = row
    doc["trades"] = trades
    doc["updated_utc"] = row["updated_utc"]
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return row
