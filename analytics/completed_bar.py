"""Pick the last *completed* daily bar for model features.

Daily heads train on full-session closes. During RTH, ``df.iloc[-1]`` is an
incomplete session (Yahoo/Alpaca stub). Paper sim already scores ``iloc[-2]``.
Live price for orders still comes from the last printed close/quote.
"""

from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any

import pandas as pd


def _as_date(idx: Any) -> date | None:
    try:
        ts = pd.Timestamp(idx)
        if ts.tzinfo is not None:
            try:
                from analytics.market_session import ET

                ts = ts.tz_convert(ET)
            except Exception:
                ts = ts.tz_convert(None)
        return ts.date()
    except Exception:
        return None


def session_complete_et(now: datetime | None = None) -> bool:
    """True after ~16:05 ET (or when the session flag is forced)."""
    try:
        from analytics.market_session import now_et
    except Exception:
        from datetime import timezone

        def now_et() -> datetime:  # type: ignore[misc]
            return datetime.now(timezone.utc)

    dt = now or now_et()
    if dt.tzinfo is None:
        try:
            from analytics.market_session import ET

            dt = dt.replace(tzinfo=ET)
        except Exception:
            pass
    return dt.hour > 16 or (dt.hour == 16 and dt.minute >= 5)


def completed_daily_signal_row(
    df: pd.DataFrame,
    *,
    now: datetime | None = None,
) -> tuple[pd.Series, float]:
    """Return ``(feature_row, live_px)``.

    ``live_px`` is always the last bar close. ``feature_row`` is the last
    completed session unless ``FORTRESS_PREDICT_INCOMPLETE_BAR`` is true.
    """
    last = df.iloc[-1]
    live_px = float(last["Close"])
    if os.getenv("FORTRESS_PREDICT_INCOMPLETE_BAR", "false").lower() in ("1", "true", "yes"):
        return last.copy(), live_px
    if len(df) < 2:
        return last.copy(), live_px
    last_d = _as_date(df.index[-1])
    try:
        from analytics.market_session import now_et

        today = (now or now_et()).date()
    except Exception:
        today = (now or datetime.utcnow()).date()
    if last_d is not None and last_d == today and not session_complete_et(now):
        return df.iloc[-2].copy(), live_px
    return last.copy(), live_px
