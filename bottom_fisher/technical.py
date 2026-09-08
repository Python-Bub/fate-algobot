"""Technical recovery signals for beaten-down names."""

from __future__ import annotations

import os
from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd

from bottom_fisher.config import BottomFisherConfig
from bottom_fisher.universe import BottomCandidate
from signals.undercut_rally import detect_undercut_rally
from utils import log


@dataclass
class RecoverySignals:
    ticker: str
    recovery_score: float
    capitulation: float
    mean_reversion_z: float
    ur_score: float
    rsi: float
    reversal_bar: float
    volume_climax: float
    trend_stabilizing: float
    momentum_turn_score: float
    rationale: str

    def to_dict(self) -> dict:
        return asdict(self)


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default


def score_recovery(candidate: BottomCandidate, df: pd.DataFrame | None = None) -> RecoverySignals:
    """Score [0,1] recovery potential on a bottom-universe name."""
    t = candidate.ticker
    if df is None:
        try:
            from data_platform.market_prices import fetch_period

            df = fetch_period(t, period="1y", interval="1d")
        except Exception as e:
            log.debug("[BOTTOM_FISHER] ohlc %s: %s", t, e)
            df = pd.DataFrame()
    if df is None or df.empty or len(df) < 30:
        return RecoverySignals(t, 0.0, 0, 0, 0, 50, 0, 0, 0, 0, "insufficient_bars")

    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]

    close_name = "Close" if "Close" in df.columns else ("Adj Close" if "Adj Close" in df.columns else None)
    if close_name is None:
        return RecoverySignals(t, 0.0, 0, 0, 0, 50, 0, 0, 0, 0, "no_close")
    close = df[close_name].astype(float)
    high = df["High"].astype(float) if "High" in df.columns else close
    low = df["Low"].astype(float) if "Low" in df.columns else close
    vol = df["Volume"].astype(float) if "Volume" in df.columns else pd.Series(1.0, index=df.index)

    ret = close.pct_change().fillna(0)
    rsi = _rsi(close, 14)
    rsi_last = float(rsi.iloc[-1])

    vol_ma = vol.rolling(20, min_periods=10).mean()
    vol_ratio = float(vol.iloc[-1] / vol_ma.iloc[-1]) if vol_ma.iloc[-1] > 0 else 1.0
    down_day = float(ret.iloc[-1]) < -0.01
    vol_climax = min(1.0, max(0.0, (vol_ratio - 1.2) / 2.5)) if down_day else min(1.0, max(0.0, (vol_ratio - 1.0) / 3.0))

    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    stabil = 0.0
    if len(ema20) > 5 and len(ema50) > 5:
        slope20 = float(ema20.iloc[-1] / ema20.iloc[-6] - 1.0)
        if slope20 > -0.02 and float(ema20.iloc[-1]) >= float(ema50.iloc[-1]) * 0.97:
            stabil = min(1.0, 0.5 + slope20 * 10)

    z = _mean_reversion_z(close, window=int(os.getenv("BOTTOM_FISHER_Z_WINDOW", "20")))
    z_score = min(1.0, max(0.0, (-z - 1.0) / 2.5)) if z < -0.5 else 0.0

    ur = detect_undercut_rally(df)
    ur_s = float(ur.score) if ur.detected else 0.0

    rev = 0.0
    if len(close) >= 3:
        prev_low = float(low.iloc[-2])
        today_close = float(close.iloc[-1])
        if today_close > prev_low and float(ret.iloc[-1]) > 0.005:
            rev = min(1.0, float(ret.iloc[-1]) * 20)

    cap = 0.0
    if rsi_last < 32 and candidate.drawdown_52w < -0.15:
        cap = min(1.0, (32 - rsi_last) / 20 + abs(candidate.drawdown_52w) * 0.5)

    dd_bonus = min(1.0, max(0.0, abs(candidate.drawdown_52w) * 1.2))
    mom_turn = 0.0
    if candidate.ret_20d > candidate.ret_60d + 0.02:
        mom_turn = min(1.0, (candidate.ret_20d - candidate.ret_60d) * 3)
    elif candidate.ret_5d > candidate.ret_20d + 0.025:
        mom_turn = min(1.0, (candidate.ret_5d - candidate.ret_20d) * 4)

    ou_term = 0.0
    try:
        from analytics.trade_math import falling_knife, ou_half_life

        logp = np.log(np.clip(close.to_numpy(dtype=float), 1e-9, None))
        hl = ou_half_life(logp)
        if hl < 8:
            ou_term = 1.0
        elif hl < 20:
            ou_term = 0.65
        elif hl < 40:
            ou_term = 0.30
        if falling_knife(candidate.ret_1d, candidate.ret_5d, candidate.ret_20d):
            ou_term *= 0.15
    except Exception:
        ou_term = 0.0

    w_cap = _f("BOTTOM_FISHER_W_CAPITULATION", 0.16)
    w_z = _f("BOTTOM_FISHER_W_ZSCORE", 0.14)
    w_ur = _f("BOTTOM_FISHER_W_UR", 0.18)
    w_rev = _f("BOTTOM_FISHER_W_REVERSAL", 0.13)
    w_vol = _f("BOTTOM_FISHER_W_VOL_CLIMAX", 0.08)
    w_stab = _f("BOTTOM_FISHER_W_STABILIZE", 0.08)
    w_dd = _f("BOTTOM_FISHER_W_DRAWDOWN", 0.05)
    w_mom = _f("BOTTOM_FISHER_W_MOM_TURN", 0.08)
    w_ou = _f("BOTTOM_FISHER_W_OU", 0.10)

    recovery = (
        w_cap * cap
        + w_z * z_score
        + w_ur * ur_s
        + w_rev * rev
        + w_vol * vol_climax
        + w_stab * stabil
        + w_dd * dd_bonus
        + w_mom * mom_turn
        + w_ou * ou_term
    )
    recovery = float(max(0.0, min(1.0, recovery)))

    try:
        from signals.dip_momentum import assess_dip_momentum, blocks_bottom_fisher_trade

        ctx = assess_dip_momentum(
            close,
            ret_20d=candidate.ret_20d,
            ret_60d=candidate.ret_60d,
            drawdown_52w=candidate.drawdown_52w,
        )
        recovery *= ctx.dip_multiplier
        blocked, block_reason = blocks_bottom_fisher_trade(
            ret_1d=candidate.ret_1d,
            ret_5d=candidate.ret_5d,
            ret_20d=candidate.ret_20d,
            recovery_score=recovery,
            reversal_bar=float(rev),
            trend_stabilizing=float(stabil),
            momentum_turn_score=float(mom_turn),
        )
        if blocked:
            recovery *= 0.25
            if ctx.falling_knife:
                recovery = min(recovery, 0.12)
        try:
            from signals.dip_momentum import assess_rally_momentum, rally_score_bonus

            rally_ctx = assess_rally_momentum(close, ret_20d=candidate.ret_20d, mom_5d=candidate.ret_5d)
            recovery += _f("BOTTOM_FISHER_W_RALLY", 0.02) * rally_score_bonus(
                rally_ctx, hold_days=int(os.getenv("BOTTOM_FISHER_HOLD_DAYS", "20"))
            )
            recovery = float(max(0.0, min(1.0, recovery)))
        except Exception:
            pass
    except Exception:
        block_reason = ""
        ctx = None

    parts = []
    if cap > 0.3:
        parts.append("capitulation")
    if ur_s > 0.35:
        parts.append("undercut_rally")
    if rev > 0.3:
        parts.append("reversal_bar")
    if z_score > 0.3:
        parts.append("mean_reversion")
    if mom_turn > 0.25:
        parts.append("momentum_turn")
    try:
        if ctx and ctx.falling_knife:
            parts.append("knife_penalty")
        if block_reason:
            parts.append(f"blocked:{block_reason[:40]}")
    except NameError:
        pass

    return RecoverySignals(
        ticker=t,
        recovery_score=recovery,
        capitulation=float(cap),
        mean_reversion_z=float(z),
        ur_score=float(ur_s),
        rsi=float(rsi_last),
        reversal_bar=float(rev),
        volume_climax=float(vol_climax),
        trend_stabilizing=float(stabil),
        momentum_turn_score=float(mom_turn),
        rationale="+".join(parts) if parts else "weak",
    )


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0).rolling(period, min_periods=period).mean()
    down = (-delta.clip(upper=0)).rolling(period, min_periods=period).mean()
    rs = up / down.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _mean_reversion_z(close: pd.Series, window: int = 20) -> float:
    if len(close) < window + 2:
        return 0.0
    ma = close.rolling(window).mean()
    sd = close.rolling(window).std()
    if float(sd.iloc[-1]) <= 0:
        return 0.0
    return float((close.iloc[-1] - ma.iloc[-1]) / sd.iloc[-1])
