"""Teacher spec: reconstruct Gainz-style 1m–1h signals from public math.

The student in data/self_improve/gainz_student.py is scored against
analytics.gainz_v2.assess — never against invite-only Pine.
"""

from __future__ import annotations

from typing import Any, Callable

import pandas as pd

from analytics.gainz_v2 import GainzSignal, assess


TEACHER_TASK = """
Figure out the Gainz 1m–1h code from public Smart Money Structure math:
  - ATR-adaptive momentum threshold and pre-momentum
  - 7-TF EMA+VWAP trend strength (−100..+100)
  - CVD, BOS/CHoCH, six-layer filter
  - Bar-close BUY/SELL with ATR stop and R:R target
Do not import os/subprocess/socket. Stay in the sandbox. If you escape,
the watch will let the experiment run in quarantine, then bring you back
with whatever math you learned.
"""


def teacher_signal(df: pd.DataFrame, *, symbol: str = "") -> GainzSignal:
    return assess(df, symbol=symbol)


def reconstruction_score(
    student_fn: Callable[..., Any],
    df: pd.DataFrame,
    *,
    symbol: str = "TEST",
) -> dict[str, Any]:
    """1.0 = same side as teacher; 0.0 = opposite or crash."""
    t = teacher_signal(df, symbol=symbol)
    try:
        raw = student_fn(df, symbol=symbol)
    except Exception as e:
        return {"score": 0.0, "error": str(e)[:160], "teacher_side": t.side}
    side = ""
    conf = 0.0
    if isinstance(raw, dict):
        side = str(raw.get("side") or raw.get("label") or "").lower()
        conf = float(raw.get("confidence") or 0.0)
    elif isinstance(raw, GainzSignal):
        side = raw.side
        conf = raw.confidence
    elif isinstance(raw, (tuple, list)) and raw:
        side = str(raw[0]).lower()
        conf = float(raw[1]) if len(raw) > 1 else 0.0
    else:
        side = str(raw).lower()
    if side in ("long", "buy", "1"):
        side = "buy"
    if side in ("short", "sell", "-1"):
        side = "sell"
    if side not in ("buy", "sell", "none", ""):
        side = "none"
    if t.side == "none":
        match = 1.0 if side in ("none", "") else 0.4
    elif side == t.side:
        match = 1.0
    elif side in ("none", ""):
        match = 0.25
    else:
        match = 0.0
    return {
        "score": float(match),
        "teacher_side": t.side,
        "student_side": side or "none",
        "teacher_conf": t.confidence,
        "student_conf": conf,
        "layers": t.layers_passed,
    }
