"""US equity session gate — stop orders outside allowed windows (RTH / extended / closed)."""

from __future__ import annotations

import os
from datetime import datetime, time, timedelta
from enum import Enum
from functools import lru_cache
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# US equities (Alpaca extended): pre 04:00–09:30, RTH 09:30–16:00, post 16:00–20:00 ET.
_PRE_OPEN = time(4, 0)
_RTH_OPEN = time(9, 30)
_RTH_CLOSE = time(16, 0)
_POST_CLOSE = time(20, 0)


class Session(str, Enum):
    CLOSED = "closed"
    PRE_MARKET = "pre_market"
    REGULAR = "regular"
    POST_MARKET = "post_market"


def now_et() -> datetime:
    return datetime.now(ET)


def minutes_to_rth_close(dt: datetime | None = None) -> float | None:
    """Minutes until 16:00 ET on a trading day; None if weekend / already past close."""
    dt = dt or now_et()
    if not is_trading_day(dt):
        return None
    close_dt = dt.replace(hour=_RTH_CLOSE.hour, minute=_RTH_CLOSE.minute, second=0, microsecond=0)
    if dt >= close_dt:
        return 0.0
    if dt.time() < _RTH_OPEN:
        return None
    return max(0.0, (close_dt - dt).total_seconds() / 60.0)


def is_trading_day(dt: datetime | None = None) -> bool:
    """Weekday (Mon–Fri ET). Holiday filter is applied via Alpaca clock when enabled."""
    dt = dt or now_et()
    return dt.weekday() < 5


_CLOCK_CACHE: tuple[float, dict] | None = None


def alpaca_clock(*, max_age_sec: float | None = None) -> dict | None:
    """Cached Alpaca /v2/clock — source of truth for open/holiday status."""
    global _CLOCK_CACHE
    import time as _time

    age = float(max_age_sec if max_age_sec is not None else os.getenv("ALPACA_CLOCK_CACHE_SEC", "60"))
    now = _time.time()
    if _CLOCK_CACHE and now - _CLOCK_CACHE[0] < age:
        return dict(_CLOCK_CACHE[1])
    try:
        import requests
        from alpaca_broker import _keys, _normalize_base, _trade_headers

        k, _ = _keys()
        if not k:
            return None
        base = _normalize_base(os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets"))
        r = requests.get(f"{base}/v2/clock", headers=_trade_headers(), timeout=8)
        r.raise_for_status()
        js = r.json() if isinstance(r.json(), dict) else {}
        _CLOCK_CACHE = (now, js)
        return dict(js)
    except Exception:
        # Soft-fail: keep last good clock briefly so a blip does not open the floodgates.
        if _CLOCK_CACHE and now - _CLOCK_CACHE[0] < max(age * 5, 300):
            return dict(_CLOCK_CACHE[1])
        return None


def exchange_is_open(*, for_hft: bool = False) -> tuple[bool, str]:
    """
    Holiday-aware open check. Extended/HFT sessions can still trade when the
    calendar says 'closed' for RTH if TRADE_ALLOW_WHEN_CLOCK_CLOSED is set;
    default is to trust Alpaca clock on weekdays.
    """
    if not is_trading_day():
        return False, "weekend"
    if os.getenv("ALPACA_CLOCK_GATE", "true").lower() not in ("1", "true", "yes"):
        return True, "clock_gate_off"
    clk = alpaca_clock()
    if clk is None:
        return True, "clock_unavailable"  # fail-open to local session math
    if bool(clk.get("is_open")):
        return True, "alpaca_open"
    # Pre/post: Alpaca is_open is False outside RTH — allow when our session mode is extended.
    if for_hft or _mode("TRADE_SESSION_MODE", "rth") == "extended":
        if os.getenv("TRADE_ALLOW_EXTENDED_WHEN_CLOCK_CLOSED", "true").lower() in ("1", "true", "yes"):
            return True, "extended_outside_rth"
    return False, "alpaca_holiday_or_closed"


def auto_unpause_window_open(dt: datetime | None = None) -> tuple[bool, str]:
    """True when AUTO_UNPAUSE should fire (trading day + at/after AUTO_UNPAUSE_ET)."""
    dt = dt or now_et()
    if not is_trading_day(dt):
        return False, "weekend"
    if os.getenv("AUTO_UNPAUSE_TRADING_DAYS", "true").lower() not in ("1", "true", "yes"):
        return False, "disabled"
    unpause_t = _parse_et_time(os.getenv("AUTO_UNPAUSE_ET", "06:00")) or time(6, 0)
    if dt.time() < unpause_t:
        return False, f"before {unpause_t.strftime('%H:%M')} ET"
    return True, "open"


def intel_window_open(dt: datetime | None = None) -> tuple[bool, str]:
    """06:00–20:00 ET weekdays — data/news/LLM prep (not necessarily order routing)."""
    dt = dt or now_et()
    if not is_trading_day(dt):
        return False, "weekend"
    start = _parse_et_time(os.getenv("INTEL_WINDOW_START_ET", "06:00")) or time(6, 0)
    end = _parse_et_time(os.getenv("INTEL_WINDOW_END_ET", "20:00")) or time(20, 0)
    t = dt.time()
    if t < start:
        return False, f"before {start.strftime('%H:%M')} ET intel open"
    if t >= end:
        return False, f"after {end.strftime('%H:%M')} ET"
    return True, "intel_open"


def _parse_et_time(raw: str) -> time | None:
    s = (raw or "").strip()
    if not s:
        return None
    parts = s.split(":")
    try:
        if len(parts) == 2:
            return time(int(parts[0]), int(parts[1]))
        if len(parts) == 3:
            return time(int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError:
        return None
    return None


def _fortress_trade_start() -> str:
    default = (
        "04:00"
        if _mode("TRADE_SESSION_MODE", "rth") == "extended"
        else "09:30"
    )
    return (
        os.getenv("FORTRESS_TRADE_START_ET", "").strip()
        or os.getenv("TRADE_START_ET", "").strip()
        or default
    )


def _within_trade_window(dt: datetime | None = None, *, for_hft: bool = False) -> tuple[bool, str]:
    """TRADE_START_ET / TRADE_END_ET; fortress default 09:00, HFT can use HFT_TRADE_START_ET=04:00."""
    dt = dt or now_et()
    if not is_trading_day(dt):
        return False, "weekend"
    end_s = os.getenv("TRADE_END_ET", "20:00").strip()
    buy_mode = _mode("HFT_TRADE_SESSION" if for_hft else "TRADE_SESSION_MODE", "rth")
    # always/24x7: respect explicit ET window on weekdays (broker may still reject off-hours).
    if buy_mode in ("always", "24x7", "any"):
        t = dt.time()
        if for_hft:
            start_s = (
                os.getenv("HFT_TRADE_START_ET", "").strip()
                or os.getenv("TRADE_START_ET", "").strip()
            )
        else:
            start_s = _fortress_trade_start() or os.getenv("TRADE_START_ET", "").strip()
        start_t = _parse_et_time(start_s) if start_s else None
        end_t = _parse_et_time(end_s) if end_s else None
        if start_t and t < start_t:
            return False, f"before TRADE_START_ET={start_s}"
        if end_t and t >= end_t:
            return False, f"after TRADE_END_ET={end_s}"
        return True, f"always_weekday_{start_s or 'open'}-{end_s or 'close'}"
    if os.getenv("TRADE_WEEKDAY_24X5", "true").lower() in ("1", "true", "yes"):
        t = dt.time()
        end_t = _parse_et_time(end_s) or _POST_CLOSE
        if for_hft:
            start_s = os.getenv("HFT_TRADE_START_ET", "").strip() or os.getenv("TRADE_START_ET", "").strip()
            start_t = _parse_et_time(start_s) if start_s else _PRE_OPEN
            if start_t <= t < end_t:
                return True, f"hft_weekday_{start_t.strftime('%H:%M')}-{end_t.strftime('%H:%M')}"
            return False, f"outside_hft_window_{start_t.strftime('%H:%M')}-{end_t.strftime('%H:%M')}"
        start_t = _parse_et_time(_fortress_trade_start()) or time(9, 0)
        if start_t <= t < end_t:
            return True, f"fortress_weekday_{_fortress_trade_start()}-{end_s or '20:00'}"
        return False, f"before_fortress_start_{_fortress_trade_start()}"
    start_s = (
        os.getenv("HFT_TRADE_START_ET", "").strip()
        if for_hft
        else _fortress_trade_start()
    )
    if not start_s and not end_s:
        return True, "window=open"
    t = dt.time()
    start_t = _parse_et_time(start_s)
    end_t = _parse_et_time(end_s)
    if start_t and t < start_t:
        return False, f"before TRADE_START_ET={start_s}"
    if end_t and t >= end_t:
        return False, f"after TRADE_END_ET={end_s}"
    return True, f"window={start_s or 'open'}-{end_s or 'close'}"


def current_session(dt: datetime | None = None) -> Session:
    dt = dt or now_et()
    if dt.weekday() >= 5:
        return Session.CLOSED
    t = dt.time()
    if _PRE_OPEN <= t < _RTH_OPEN:
        return Session.PRE_MARKET
    if _RTH_OPEN <= t < _RTH_CLOSE:
        return Session.REGULAR
    if _RTH_CLOSE <= t < _POST_CLOSE:
        return Session.POST_MARKET
    return Session.CLOSED


def rth_open_protect_window(dt: datetime | None = None) -> tuple[bool, str]:
    """True for the first N minutes of RTH (default 45) — hold strong premarket names.

    Also true during pre_market itself so we don't soft-exit winners before the bell.
    """
    dt = dt or now_et()
    if not is_trading_day(dt):
        return False, "weekend"
    sess = current_session(dt)
    try:
        protect_min = float(os.getenv("PREMARKET_OPEN_PROTECT_MIN", "45"))
    except (TypeError, ValueError):
        protect_min = 45.0
    if sess == Session.PRE_MARKET:
        return True, "pre_market"
    if sess != Session.REGULAR:
        return False, f"session={sess.value}"
    open_dt = dt.replace(
        hour=_RTH_OPEN.hour, minute=_RTH_OPEN.minute, second=0, microsecond=0
    )
    mins = (dt - open_dt).total_seconds() / 60.0
    if 0 <= mins <= protect_min:
        return True, f"rth_open+{mins:.0f}m"
    return False, f"past_open_protect ({mins:.0f}m)"


def _mode(name: str, default: str) -> str:
    return os.getenv(name, default).strip().lower()


def _session_in_mode(sess: Session, mode: str) -> bool:
    if mode in ("always", "24x7", "any"):
        return True
    if mode == "extended":
        return sess in (Session.PRE_MARKET, Session.REGULAR, Session.POST_MARKET)
    # default: rth
    return sess == Session.REGULAR


def midday_hft_only(dt: datetime | None = None) -> tuple[bool, str]:
    """
    Midday chop (10:15–15:30 ET) is HFT-only — slow intraday/fortress/day-trade buys blocked.
  Tiny gains need subsecond scalps, not 20s fortress loops.
    """
    if os.getenv("MIDDAY_HFT_ONLY", "true").lower() not in ("1", "true", "yes"):
        return False, "midday_hft_only=off"
    dt = dt or now_et()
    if not is_trading_day(dt):
        return False, "weekend"
    t = dt.time()
    start = _parse_et_time(os.getenv("MIDDAY_HFT_START_ET", "10:15")) or time(10, 15)
    end = _parse_et_time(os.getenv("MIDDAY_HFT_END_ET", "15:30")) or time(15, 30)
    if start <= t < end:
        return True, f"midday_hft_only_{start.strftime('%H:%M')}-{end.strftime('%H:%M')}"
    return False, "outside_midday_band"


def slow_intraday_buy_allowed(*, for_hft: bool = False, dt: datetime | None = None) -> tuple[bool, str]:
    """Fortress / day-trade / weekly-style buys — blocked during midday HFT window.

    Exception: when the 1d head is being faded (invert new buys after the open),
    fortress must still be able to buy the opposite of the morning spike.
    """
    if for_hft:
        return True, "hft_exempt"
    mid, reason = midday_hft_only(dt)
    if mid:
        fade = os.getenv("FORTRESS_FADE_DURING_MIDDAY", "true").lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        inv = os.getenv("FORTRESS_INVERT_P_UP", "auto").strip().lower()
        if fade and inv not in ("0", "false", "no", "off"):
            return True, "fade_midday"
        return False, reason
    return True, "slow_buy_ok"


def orders_allowed(side: str = "buy", *, for_hft: bool = False, symbol: str | None = None) -> tuple[bool, str]:
    """Return (ok, reason). side: buy | sell | close | exit | any.

    Crypto spot is 24/7 on Alpaca — do not apply NYSE clock / RTH windows.
    """
    if symbol:
        try:
            from crypto_universe import is_crypto_symbol

            if is_crypto_symbol(symbol) and os.getenv("TRADE_CRYPTO_24_7", "true").lower() in (
                "1",
                "true",
                "yes",
                "on",
            ):
                side_l = (side or "buy").strip().lower()
                if side_l in ("sell", "close", "exit", "short", "cover"):
                    return True, "crypto_24_7_exit"
                if os.getenv("TRADE_CRYPTO", "true").lower() not in ("1", "true", "yes", "on"):
                    return False, "crypto_disabled"
                return True, "crypto_24_7"
        except Exception:
            pass
    sess = current_session()
    side_l = (side or "buy").strip().lower()
    buy_mode = _mode("TRADE_SESSION_MODE", "rth")
    exit_mode = _mode("TRADE_EXIT_SESSION_MODE", buy_mode)

    flatten = side_l in ("sell", "close", "exit", "short", "cover")
    # Overnight leftover-cash deploy is a weeknight (20:00→04:00 ET) allowance so cash
    # is working at the next open. Equities stay 24/5: a Sat/Sun buy would only queue
    # through the weekend gap, so the weekend gate below still applies.
    overnight_cash = (
        (not flatten)
        and (not for_hft)
        and is_trading_day()
        and os.getenv("FORTRESS_OVERNIGHT_CASH_DEPLOY", "false").lower()
        in ("1", "true", "yes", "on")
    )

    # NYSE holiday / early-close gate (Alpaca clock). Exits still allowed unless blocked.
    exch_ok, exch_reason = exchange_is_open(for_hft=for_hft)
    if not exch_ok and not flatten and not overnight_cash:
        return False, exch_reason

    window_ok, window_reason = _within_trade_window(for_hft=for_hft)
    # Buys always respect TRADE_START_ET; exits can run from RTH open unless TRADE_BLOCK_EXITS_UNTIL_START=true.
    block_exits = os.getenv("TRADE_BLOCK_EXITS_UNTIL_START", "false").lower() in ("1", "true", "yes")
    if not window_ok:
        if flatten and not block_exits:
            pass
        elif overnight_cash:
            pass
        elif not flatten or block_exits:
            return False, window_reason

    if flatten:
        ok = _session_in_mode(sess, exit_mode)
        return ok, f"session={sess.value} exit_mode={exit_mode}"

    if overnight_cash:
        # Leftover cash may buy when NYSE is closed. Midday chop still stays HFT-only.
        if side_l in ("buy", "any") and not for_hft:
            slow_ok, slow_reason = slow_intraday_buy_allowed(for_hft=False)
            if not slow_ok:
                return False, slow_reason
            if "fade" in slow_reason:
                return True, slow_reason
        return True, "overnight_cash_deploy"

    if side_l in ("buy", "any") and not for_hft:
        slow_ok, slow_reason = slow_intraday_buy_allowed(for_hft=False)
        if not slow_ok:
            return False, slow_reason

    # Morning sweet spot: block buys before ~06:00 ET (bleed zone).
    if side_l in ("buy", "any"):
        try:
            from analytics.premarket_protect import morning_buy_allowed

            sweet_ok, sweet_why = morning_buy_allowed(for_hft=for_hft)
            if not sweet_ok:
                return False, sweet_why
        except Exception:
            pass

    if side_l == "any":
        ok = _session_in_mode(sess, buy_mode) or _session_in_mode(sess, exit_mode)
        return ok, f"session={sess.value} buy_mode={buy_mode} exit_mode={exit_mode}"

    ok = _session_in_mode(sess, buy_mode)
    return ok, f"session={sess.value} buy_mode={buy_mode}"


def next_session_open(dt: datetime | None = None) -> datetime | None:
    dt = (dt or now_et()).replace(second=0, microsecond=0)
    for day_off in range(0, 8):
        day = dt + timedelta(days=day_off)
        if day.weekday() >= 5:
            continue
        mode = _mode("TRADE_SESSION_MODE", "rth")
        start_s = os.getenv("TRADE_START_ET", "").strip()
        start_t = _parse_et_time(start_s) if start_s else None
        if mode == "extended":
            open_t = start_t if start_t else _PRE_OPEN
            candidate = day.replace(hour=open_t.hour, minute=open_t.minute, second=0, microsecond=0)
            if candidate > dt:
                return candidate
        candidate = day.replace(hour=_RTH_OPEN.hour, minute=_RTH_OPEN.minute, second=0, microsecond=0)
        if candidate > dt:
            return candidate
    return None


@lru_cache(maxsize=1)
def _cached_summary_key() -> str:
    """Bust cache every minute."""
    n = now_et()
    return f"{n.date()}_{n.hour}_{n.minute}"


def session_summary() -> dict:
    _cached_summary_key()
    sess = current_session()
    buy_ok, buy_reason = orders_allowed("buy")
    exit_ok, exit_reason = orders_allowed("sell")
    window_ok, window_reason = _within_trade_window()
    nxt = next_session_open()
    return {
        "session": sess.value,
        "et_now": now_et().isoformat(),
        "buy_allowed": buy_ok,
        "exit_allowed": exit_ok,
        "any_orders": buy_ok or exit_ok,
        "buy_reason": buy_reason,
        "exit_reason": exit_reason,
        "trade_window_ok": window_ok,
        "trade_window_reason": window_reason,
        "trade_start_et": _fortress_trade_start(),
        "hft_trade_start_et": os.getenv("HFT_TRADE_START_ET", "04:00").strip() or "04:00",
        "trade_end_et": os.getenv("TRADE_END_ET", "20:00").strip() or "20:00",
        "trade_weekday_24x5": os.getenv("TRADE_WEEKDAY_24X5", "true").lower()
        in ("1", "true", "yes"),
        "next_open_et": nxt.isoformat() if nxt else None,
        "trade_session_mode": _mode("TRADE_SESSION_MODE", "rth"),
        "trade_exit_session_mode": _mode("TRADE_EXIT_SESSION_MODE", _mode("TRADE_SESSION_MODE", "rth")),
    }


def log_session_block(tag: str, side: str) -> None:
    import logging

    ok, reason = orders_allowed(side)
    if ok:
        return
    logging.getLogger(__name__).info("[%s] blocked %s — %s", tag, side, reason)


def swing_buy_window_open(dt: datetime | None = None) -> tuple[bool, str]:
    """
    Multi-day / swing entries only at the open or close auction windows (not midday).

    SWING_BUY_OPEN_END_ET   default 10:15  (from 09:30)
    SWING_BUY_CLOSE_START_ET default 15:30 (until 16:00)
    Set SWING_BUY_WINDOW_ENABLED=false to allow swing buys any time RTH allows.
    """
    if os.getenv("SWING_BUY_WINDOW_ENABLED", "true").lower() not in ("1", "true", "yes"):
        return True, "swing_window=disabled"

    dt = dt or now_et()
    if not is_trading_day(dt):
        return False, "weekend"

    t = dt.time()
    open_end = _parse_et_time(os.getenv("SWING_BUY_OPEN_END_ET", "10:15")) or time(10, 15)
    close_start = _parse_et_time(os.getenv("SWING_BUY_CLOSE_START_ET", "15:30")) or time(15, 30)

    if _RTH_OPEN <= t < open_end:
        return True, f"swing_open_window<{open_end.strftime('%H:%M')}"
    if close_start <= t < _RTH_CLOSE:
        return True, f"swing_close_window>={close_start.strftime('%H:%M')}"
    return False, f"swing_midday_block ({open_end.strftime('%H:%M')}-{close_start.strftime('%H:%M')} ET)"


def swing_buy_allowed(*, hold_days: int | None = None, dt: datetime | None = None) -> tuple[bool, str]:
    """Gate multi-day strategies; short-term (hold_days < SWING_HOLD_DAYS_MIN) always allowed in RTH."""
    min_hold = int(os.getenv("SWING_HOLD_DAYS_MIN", "5"))
    hd = hold_days if hold_days is not None else int(os.getenv("HOLD_DAYS_DEFAULT", "5"))
    if hd < min_hold:
        return True, f"short_hold={hd}d"
    ok, reason = orders_allowed("buy")
    if not ok:
        return False, reason
    return swing_buy_window_open(dt)


def log_swing_block(tag: str, *, hold_days: int) -> None:
    import logging

    ok, reason = swing_buy_allowed(hold_days=hold_days)
    if ok:
        return
    logging.getLogger(__name__).info("[%s] swing buy blocked (%dd) — %s", tag, hold_days, reason)
