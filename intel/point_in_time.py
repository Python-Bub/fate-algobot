"""Point-in-time news/event filters — historical bars may not see later headlines.

Live trading passes as_of=None (today). Hist / paper_sim pass the signal date.
Undated items are dropped in hist mode so we fail closed vs look-ahead.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any


def parse_as_of(raw: date | datetime | str | None) -> date | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    s = str(raw).strip()[:10]
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def as_of_end_utc(as_of: date | datetime | str | None) -> datetime | None:
    """Inclusive end of the as-of session in UTC (23:59:59)."""
    d = parse_as_of(as_of)
    if d is None:
        return None
    return datetime.combine(d, time(23, 59, 59), tzinfo=timezone.utc)


def news_window(
    as_of: date | datetime | str | None,
    *,
    lookback_days: int = 7,
) -> tuple[date, date]:
    end = parse_as_of(as_of) or date.today()
    start = end - timedelta(days=max(1, int(lookback_days)))
    return start, end


def published_ts(item: Any) -> datetime | None:
    """Best-effort published time from Finnhub/NewsAPI-style dicts or ISO strings."""
    if item is None:
        return None
    if isinstance(item, datetime):
        dt = item
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    if isinstance(item, (int, float)):
        ts = float(item)
        if ts > 1e12:
            ts /= 1000.0
        if ts <= 0:
            return None
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    if isinstance(item, str):
        s = item.strip()
        if not s:
            return None
        try:
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            return None
    if isinstance(item, dict):
        for key in (
            "datetime",
            "datetime_utc",
            "publishedAt",
            "published_at",
            "published",
            "time",
            "ts",
            "created_at",
        ):
            if key in item and item.get(key) not in (None, ""):
                got = published_ts(item.get(key))
                if got is not None:
                    return got
    return None


def item_not_after(item: Any, as_of: date | datetime | str | None) -> bool:
    """True if the item is dated on or before as_of. Undated → False when as_of set."""
    end = as_of_end_utc(as_of)
    if end is None:
        return True
    ts = published_ts(item)
    if ts is None:
        return False
    return ts <= end


def filter_items_as_of(
    items: list[Any],
    as_of: date | datetime | str | None,
    *,
    drop_undated: bool = True,
) -> list[Any]:
    """Keep only items published on or before as_of. Live (as_of=None) keeps all."""
    if parse_as_of(as_of) is None:
        return list(items or [])
    out: list[Any] = []
    for it in items or []:
        ts = published_ts(it)
        if ts is None:
            if not drop_undated:
                out.append(it)
            continue
        if item_not_after(it, as_of):
            out.append(it)
    return out
