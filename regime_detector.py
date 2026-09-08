"""
Market regime: VIX level + simple HMM optional; RegimeSwitch adjusts sizing and stops.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum

import numpy as np
import pandas as pd

from utils import log


class Regime(str, Enum):
    BULL_TREND = "bull_trend"
    BEAR_TREND = "bear_trend"
    HIGH_VOL_RANGE = "high_vol_range"
    LOW_VOL_RANGE = "low_vol_range"


@dataclass
class RegimeState:
    name: Regime
    vix: float
    position_scale: float
    stop_widen: float


def fetch_vix() -> float:
    try:
        from data_platform.market_prices import fetch_period

        v = fetch_period("^VIX", period="5d", interval="1d")
        if v.empty:
            return 20.0
        return float(v["Close"].iloc[-1])
    except Exception:
        return 20.0


def simple_regime_from_spy(df_spy: pd.DataFrame, vix: float | None = None) -> RegimeState:
    vix = vix if vix is not None else fetch_vix()
    if df_spy.empty or "Close" not in df_spy.columns:
        return RegimeState(Regime.LOW_VOL_RANGE, vix, 1.0, 1.0)

    c = df_spy["Close"]
    ema20 = c.ewm(20).mean().iloc[-1]
    ema50 = c.ewm(50).mean().iloc[-1]
    ret20 = c.pct_change(20).iloc[-1]
    vol20 = c.pct_change().rolling(20).std().iloc[-1]

    if vix > 30:
        stop_widen = float(os.getenv("REGIME_VIX30_STOP_MULT", "1.5"))
        scale = float(os.getenv("REGIME_VIX30_SIZE_MULT", "0.5"))
    else:
        stop_widen = 1.0
        scale = 1.0

    if ema20 > ema50 and ret20 > 0:
        name = Regime.BULL_TREND
    elif ema20 < ema50 and ret20 < 0:
        name = Regime.BEAR_TREND
    elif (vol20 or 0) > float(os.getenv("REGIME_HIGH_VOL", "0.02")):
        name = Regime.HIGH_VOL_RANGE
    else:
        name = Regime.LOW_VOL_RANGE

    st = RegimeState(name, vix, scale, stop_widen)
    log.info("[REGIME] %s VIX=%.2f scale=%.2f stop_mult=%.2f", name.value, vix, scale, stop_widen)
    return st


def hmm_regime(returns: pd.Series, n_states: int = 4) -> np.ndarray | None:
    try:
        from hmmlearn.hmm import GaussianHMM

        x = returns.dropna().values.reshape(-1, 1)
        if len(x) < 50:
            return None
        model = GaussianHMM(n_components=n_states, covariance_type="diag", n_iter=200, random_state=42)
        model.fit(x)
        return model.predict(x)
    except ImportError:
        log.info("[REGIME] hmmlearn not installed; pip install hmmlearn for HMM regimes")
        return None
    except Exception as e:
        log.warning("[REGIME] HMM failed: %s", e)
        return None
