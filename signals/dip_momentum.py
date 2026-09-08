"""Price momentum — dip guard (falling knives) + rally continuation (trend persists).

Negative momentum: a stock that just dropped can keep dropping.
Positive momentum: a stock that is rising can keep rising — don't fade it on short holds.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass

import pandas as pd


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default


def _i(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def _b(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes")


@dataclass
class DipMomentumContext:
    ret_1d: float
    ret_3d: float
    ret_5d: float
    ret_20d: float
    consecutive_down_days: int
    falling_knife: bool
    knife_severity: float
    stabilized: bool
    momentum_turn: bool
    longer_term_dip: bool
    horizon_scale: float
    dip_multiplier: float
    rationale: str

    def to_dict(self) -> dict:
        return asdict(self)


def _ret(closes: pd.Series, n: int) -> float:
    if closes is None or len(closes) < n + 1:
        return 0.0
    base = float(closes.iloc[-1 - n])
    if base <= 0:
        return 0.0
    return float(closes.iloc[-1] / base - 1.0)


def _consecutive_down_days(closes: pd.Series, max_look: int = 8) -> int:
    if closes is None or len(closes) < 3:
        return 0
    rets = closes.pct_change().fillna(0.0)
    n = 0
    for i in range(len(rets) - 1, max(0, len(rets) - max_look - 1), -1):
        if float(rets.iloc[i]) < -0.001:
            n += 1
        else:
            break
    return n


def dip_horizon_scale() -> float:
    """Dip tilt is longer-horizon — scale down when hold window is very short."""
    hold = _f("HOLD_DAYS_DEFAULT", 5.0)
    min_hold = _f("DIP_MIN_HOLD_DAYS", 10.0)
    if hold >= min_hold:
        return 1.0
    floor = _f("DIP_HORIZON_SCALE_FLOOR", 0.25)
    return max(floor, hold / max(min_hold, 1.0))


def assess_dip_momentum(
    closes: pd.Series,
    *,
    ret_20d: float | None = None,
    ret_60d: float | None = None,
    drawdown_52w: float | None = None,
) -> DipMomentumContext:
    close = closes.astype(float) if closes is not None else pd.Series(dtype=float)
    r1 = _ret(close, 1)
    r3 = _ret(close, 3)
    r5 = _ret(close, 5)
    r20 = float(ret_20d) if ret_20d is not None else _ret(close, 20)
    r60 = float(ret_60d) if ret_60d is not None else _ret(close, 60)
    consec = _consecutive_down_days(close)

    knife_1d = _f("DIP_KNIFE_1D", -0.025)
    knife_3d = _f("DIP_KNIFE_3D", -0.055)
    knife_5d = _f("DIP_KNIFE_5D", -0.09)
    knife_consec = _i("DIP_KNIFE_CONSEC_DOWN", 3)
    accel_gap = _f("DIP_KNIFE_ACCEL_GAP", 0.035)

    accel = r5 < r20 - accel_gap and r5 < knife_5d * 0.5
    fresh_panic = r1 <= knife_1d or (r3 <= knife_3d and r3 <= r5)
    waterfall = consec >= knife_consec and r3 < 0

    falling_knife = bool(fresh_panic or waterfall or accel)
    knife_severity = 0.0
    if falling_knife:
        knife_severity = min(
            1.0,
            max(
                0.35,
                abs(min(r1, 0.0)) / abs(knife_1d),
                abs(min(r3, 0.0)) / abs(knife_3d),
                consec / max(knife_consec, 1),
            ),
        )

    momentum_turn = r5 > r20 + _f("DIP_MOM_TURN_GAP", 0.025) and r1 > _f("DIP_MOM_TURN_1D", -0.005)
    short_stabil = r3 >= r5 * _f("DIP_STABIL_RATIO", 0.88) or r1 > _f("DIP_STABIL_1D", 0.004)
    stabilized = (not falling_knife) and (momentum_turn or short_stabil)

    look = min(len(close) - 2, _i("DIP_DEEP_HIGH_LOOKBACK", 60))
    look = max(22, look)
    if len(close) >= look + 2:
        roll_high = float(close.iloc[-(look + 2) : -2].max())
        last = float(close.iloc[-2])
        dd_local = last / roll_high - 1.0 if roll_high > 0 else 0.0
    else:
        dd_local = 0.0
    dd = drawdown_52w if drawdown_52w is not None else dd_local
    longer_start = _f("DIP_LONGER_START_DD", -0.08)
    longer_ret20 = _f("DIP_LONGER_RET20", -0.06)
    longer_term_dip = dd <= longer_start or r20 <= longer_ret20 or r60 <= _f("DIP_LONGER_RET60", -0.12)

    horizon_scale = dip_horizon_scale()
    dip_multiplier = 1.0
    parts: list[str] = []

    if falling_knife:
        dip_multiplier = max(0.0, 1.0 - knife_severity)
        parts.append("falling_knife")
    elif not longer_term_dip:
        dip_multiplier = _f("DIP_SHORT_PULLBACK_MULT", 0.35)
        parts.append("short_pullback_only")
    elif not stabilized:
        dip_multiplier = _f("DIP_UNSTABILIZED_MULT", 0.55)
        parts.append("await_stabilization")
    else:
        dip_multiplier = 1.0
        if momentum_turn:
            parts.append("momentum_turn")
        else:
            parts.append("stabilized")

    if horizon_scale < 0.99:
        dip_multiplier *= horizon_scale
        parts.append(f"horizon_x{horizon_scale:.2f}")

    return DipMomentumContext(
        ret_1d=r1,
        ret_3d=r3,
        ret_5d=r5,
        ret_20d=r20,
        consecutive_down_days=consec,
        falling_knife=falling_knife,
        knife_severity=float(knife_severity),
        stabilized=stabilized,
        momentum_turn=momentum_turn,
        longer_term_dip=longer_term_dip,
        horizon_scale=float(horizon_scale),
        dip_multiplier=float(max(0.0, min(1.0, dip_multiplier))),
        rationale="+".join(parts) if parts else "neutral",
    )


def apply_dip_momentum_filter(
    closes: pd.Series,
    raw_dip: float,
    **kwargs: object,
) -> tuple[float, DipMomentumContext]:
    ctx = assess_dip_momentum(closes, **kwargs)  # type: ignore[arg-type]
    return float(max(0.0, min(1.0, raw_dip * ctx.dip_multiplier))), ctx


def blocks_bottom_fisher_trade(
    *,
    ret_1d: float,
    ret_5d: float,
    ret_20d: float,
    recovery_score: float,
    reversal_bar: float = 0.0,
    trend_stabilizing: float = 0.0,
    momentum_turn_score: float = 0.0,
) -> tuple[bool, str]:
    """Hard gate for bottom-fisher entries — no catch-a-falling-knife without proof of turn."""
    if not _b("DIP_MOMENTUM_GATE", True):
        return False, ""
    knife_1d = _f("BOTTOM_FISHER_KNIFE_1D", -0.03)
    knife_5d = _f("BOTTOM_FISHER_KNIFE_5D", -0.10)
    if ret_1d <= knife_1d and reversal_bar < _f("BOTTOM_FISHER_MIN_REVERSAL", 0.35):
        return True, f"fresh drop {ret_1d*100:.1f}% 1d — wait for reversal"
    if ret_5d <= knife_5d and ret_5d < ret_20d - _f("DIP_KNIFE_ACCEL_GAP", 0.035):
        if momentum_turn_score < _f("BOTTOM_FISHER_MIN_MOM_TURN", 0.20):
            return True, "5d momentum still accelerating down"
    if ret_20d > _f("BOTTOM_FISHER_MIN_WEAK_20D", -0.04):
        if recovery_score < _f("BOTTOM_FISHER_MIN_RECOVERY_LONG", 0.55):
            return True, "not a longer-term washout yet"
    if trend_stabilizing < _f("BOTTOM_FISHER_MIN_STABIL", 0.15) and momentum_turn_score < 0.2:
        if ret_5d < -0.04:
            return True, "no stabilization after recent weakness"
    return False, ""


@dataclass
class RallyMomentumContext:
    ret_1d: float
    ret_3d: float
    ret_5d: float
    ret_20d: float
    consecutive_up_days: int
    momentum_rising: bool
    rally_continuation: bool
    rally_bonus: float
    rationale: str

    def to_dict(self) -> dict:
        return asdict(self)


def _consecutive_up_days(closes: pd.Series, max_look: int = 8) -> int:
    if closes is None or len(closes) < 3:
        return 0
    rets = closes.pct_change().fillna(0.0)
    n = 0
    for i in range(len(rets) - 1, max(0, len(rets) - max_look - 1), -1):
        if float(rets.iloc[i]) > 0.001:
            n += 1
        else:
            break
    return n


def assess_rally_momentum(
    closes: pd.Series,
    *,
    ret_20d: float | None = None,
    mom_5d: float | None = None,
) -> RallyMomentumContext:
    """Upward momentum continuation — trend can persist (mirror of falling-knife logic)."""
    close = closes.astype(float) if closes is not None else pd.Series(dtype=float)
    r1 = _ret(close, 1)
    r3 = _ret(close, 3)
    r5 = float(mom_5d) if mom_5d is not None else _ret(close, 5)
    r20 = float(ret_20d) if ret_20d is not None else _ret(close, 20)
    consec = _consecutive_up_days(close)

    up_1d = _f("RALLY_MIN_1D", 0.004)
    up_3d = _f("RALLY_MIN_3D", 0.012)
    accel_gap = _f("RALLY_ACCEL_GAP", 0.025)

    momentum_rising = r5 > r20 + accel_gap and r3 > 0
    fresh_push = r1 >= up_1d or (r3 >= up_3d and r3 >= r5 * 0.85)
    waterfall_up = consec >= _i("RALLY_CONSEC_UP", 2) and r3 > 0

    rally_continuation = bool((momentum_rising and fresh_push) or waterfall_up)

    bonus = 0.0
    parts: list[str] = []
    if rally_continuation:
        bonus = min(
            1.0,
            0.45
            + min(0.35, max(r1, 0.0) / max(up_1d, 1e-9) * 0.12)
            + min(0.25, max(r5 - r20, 0.0) * 4.0)
            + min(0.15, consec * 0.05),
        )
        parts.append("rally_continuation")
    elif r5 > 0 and r1 > -0.005:
        bonus = min(0.45, max(0.0, r5 * 3.0))
        parts.append("positive_drift")
    elif r5 < -0.03 and r1 < -0.01:
        bonus = 0.0
        parts.append("weak_momentum")

    return RallyMomentumContext(
        ret_1d=r1,
        ret_3d=r3,
        ret_5d=r5,
        ret_20d=r20,
        consecutive_up_days=consec,
        momentum_rising=momentum_rising,
        rally_continuation=rally_continuation,
        rally_bonus=float(max(0.0, min(1.0, bonus))),
        rationale="+".join(parts) if parts else "neutral",
    )


def rally_score_bonus(ctx: RallyMomentumContext, *, hold_days: int | None = None) -> float:
    """Short holds lean harder into continuation; long holds still get a modest boost."""
    hold = float(hold_days if hold_days is not None else _f("HOLD_DAYS_DEFAULT", 5.0))
    if hold <= 1.0:
        scale = _f("RALLY_SCALE_1D", 0.55)
    elif hold <= 5.0:
        scale = _f("RALLY_SCALE_1W", 0.45)
    elif hold <= 20.0:
        scale = _f("RALLY_SCALE_1M", 0.35)
    else:
        scale = _f("RALLY_SCALE_2M", 0.28)
    if ctx.rally_continuation:
        return float(min(1.0, ctx.rally_bonus * scale))
    return float(min(0.5, ctx.rally_bonus * scale * 0.7))


def family_momentum_ok(row: dict, hold_days: int) -> tuple[bool, str]:
    """Family display gate — optional. Default off: if model says 55%+ up, show it."""
    if not _b("FAMILY_MOMENTUM_GATE", False):
        return True, ""
    mom5 = float(row.get("momentum_5d", 0))
    r1 = float(row.get("momentum_ret_1d", row.get("ret_1d", 0)))
    if hold_days <= 1:
        if mom5 < _f("FAMILY_1D_MIN_MOM5", -0.06):
            return False, f"1d falling knife (mom5={mom5*100:.1f}%)"
        if r1 < _f("FAMILY_1D_BLOCK_1D", -0.025):
            return False, f"down today ({r1*100:.1f}%) — wait for turn"
    elif hold_days <= 5:
        if mom5 < _f("FAMILY_1W_MIN_MOM5", -0.08):
            return False, f"weekly falling knife (mom5={mom5*100:.1f}%)"
    return True, ""


def family_momentum_rank_boost(row: dict, hold_days: int) -> float:
    """Light tie-breaker only — model probability still dominates family picks."""
    scale = _f("FAMILY_MOMENTUM_RANK_SCALE", 0.25)
    mom5 = float(row.get("momentum_5d", 0))
    rally = float(row.get("rally_signal", row.get("rally_bonus", 0)))
    if hold_days <= 1:
        raw = rally * 0.6 + max(0.0, mom5) * 0.8
    elif hold_days <= 5:
        raw = rally * 0.5 + max(0.0, mom5) * 0.6
    else:
        raw = rally * 0.35 + max(0.0, mom5) * 0.4
    return float(raw * scale)
