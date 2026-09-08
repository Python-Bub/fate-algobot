"""Multi-source earnings calendar — Finnhub batch + stock history + yfinance fallback."""

from __future__ import annotations

import json
import logging
import os
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from utils import log

ROOT = Path(__file__).resolve().parents[1]
DISK_CACHE_PATH = ROOT / "data" / "earnings_cache.json"
FINNHUB_BATCH_PATH = ROOT / "data" / "earnings_finnhub_batch.json"
# Shared rich calendar (date + session hour + optional call clocks) — fortress/HFT/radar read this.
SHARED_CALENDAR_PATH = ROOT / "data" / "intel" / "earnings_calendar.json"
TIME_OVERRIDES_PATH = ROOT / "data" / "intel" / "earnings_time_overrides.json"
CALENDAR_OVERRIDES_PATH = ROOT / "data" / "intel" / "earnings_calendar_overrides.json"

_EARN_CACHE: dict[str, tuple[float, list[date]]] = {}
_EMPTY_CACHE: dict[str, float] = {}
_SNAP_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_BATCH_INDEX: dict[str, list[str]] | None = None
_BATCH_META: dict[str, dict[str, Any]] | None = None  # symbol → {dates, by_date:{date→hour}}
_BATCH_REFRESHING = False
_MIN_VALID_YEAR = 1990


def _norm_hour(val: Any) -> str | None:
    """Normalize Finnhub/Yahoo session labels to amc|bmo|dmh|unknown."""
    if val is None:
        return None
    s = str(val).strip().lower()
    if not s or s in ("none", "null", "nan"):
        return None
    if s in ("amc", "after market close", "after-market", "after_market_close"):
        return "amc"
    if s in ("bmo", "before market open", "pre-market", "before_market_open"):
        return "bmo"
    if s in ("dmh", "during market hours", "tns", "time not supplied"):
        return s if s in ("dmh", "tns") else "dmh"
    # Already a clock like "13:15" / "4:15 PM"
    return s


def _session_datetimes(earn_date: date, hour: str | None) -> dict[str, str | None]:
    """Approximate ET/PT datetimes from session label (AMC≈16:00 ET, BMO≈08:00 ET)."""
    h = _norm_hour(hour) or ""
    et_hhmm = None
    if h == "amc":
        et_hhmm = "16:00"
    elif h == "bmo":
        et_hhmm = "08:00"
    elif ":" in h and h[0].isdigit():
        et_hhmm = h[:5]
    if not et_hhmm:
        return {
            "next_datetime_et": None,
            "next_datetime_pt": None,
            "timezone_et": "America/New_York",
            "timezone_pt": "America/Los_Angeles",
            "session": h or None,
        }
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        return {
            "next_datetime_et": f"{earn_date.isoformat()}T{et_hhmm}:00",
            "next_datetime_pt": None,
            "timezone_et": "America/New_York",
            "timezone_pt": "America/Los_Angeles",
            "session": h or None,
        }
    et = ZoneInfo("America/New_York")
    pt = ZoneInfo("America/Los_Angeles")
    hh, mm = int(et_hhmm[:2]), int(et_hhmm[3:5])
    dt_et = datetime(earn_date.year, earn_date.month, earn_date.day, hh, mm, tzinfo=et)
    dt_pt = dt_et.astimezone(pt)
    return {
        "next_datetime_et": dt_et.isoformat(),
        "next_datetime_pt": dt_pt.isoformat(),
        "timezone_et": "America/New_York",
        "timezone_pt": "America/Los_Angeles",
        "session": h or None,
    }


def _load_time_overrides() -> dict[str, Any]:
    if not TIME_OVERRIDES_PATH.is_file():
        return {}
    try:
        doc = json.loads(TIME_OVERRIDES_PATH.read_text(encoding="utf-8"))
        syms = doc.get("symbols") if isinstance(doc.get("symbols"), dict) else doc
        return syms if isinstance(syms, dict) else {}
    except Exception:
        return {}


def _load_calendar_overrides() -> dict[str, Any]:
    """Durable last-print / note overrides that survive Finnhub next-date roll-forward."""
    if not CALENDAR_OVERRIDES_PATH.is_file():
        return {}
    try:
        doc = json.loads(CALENDAR_OVERRIDES_PATH.read_text(encoding="utf-8"))
        ov = doc.get("overrides") if isinstance(doc.get("overrides"), dict) else doc
        return ov if isinstance(ov, dict) else {}
    except Exception:
        return {}


def _today(as_of: date | datetime | None = None) -> date:
    if as_of is None:
        return datetime.now(timezone.utc).date()
    if isinstance(as_of, datetime):
        return as_of.date()
    return as_of


def _cache_ttl() -> float:
    return float(os.getenv("EARNINGS_CACHE_TTL_SEC", "21600"))


def _empty_cache_ttl() -> float:
    return float(os.getenv("EARNINGS_EMPTY_CACHE_TTL_SEC", "300"))


def _parse_date(val: Any) -> date | None:
    if val is None:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        d = val
    elif isinstance(val, datetime):
        d = val.date()
    else:
        try:
            import pandas as pd

            ts = pd.Timestamp(val)
            if pd.isna(ts):
                return None
            d = ts.date()
        except Exception:
            try:
                d = datetime.fromisoformat(str(val)[:10]).date()
            except Exception:
                return None
    if d.year < _MIN_VALID_YEAR:
        return None
    return d


def _dedupe_dates(dates: list[date]) -> list[date]:
    """Unique dates, then collapse Finnhub day-clusters (e.g. AAPL 2026-07-29+30 → one print)."""
    uniq = sorted({d for d in dates if d and d.year >= _MIN_VALID_YEAR})
    if len(uniq) <= 1:
        return uniq
    cluster_gap = int(os.getenv("EARNINGS_DATE_CLUSTER_DAYS", "2"))
    collapsed: list[date] = []
    for d in uniq:
        if collapsed and (d - collapsed[-1]).days <= cluster_gap:
            # Keep the later day in a same-print cluster (AMC → next calendar day noise).
            collapsed[-1] = d
            continue
        collapsed.append(d)
    return collapsed


def _load_disk_cache() -> dict[str, Any]:
    if not DISK_CACHE_PATH.is_file():
        return {"version": 1, "symbols": {}}
    try:
        doc = json.loads(DISK_CACHE_PATH.read_text(encoding="utf-8"))
        doc.setdefault("symbols", {})
        return doc
    except Exception:
        return {"version": 1, "symbols": {}}


def _save_disk_cache(doc: dict[str, Any]) -> None:
    try:
        DISK_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = DISK_CACHE_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(doc, indent=0), encoding="utf-8")
        os.replace(tmp, DISK_CACHE_PATH)
    except Exception as e:
        log.debug("[EARNINGS] disk cache write failed: %s", e)


def _disk_dates(symbol: str) -> list[date]:
    sym = symbol.strip().upper()
    row = _load_disk_cache().get("symbols", {}).get(sym) or {}
    raw = row.get("dates") or []
    out: list[date] = []
    for item in raw:
        d = _parse_date(item)
        if d:
            out.append(d)
    return _dedupe_dates(out)


def _persist_disk_dates(symbol: str, dates: list[date], *, sources: list[str]) -> None:
    if not dates:
        return
    sym = symbol.strip().upper()
    doc = _load_disk_cache()
    doc.setdefault("symbols", {})[sym] = {
        "dates": [d.isoformat() for d in _dedupe_dates(dates)],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "sources": sorted(set(sources)),
    }
    _save_disk_cache(doc)


def _finnhub_budget_ok(*, primary: str = "finnhub_earnings", allow_fallback: bool = True) -> tuple[bool, str]:
    if os.getenv("EARNINGS_FINNHUB_IGNORE_BUDGET", "false").lower() in ("1", "true", "yes"):
        return True, primary
    try:
        from intel.api_budget import allow

        if allow(primary):
            return True, primary
        if allow_fallback and primary == "finnhub_earnings" and allow("finnhub"):
            return True, "finnhub"
        return False, primary
    except Exception:
        return True, primary


def _record_finnhub(*, provider: str = "finnhub_earnings") -> None:
    try:
        from intel.api_budget import record

        record(provider)
    except Exception:
        pass


def _earning_window(as_of: date | None = None) -> tuple[date, date]:
    today = _today(as_of)
    lookback = int(os.getenv("EARNINGS_LOOKBACK_DAYS", "400"))
    lookahead = int(os.getenv("EARNINGS_LOOKAHEAD_DAYS", "120"))
    return today - timedelta(days=lookback), today + timedelta(days=lookahead)


def _month_chunks(start: date, end: date) -> list[tuple[date, date]]:
    chunks: list[tuple[date, date]] = []
    cur = start.replace(day=1)
    while cur <= end:
        if cur.month == 12:
            month_end = date(cur.year, 12, 31)
        else:
            month_end = date(cur.year, cur.month + 1, 1) - timedelta(days=1)
        chunk_end = min(month_end, end)
        chunk_start = max(cur, start)
        if chunk_start <= chunk_end:
            chunks.append((chunk_start, chunk_end))
        cur = month_end + timedelta(days=1)
    return chunks


def _load_finnhub_batch_doc() -> dict[str, Any]:
    if not FINNHUB_BATCH_PATH.is_file():
        return {"version": 1, "symbols": {}, "updated_at": None, "from": None, "to": None}
    try:
        doc = json.loads(FINNHUB_BATCH_PATH.read_text(encoding="utf-8"))
        doc.setdefault("symbols", {})
        return doc
    except Exception:
        return {"version": 1, "symbols": {}, "updated_at": None, "from": None, "to": None}


def _save_finnhub_batch_doc(doc: dict[str, Any]) -> None:
    try:
        FINNHUB_BATCH_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = FINNHUB_BATCH_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(doc, indent=0), encoding="utf-8")
        os.replace(tmp, FINNHUB_BATCH_PATH)
    except Exception as e:
        log.debug("[EARNINGS] Finnhub batch cache write failed: %s", e)


def _finnhub_batch_fresh(doc: dict[str, Any]) -> bool:
    updated_at = doc.get("updated_at")
    if not updated_at:
        return False
    try:
        ts = datetime.fromisoformat(str(updated_at).replace("Z", "+00:00"))
        age = time.time() - ts.timestamp()
    except Exception:
        return False
    if age > _cache_ttl():
        return False
    start, end = _earning_window()
    return doc.get("from") == start.isoformat() and doc.get("to") == end.isoformat()


def _finnhub_calendar_rows(params: dict[str, str], *, provider: str = "finnhub_earnings") -> list[dict[str, Any]]:
    key = (os.getenv("FINNHUB_API_KEY") or "").strip()
    ok, budget_provider = _finnhub_budget_ok(primary=provider)
    if not key or not ok:
        return []
    try:
        import requests

        r = requests.get(
            "https://finnhub.io/api/v1/calendar/earnings",
            params={**params, "token": key},
            timeout=float(os.getenv("SENT_HTTP_TIMEOUT", "10")),
        )
        if r.status_code != 200:
            return []
        body = r.json() or {}
        rows = body.get("earningsCalendar") or []
        _record_finnhub(provider=budget_provider)
        return [row for row in rows if isinstance(row, dict)]
    except Exception as e:
        log.debug("[EARNINGS] Finnhub calendar failed: %s", e)
        return []


def _ensure_finnhub_batch_index(*, force_refresh: bool = False) -> dict[str, list[str]]:
    """Fetch monthly Finnhub calendar slices once, index by symbol (few calls vs per-ticker).

    Also persists per-date hour (amc/bmo) into FINNHUB_BATCH_PATH['meta'] and refreshes
    SHARED_CALENDAR_PATH for fortress / radar / HFT.
    """
    global _BATCH_INDEX, _BATCH_META, _BATCH_REFRESHING

    if (
        not force_refresh
        and _BATCH_INDEX is not None
        and os.getenv("EARNINGS_FINNHUB_BATCH", "true").lower() in ("1", "true", "yes")
    ):
        return _BATCH_INDEX

    if os.getenv("EARNINGS_FINNHUB_BATCH", "true").lower() not in ("1", "true", "yes"):
        _BATCH_INDEX = {}
        _BATCH_META = {}
        return _BATCH_INDEX

    doc = _load_finnhub_batch_doc()
    if not force_refresh and _finnhub_batch_fresh(doc):
        _BATCH_INDEX = {str(k).upper(): list(v) for k, v in (doc.get("symbols") or {}).items()}
        _BATCH_META = {
            str(k).upper(): (v if isinstance(v, dict) else {})
            for k, v in (doc.get("meta") or {}).items()
        }
        return _BATCH_INDEX

    if _BATCH_REFRESHING:
        _BATCH_INDEX = {str(k).upper(): list(v) for k, v in (doc.get("symbols") or {}).items()}
        _BATCH_META = {
            str(k).upper(): (v if isinstance(v, dict) else {})
            for k, v in (doc.get("meta") or {}).items()
        }
        return _BATCH_INDEX

    start, end = _earning_window()
    merged: dict[str, set[str]] = {
        str(k).upper(): set(v) for k, v in (doc.get("symbols") or {}).items() if isinstance(v, list)
    }
    meta: dict[str, dict[str, Any]] = {
        str(k).upper(): dict(v) if isinstance(v, dict) else {}
        for k, v in (doc.get("meta") or {}).items()
    }
    _BATCH_REFRESHING = True
    try:
        chunks = _month_chunks(start, end)
        fetched_any = False
        for chunk_start, chunk_end in chunks:
            rows = _finnhub_calendar_rows(
                {"from": chunk_start.isoformat(), "to": chunk_end.isoformat()},
            )
            if not rows:
                continue
            fetched_any = True
            for row in rows:
                sym = str(row.get("symbol") or "").upper()
                d = _parse_date(row.get("date") or row.get("period"))
                if not (sym and d):
                    continue
                iso = d.isoformat()
                merged.setdefault(sym, set()).add(iso)
                hour = _norm_hour(row.get("hour") or row.get("time") or row.get("when"))
                m = meta.setdefault(sym, {"by_date": {}})
                by_date = m.setdefault("by_date", {})
                if isinstance(by_date, dict):
                    entry = by_date.setdefault(iso, {})
                    if hour:
                        entry["hour"] = hour
                    if row.get("epsEstimate") is not None:
                        entry["epsEstimate"] = row.get("epsEstimate")
                    if row.get("revenueEstimate") is not None:
                        entry["revenueEstimate"] = row.get("revenueEstimate")
                    entry["quarter"] = row.get("quarter")
                    entry["year"] = row.get("year")
        if fetched_any or merged:
            out_doc = {
                "version": 2,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "from": start.isoformat(),
                "to": end.isoformat(),
                "symbols": {sym: sorted(ds) for sym, ds in merged.items()},
                "meta": meta,
            }
            _save_finnhub_batch_doc(out_doc)
            _BATCH_INDEX = out_doc["symbols"]
            _BATCH_META = meta
            log.info("[EARNINGS] Finnhub batch index refreshed (%d symbols)", len(_BATCH_INDEX))
            try:
                build_shared_earnings_calendar(force_refresh=False)
            except Exception as e:
                log.debug("[EARNINGS] shared calendar build deferred: %s", e)
            return _BATCH_INDEX
    finally:
        _BATCH_REFRESHING = False

    _BATCH_INDEX = {sym: sorted(ds) for sym, ds in merged.items()}
    _BATCH_META = meta
    return _BATCH_INDEX


def _finnhub_hour_for(symbol: str, earn_date: date | None) -> str | None:
    """Lookup Finnhub session hour for symbol/date from batch meta."""
    if earn_date is None:
        return None
    global _BATCH_META
    if _BATCH_META is None:
        _ensure_finnhub_batch_index()
    meta = (_BATCH_META or {}).get(symbol.strip().upper()) or {}
    by_date = meta.get("by_date") if isinstance(meta, dict) else None
    if not isinstance(by_date, dict):
        return None
    row = by_date.get(earn_date.isoformat()) or {}
    return _norm_hour(row.get("hour") if isinstance(row, dict) else None)


def _finnhub_batch_dates(symbol: str) -> list[date]:
    sym = symbol.strip().upper()
    if not sym:
        return []
    index = _ensure_finnhub_batch_index()
    raw = index.get(sym) or []
    out: list[date] = []
    for item in raw:
        d = _parse_date(item)
        if d:
            out.append(d)
    return _dedupe_dates(out)


def _finnhub_earnings_dates(symbol: str) -> list[date]:
    sym = symbol.strip().upper()
    start, end = _earning_window()
    rows = _finnhub_calendar_rows(
        {"symbol": sym, "from": start.isoformat(), "to": end.isoformat()},
    )
    out: list[date] = []
    for row in rows:
        if str(row.get("symbol", "")).upper() not in ("", sym):
            continue
        d = _parse_date(row.get("date") or row.get("period"))
        if d:
            out.append(d)
    return out


def _finnhub_stock_earnings_dates(symbol: str) -> list[date]:
    sym = symbol.strip().upper()
    if not sym:
        return []
    key = (os.getenv("FINNHUB_API_KEY") or "").strip()
    ok, provider = _finnhub_budget_ok(primary="finnhub", allow_fallback=False)
    if not key or not ok:
        return []
    try:
        import requests

        r = requests.get(
            "https://finnhub.io/api/v1/stock/earnings",
            params={"symbol": sym, "token": key},
            timeout=float(os.getenv("SENT_HTTP_TIMEOUT", "10")),
        )
        if r.status_code != 200:
            return []
        body = r.json()
        if not isinstance(body, list):
            return []
        _record_finnhub(provider=provider)
        out: list[date] = []
        for row in body:
            if not isinstance(row, dict):
                continue
            if str(row.get("symbol", sym)).upper() not in ("", sym):
                continue
            d = _parse_date(row.get("period") or row.get("date"))
            if d:
                out.append(d)
        return _dedupe_dates(out)
    except Exception as e:
        log.debug("[EARNINGS] Finnhub stock/earnings failed %s: %s", sym, e)
        return []


def _project_next_earnings(past: list[date], today: date) -> date | None:
    """Estimate next report date from historical announcement cadence."""
    if not past:
        return None
    ordered = sorted(past, reverse=True)
    gaps = [
        (ordered[i] - ordered[i + 1]).days
        for i in range(min(3, len(ordered) - 1))
        if (ordered[i] - ordered[i + 1]).days > 0
    ]
    gaps = [g for g in gaps if 60 <= g <= 120]
    gap = int(round(sum(gaps) / len(gaps))) if gaps else int(os.getenv("EARNINGS_DEFAULT_CADENCE_DAYS", "91"))
    candidate = ordered[0] + timedelta(days=gap)
    guard = 0
    while candidate <= today and guard < 6:
        candidate += timedelta(days=gap)
        guard += 1
    return candidate if candidate > today else None


@contextmanager
def _suppress_yfinance_logs() -> Iterator[None]:
    saved: list[tuple[Any, int]] = []
    for lg in (logging.getLogger("yfinance"),):
        saved.append((lg, lg.level))
        lg.setLevel(logging.CRITICAL)
    try:
        from yfinance.utils import get_yf_logger

        yfl = get_yf_logger()
        saved.append((yfl, yfl.level))
        yfl.setLevel(logging.CRITICAL)
    except Exception:
        pass
    try:
        yield
    finally:
        for lg, level in saved:
            lg.setLevel(level)


def _yfinance_enabled() -> bool:
    return os.getenv("EARNINGS_YFINANCE_ENABLED", "true").lower() in ("1", "true", "yes")


def _yfinance_earnings_dates(symbol: str) -> list[date]:
    if not _yfinance_enabled():
        return []
    sym = symbol.strip().upper()
    out: list[date] = []
    retries = max(1, int(os.getenv("EARNINGS_YF_RETRIES", "2")))
    backoff = float(os.getenv("EARNINGS_YF_RETRY_SEC", "0.4"))

    for attempt in range(retries):
        try:
            import yfinance as yf

            with _suppress_yfinance_logs():
                tk = yf.Ticker(sym)
                batch = _yfinance_dates_from_ticker(tk)
            if batch:
                out.extend(batch)
                break
        except Exception as e:
            log.debug("[EARNINGS] yfinance attempt %s/%s failed %s: %s", attempt + 1, retries, sym, e)
        if attempt + 1 < retries:
            time.sleep(backoff * (attempt + 1))
    return _dedupe_dates(out)


def _yfinance_dates_from_ticker(tk: Any) -> list[date]:
    out: list[date] = []
    limit = int(os.getenv("EARNINGS_YF_LIMIT", "24"))

    try:
        cal = tk.get_calendar()
        if cal and "Earnings Date" in cal:
            raw = cal["Earnings Date"]
            items = raw if isinstance(raw, (list, tuple)) else [raw]
            for item in items:
                d = _parse_date(item)
                if d:
                    out.append(d)
    except Exception:
        pass

    try:
        edf = tk.get_earnings_dates(limit=max(limit, 12))
        if edf is not None and not edf.empty:
            if "Earnings Date" in edf.columns:
                for val in edf["Earnings Date"].dropna():
                    d = _parse_date(val)
                    if d:
                        out.append(d)
            else:
                for idx in edf.index:
                    d = _parse_date(idx)
                    if d:
                        out.append(d)
    except Exception:
        pass

    try:
        info = tk.info or {}
        for key in ("earningsDate", "mostRecentQuarter"):
            raw = info.get(key)
            if isinstance(raw, (list, tuple)):
                for item in raw:
                    d = _parse_date(item)
                    if d:
                        out.append(d)
            else:
                d = _parse_date(raw)
                if d:
                    out.append(d)
        quote_type = str(info.get("quoteType") or "").upper()
        if quote_type in ("ETF", "MUTUALFUND", "INDEX", "CURRENCY"):
            return []
    except Exception:
        pass
    return _dedupe_dates(out)


def load_all_earnings_dates(symbol: str, *, force_refresh: bool = False) -> list[date]:
    """Merge disk + Finnhub batch/per-symbol + stock history + yfinance (deduped, sorted)."""
    sym = symbol.strip().upper()
    if not sym:
        return []
    now = time.time()

    hit = _EARN_CACHE.get(sym)
    if not force_refresh and hit and (now - hit[0]) < _cache_ttl():
        return list(hit[1])

    empty_at = _EMPTY_CACHE.get(sym)
    if not force_refresh and empty_at and (now - empty_at) < _empty_cache_ttl():
        return []

    dates: list[date] = []
    sources: list[str] = []
    budget_blocked = False

    disk = _disk_dates(sym)
    if disk:
        dates.extend(disk)
        sources.append("disk")

    batch_dates = _finnhub_batch_dates(sym)
    if batch_dates:
        dates.extend(batch_dates)
        sources.append("finnhub_batch")

    per_symbol_ok = os.getenv("EARNINGS_FINNHUB_PER_SYMBOL", "false").lower() in ("1", "true", "yes")
    if per_symbol_ok or not batch_dates:
        ok, _ = _finnhub_budget_ok()
        if ok:
            fh_dates = _finnhub_earnings_dates(sym)
            if fh_dates:
                dates.extend(fh_dates)
                sources.append("finnhub")
        elif not batch_dates:
            budget_blocked = True

    if not dates:
        ok, _ = _finnhub_budget_ok(primary="finnhub", allow_fallback=False)
        if ok:
            hist_dates = _finnhub_stock_earnings_dates(sym)
            if hist_dates:
                dates.extend(hist_dates)
                sources.append("finnhub_stock")
        elif not budget_blocked:
            budget_blocked = True

    if not dates and _yfinance_enabled():
        yf_dates = _yfinance_earnings_dates(sym)
        if yf_dates:
            dates.extend(yf_dates)
            sources.append("yfinance")

    uniq = _dedupe_dates(dates)
    if uniq:
        _EARN_CACHE[sym] = (now, uniq)
        _EMPTY_CACHE.pop(sym, None)
        _persist_disk_dates(sym, uniq, sources=sources)
        return uniq

    if not budget_blocked:
        _EMPTY_CACHE[sym] = now
    return []


def earnings_snapshot(symbol: str, *, as_of: date | None = None, force_refresh: bool = False) -> dict[str, Any]:
    """Next/prev earnings + days_to_next for AI and risk filters."""
    sym = symbol.strip().upper()
    today = _today(as_of)
    now = time.time()
    cache_key = f"{sym}:{today.isoformat()}"
    hit = _SNAP_CACHE.get(cache_key)
    if not force_refresh and hit and (now - hit[0]) < _cache_ttl():
        return dict(hit[1])

    all_dates = load_all_earnings_dates(sym, force_refresh=force_refresh)
    future = sorted(d for d in all_dates if d >= today)
    past = sorted((d for d in all_dates if d < today), reverse=True)
    nxt = future[0] if future else None
    estimated = False

    if nxt is None and past:
        projected = _project_next_earnings(past, today)
        if projected:
            nxt = projected
            estimated = True
            all_dates = _dedupe_dates(all_dates + [projected])
            future = sorted(d for d in all_dates if d >= today)

    prev = past[0] if past else None
    days_to = (nxt - today).days if nxt else None
    days_since = (today - prev).days if prev else None

    # Durable last-print overrides survive Finnhub next-date roll-forward (MSFT/SBUX/…).
    # Only treat as *already printed* when last_earnings_date is strictly before today —
    # day-of names (AAPL/AMZN) keep next=today until the calendar day rolls.
    _cal_ov = _load_calendar_overrides()
    cov = _cal_ov.get(sym) if isinstance(_cal_ov.get(sym), dict) else None
    if cov and cov.get("last_earnings_date"):
        try:
            last_override_date = datetime.fromisoformat(str(cov["last_earnings_date"])[:10]).date()
        except Exception:
            last_override_date = None
        if last_override_date is not None and last_override_date < today:
            if prev is None or last_override_date >= prev:
                prev = last_override_date
                days_since = (today - prev).days
                if last_override_date not in past:
                    past = [last_override_date] + [d for d in past if d != last_override_date]
            # Finnhub sometimes still lists the printed day as "next" — prefer later quarter.
            if nxt is not None and last_override_date >= nxt:
                future2 = [d for d in future if d > last_override_date]
                if future2:
                    nxt = future2[0]
                    days_to = (nxt - today).days
                    future = future2

    hour = _finnhub_hour_for(sym, nxt) if nxt else None
    ov = _load_time_overrides().get(sym) or {}
    ov_date = str(ov.get("date") or "") if isinstance(ov, dict) else ""
    call_pt = call_et = results_release = None
    time_sources: list[str] = ["finnhub" if hour else "dates_only"]
    if isinstance(ov, dict) and ov_date and nxt and ov_date == nxt.isoformat():
        hour = _norm_hour(ov.get("finnhub_hour") or ov.get("report_session") or hour) or hour
        call_pt = ov.get("call_time_pt")
        call_et = ov.get("call_time_et")
        results_release = ov.get("results_release")
        time_sources = list(ov.get("sources") or time_sources)
    dt_info = _session_datetimes(nxt, hour) if nxt else {
        "next_datetime_et": None,
        "next_datetime_pt": None,
        "timezone_et": "America/New_York",
        "timezone_pt": "America/Los_Angeles",
        "session": None,
    }
    # Prefer IR call clock when present (PT primary)
    if call_pt and nxt:
        try:
            from zoneinfo import ZoneInfo

            hh, mm = int(str(call_pt)[:2]), int(str(call_pt)[3:5])
            dt_pt = datetime(nxt.year, nxt.month, nxt.day, hh, mm, tzinfo=ZoneInfo("America/Los_Angeles"))
            dt_et = dt_pt.astimezone(ZoneInfo("America/New_York"))
            dt_info["call_datetime_pt"] = dt_pt.isoformat()
            dt_info["call_datetime_et"] = dt_et.isoformat()
            # For AMC names, results ≈ market close ET; keep session datetimes from hour
            if not dt_info.get("next_datetime_et") and hour == "amc":
                close_et = datetime(nxt.year, nxt.month, nxt.day, 16, 0, tzinfo=ZoneInfo("America/New_York"))
                dt_info["next_datetime_et"] = close_et.isoformat()
                dt_info["next_datetime_pt"] = close_et.astimezone(ZoneInfo("America/Los_Angeles")).isoformat()
        except Exception:
            dt_info["call_time_pt"] = call_pt
            dt_info["call_time_et"] = call_et

    snap: dict[str, Any] = {
        "symbol": sym,
        "next_earnings_date": nxt.isoformat() if nxt else None,
        "prev_earnings_date": prev.isoformat() if prev else None,
        "days_to_earnings": days_to,
        "days_since_earnings": days_since,
        "earnings_count": len(all_dates),
        "upcoming_dates": [d.isoformat() for d in future[:6]],
        "recent_dates": [d.isoformat() for d in past[:4]],
        "in_earnings_window": bool(
            days_to is not None
            and not estimated
            and 0 <= days_to <= int(os.getenv("ALGO_RISK_EARNINGS_BUFFER_DAYS", "5"))
        ),
        "estimated_next": estimated,
        "as_of": today.isoformat(),
        "hour": hour,
        "session": dt_info.get("session") or hour,
        "next_datetime_et": dt_info.get("next_datetime_et"),
        "next_datetime_pt": dt_info.get("next_datetime_pt"),
        "call_time_pt": call_pt,
        "call_time_et": call_et or (None if not call_pt else None),
        "call_datetime_pt": dt_info.get("call_datetime_pt"),
        "call_datetime_et": dt_info.get("call_datetime_et"),
        "results_release": results_release,
        "timezone_et": "America/New_York",
        "timezone_pt": "America/Los_Angeles",
        "time_sources": time_sources,
    }
    if cov:
        if cov.get("last_earnings_date"):
            snap["last_earnings_date"] = str(cov["last_earnings_date"])[:10]
        if cov.get("last_results_release"):
            snap["last_results_release"] = cov.get("last_results_release")
        if cov.get("last_call_time_pt"):
            snap["last_call_time_pt"] = cov.get("last_call_time_pt")
        if cov.get("note"):
            snap["calendar_override_note"] = cov.get("note")
        snap["time_sources"] = list(dict.fromkeys(list(snap.get("time_sources") or []) + ["calendar_overrides"]))
    if call_et:
        snap["call_time_et"] = call_et
    _SNAP_CACHE[cache_key] = (now, snap)
    return snap


def days_to_next_earnings(symbol: str, *, as_of: date | None = None) -> tuple[date | None, int | None]:
    snap = earnings_snapshot(symbol, as_of=as_of)
    nxt_s = snap.get("next_earnings_date")
    nxt = datetime.fromisoformat(nxt_s).date() if nxt_s else None
    days = snap.get("days_to_earnings")
    return nxt, int(days) if days is not None else None


def earnings_context_text(symbol: str, *, as_of: date | None = None) -> str:
    snap = earnings_snapshot(symbol, as_of=as_of)
    parts = [f"Symbol {symbol.upper()}"]
    if snap.get("next_earnings_date"):
        est = " (estimated)" if snap.get("estimated_next") else ""
        sess = snap.get("hour") or snap.get("session") or ""
        clock = ""
        if snap.get("call_time_pt"):
            clock = f" call {snap['call_time_pt']} PT / {snap.get('call_time_et') or '?'} ET"
        elif snap.get("next_datetime_pt"):
            clock = f" ~{snap['next_datetime_pt']}"
        parts.append(
            f"Next earnings: {snap['next_earnings_date']}{est} "
            f"[{sess or 'time_unknown'}]{clock} "
            f"({snap.get('days_to_earnings')} calendar days away)"
        )
    if snap.get("prev_earnings_date"):
        parts.append(f"Last earnings: {snap['prev_earnings_date']}")
    if snap.get("upcoming_dates"):
        parts.append(f"Upcoming dates: {', '.join(snap['upcoming_dates'][:4])}")
    if snap.get("in_earnings_window"):
        parts.append("WARNING: inside pre-earnings binary window — treat headlines as high-impact.")
    return ". ".join(parts)


def build_shared_earnings_calendar(
    *,
    symbols: list[str] | None = None,
    force_refresh: bool = False,
    horizon_days: int = 120,
) -> dict[str, Any]:
    """
    Write data/intel/earnings_calendar.json — shared store for fortress / paper / HFT / radar.

    Merges Finnhub batch (date+hour) + IR time overrides. Does not delete existing coverage.
    """
    _ensure_finnhub_batch_index(force_refresh=force_refresh)
    today = _today()
    end = today + timedelta(days=horizon_days)
    overrides = _load_time_overrides()
    cal_overrides = _load_calendar_overrides()

    if symbols:
        universe = [s.strip().upper() for s in symbols if s and str(s).strip()]
    else:
        # Prefer model-covered + Finnhub-indexed names (tradable focus)
        universe = sorted(set((_BATCH_INDEX or {}).keys()) | set(overrides.keys()))
        models_dir = ROOT / "models"
        if models_dir.is_dir():
            for p in models_dir.glob("*_model.pkl"):
                universe.append(p.name.replace("_model.pkl", "").upper())
        universe = sorted(set(universe))

    entries: dict[str, Any] = {}
    with_date = 0
    with_hour = 0
    with_call_clock = 0
    near: list[dict[str, Any]] = []

    for sym in universe:
        dates = _finnhub_batch_dates(sym)
        future = sorted(d for d in dates if today <= d <= end)
        if not future and sym not in overrides and sym not in cal_overrides:
            # Skip slow per-symbol network snapshots in bulk rebuild (was hanging ~1k names).
            # Priority symbols still resolve via earnings_snapshot / export tools.
            continue
        if not future and (sym in overrides or sym in cal_overrides):
            # Override-only: still include next from snapshot (small set).
            snap = earnings_snapshot(sym)
            if not snap.get("next_earnings_date"):
                continue
            nxt = datetime.fromisoformat(snap["next_earnings_date"]).date()
            if not (today <= nxt <= end):
                # Still emit last-print-only rows for post-print radar.
                if sym in cal_overrides and cal_overrides[sym].get("last_earnings_date"):
                    row = {
                        "symbol": sym,
                        "next_earnings_date": snap.get("next_earnings_date"),
                        "hour": snap.get("hour"),
                        "session": snap.get("session") or snap.get("hour"),
                        "next_datetime_et": snap.get("next_datetime_et"),
                        "next_datetime_pt": snap.get("next_datetime_pt"),
                        "call_time_pt": snap.get("call_time_pt"),
                        "call_time_et": snap.get("call_time_et"),
                        "results_release": snap.get("results_release"),
                        "timezone_et": "America/New_York",
                        "timezone_pt": "America/Los_Angeles",
                        "upcoming_dates": list(snap.get("upcoming_dates") or []),
                        "sources": ["calendar_overrides", "snapshot"],
                        "last_earnings_date": str(cal_overrides[sym].get("last_earnings_date")),
                    }
                    if cal_overrides[sym].get("last_results_release"):
                        row["last_results_release"] = cal_overrides[sym].get("last_results_release")
                    if cal_overrides[sym].get("last_call_time_pt"):
                        row["last_call_time_pt"] = cal_overrides[sym].get("last_call_time_pt")
                    if cal_overrides[sym].get("note"):
                        row["calendar_override_note"] = cal_overrides[sym].get("note")
                    entries[sym] = row
                    with_date += 1
                continue
            future = [nxt]
        if not future:
            continue
        nxt = future[0]
        hour = _finnhub_hour_for(sym, nxt)
        ov = overrides.get(sym) if isinstance(overrides.get(sym), dict) else None
        call_pt = call_et = None
        results_release = None
        sources = ["finnhub_batch"]
        if ov and str(ov.get("date") or "") == nxt.isoformat():
            hour = _norm_hour(ov.get("finnhub_hour") or ov.get("report_session") or hour) or hour
            call_pt = ov.get("call_time_pt")
            call_et = ov.get("call_time_et")
            results_release = ov.get("results_release")
            sources = list(ov.get("sources") or sources)
        dt_info = _session_datetimes(nxt, hour)
        row = {
            "symbol": sym,
            "next_earnings_date": nxt.isoformat(),
            "hour": hour,
            "session": hour,
            "next_datetime_et": dt_info.get("next_datetime_et"),
            "next_datetime_pt": dt_info.get("next_datetime_pt"),
            "call_time_pt": call_pt,
            "call_time_et": call_et,
            "results_release": results_release,
            "timezone_et": "America/New_York",
            "timezone_pt": "America/Los_Angeles",
            "upcoming_dates": [d.isoformat() for d in future[:8]],
            "sources": sources,
        }
        cov = cal_overrides.get(sym) if isinstance(cal_overrides.get(sym), dict) else None
        if cov:
            if cov.get("last_earnings_date"):
                row["last_earnings_date"] = str(cov["last_earnings_date"])
            if cov.get("last_results_release"):
                row["last_results_release"] = cov.get("last_results_release")
            if cov.get("last_call_time_pt"):
                row["last_call_time_pt"] = cov.get("last_call_time_pt")
            if cov.get("note"):
                row["calendar_override_note"] = cov.get("note")
            row["sources"] = list(dict.fromkeys(list(row.get("sources") or []) + ["calendar_overrides"]))
        if call_pt:
            try:
                from zoneinfo import ZoneInfo

                hh, mm = int(str(call_pt)[:2]), int(str(call_pt)[3:5])
                dt_pt = datetime(nxt.year, nxt.month, nxt.day, hh, mm, tzinfo=ZoneInfo("America/Los_Angeles"))
                row["call_datetime_pt"] = dt_pt.isoformat()
                row["call_datetime_et"] = dt_pt.astimezone(ZoneInfo("America/New_York")).isoformat()
                with_call_clock += 1
            except Exception:
                pass
        entries[sym] = row
        with_date += 1
        if hour:
            with_hour += 1
        if (nxt - today).days <= 7:
            near.append(
                {
                    "symbol": sym,
                    "date": nxt.isoformat(),
                    "hour": hour,
                    "call_time_pt": call_pt,
                    "days_to": (nxt - today).days,
                }
            )

    near.sort(key=lambda r: (r.get("days_to") if r.get("days_to") is not None else 99, r["symbol"]))
    doc = {
        "version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "as_of": today.isoformat(),
        "horizon_days": horizon_days,
        "universe_n": len(universe),
        "with_next_date": with_date,
        "with_session_hour": with_hour,
        "with_call_clock": with_call_clock,
        "pct_hour_given_date": round(100.0 * with_hour / with_date, 2) if with_date else 0.0,
        "near_7d": near[:80],
        "symbols": entries,
        "sbux": entries.get("SBUX"),
        "path": str(SHARED_CALENDAR_PATH.relative_to(ROOT)),
    }
    try:
        SHARED_CALENDAR_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = SHARED_CALENDAR_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        os.replace(tmp, SHARED_CALENDAR_PATH)
        log.info(
            "[EARNINGS] shared calendar → %s names=%d hour=%d call_clock=%d",
            SHARED_CALENDAR_PATH,
            with_date,
            with_hour,
            with_call_clock,
        )
    except Exception as e:
        log.warning("[EARNINGS] shared calendar write failed: %s", e)
    return doc


def load_shared_earnings_calendar() -> dict[str, Any]:
    if not SHARED_CALENDAR_PATH.is_file():
        return {}
    try:
        return json.loads(SHARED_CALENDAR_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
