import os
import time

import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta, timezone

from utils import log
from symbol_aliases import price_feed_symbol

try:
    from data_store import load_cached_ohlcv, merge_and_save
except ImportError:
    load_cached_ohlcv = None  # type: ignore
    merge_and_save = None  # type: ignore

_ibkr_bars_enabled: bool = True
_FEATURE_BUILD_CACHE: dict[tuple, tuple[float, pd.DataFrame]] = {}
_SPY_BENCH_CACHE: dict[tuple[str, str], pd.DataFrame] = {}


def _disable_ibkr_bars_once(err: Exception) -> None:
    global _ibkr_bars_enabled
    if not _ibkr_bars_enabled:
        return
    _ibkr_bars_enabled = False
    log.warning(
        "[FEATURE] IBKR disabled for this process after connection failure: %s. "
        "Falling back to Yahoo prices. To avoid IBKR attempts, set PRICE_DATA_SOURCE=yfinance.",
        str(err)[:220],
    )


def _default_end_date(end_date: str | None) -> str:
    """yfinance often truncates to ~20 rows if `start` is set without `end`."""
    if end_date:
        return end_date
    return (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%d")


def _flatten_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    if isinstance(df.columns, pd.MultiIndex):
        out = df.copy()
        out.columns = [c[0] if isinstance(c, tuple) else c for c in out.columns]
        return out
    return df


def _naive_index(d: pd.DataFrame) -> pd.DataFrame:
    if d is None or d.empty:
        return d
    out = d.copy()
    idx = pd.to_datetime(out.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    out.index = idx
    return out


def _price_source() -> str:
    paper_sim = os.getenv("PAPER_SIM_ACTIVE_RUN", "false").lower() in ("1", "true", "yes")
    try:
        from data_platform.price_fetch_policy import force_yahoo_prices, use_polygon_first

        poly_first = use_polygon_first() and not force_yahoo_prices()
    except ImportError:
        poly_first = bool(os.getenv("POLYGON_API_KEY", "").strip())

    if (paper_sim or poly_first) and not force_yahoo_prices():
        if os.getenv("PAPER_SIM_USE_POLYGON", os.getenv("USE_POLYGON_FIRST", "true")).lower() in (
            "1",
            "true",
            "yes",
        ) and os.getenv("POLYGON_API_KEY", "").strip():
            return "hybrid_polygon"
        if paper_sim and os.getenv("PAPER_SIM_USE_ALPACA", "true").lower() in ("1", "true", "yes"):
            try:
                from alpaca_broker import alpaca_bars_feed_active

                if alpaca_bars_feed_active() and os.getenv("ALPACA_API_KEY", "").strip():
                    return "hybrid_alpaca"
            except ImportError:
                pass

    # Keep runtime stable when shells still have stale PRICE_DATA_SOURCE=ibkr.
    if os.getenv("FORCE_YAHOO_PRICES", "false").lower() in ("1", "true", "yes"):
        if paper_sim and os.getenv("PAPER_SIM_FORCE_YAHOO", "false").lower() not in ("1", "true", "yes"):
            pass
        else:
            return "yfinance"

    ex = os.getenv("PRICE_DATA_SOURCE", "").strip().lower()
    if ex:
        if ex in ("ibkr", "hybrid") and not _ibkr_bars_enabled:
            ex = "yfinance"
        if ex == "yfinance":
            try:
                from data_platform.price_fetch_policy import force_yahoo_prices, use_polygon_first

                if use_polygon_first() and not force_yahoo_prices():
                    return "hybrid_polygon"
            except ImportError:
                pass
        return ex
    try:
        from alpaca_broker import alpaca_bars_feed_active

        if not alpaca_bars_feed_active():
            return "yfinance"
    except ImportError:
        pass
    if os.getenv("BROKER", "alpaca").strip().lower() == "alpaca":
        if os.getenv("ALPACA_API_KEY", "").strip() and os.getenv("ALPACA_SECRET_KEY", "").strip():
            return "alpaca"
    return "yfinance"


def _skip_yahoo_fallback() -> bool:
    try:
        from data_platform.price_fetch_policy import skip_yahoo_fallback

        return skip_yahoo_fallback()
    except ImportError:
        return False


def _min_price_rows() -> int:
    return int(os.getenv("PRICE_MIN_ROWS", "60"))


def _cache_slice_ok(cached: pd.DataFrame, start_date: str, end: str) -> pd.DataFrame | None:
    """Return cached slice if it covers the requested window with enough rows.

    Fresh-but-truncated caches (e.g. ~130 recent bars while TRAIN_DATA_START=2010)
    must be rejected — they starve daily/xlong/meta multi-horizon heads.
    """
    if cached is None or cached.empty:
        return None
    start_ts = pd.Timestamp(start_date)
    sliced = _naive_index(cached).loc[_naive_index(cached).index >= start_ts]
    if len(sliced) < _min_price_rows():
        return None
    # Reject truncated history: cache begins far after the requested start.
    max_start_gap = int(os.getenv("PRICE_CACHE_MAX_START_GAP_DAYS", "400"))
    if max_start_gap > 0:
        gap = int((sliced.index.min() - start_ts).days)
        if gap > max_start_gap:
            return None
    # Multi-horizon training needs enough bars for 60d labels + warm-up.
    if os.getenv("MULTI_HORIZON_TRAIN", "false").lower() in ("1", "true", "yes"):
        min_mh = int(os.getenv("PRICE_CACHE_MIN_MULTI_HORIZON", "400"))
        if len(sliced) < min_mh:
            return None
    stale_ok_days = int(os.getenv("PRICE_CACHE_STALE_OK_DAYS", "5"))
    if stale_ok_days > 0:
        last = sliced.index.max()
        if (pd.Timestamp(end) - last).days > stale_ok_days:
            return None
    return sliced


def _load_local_csv(logical: str) -> pd.DataFrame:
    p = os.path.join("data", f"{logical}.csv")
    if not os.path.isfile(p):
        return pd.DataFrame()
    try:
        d = pd.read_csv(p, index_col=0, parse_dates=True)
        d = _naive_index(d)
        # Normalize common csv schema to expected columns.
        if "Adj Close" not in d.columns and "Close" in d.columns:
            d["Adj Close"] = d["Close"]
        return d
    except Exception as e:
        log.warning("[FEATURE] local csv load failed %s: %s", logical, e)
        return pd.DataFrame()


def _load_yfinance(logical: str, api_ticker: str, start_date: str, end: str, use_cache: bool) -> pd.DataFrame:
    from data_platform.yahoo_throttle import note_rate_limit, should_skip_yahoo_fetch, wait_turn

    tk = yf.Ticker(api_ticker)
    df: pd.DataFrame = pd.DataFrame()
    # Cache under the feed symbol so dual-listing fallbacks (SKHY→000660.KS) don't
    # reuse a thin primary cache.
    cache_key = (api_ticker or logical).strip().upper()
    cached = load_cached_ohlcv(cache_key) if (use_cache and load_cached_ohlcv) else None

    def _is_rate_limit(err: Exception) -> bool:
        msg = str(err).lower()
        return "too many requests" in msg or "rate limit" in msg

    def _hist(s: str, e: str) -> pd.DataFrame:
        if should_skip_yahoo_fetch():
            raise RuntimeError("Yahoo cooldown active")
        if not wait_turn():
            raise RuntimeError("Yahoo cooldown active")
        last_err: Exception | None = None
        for i in range(3):
            try:
                out = tk.history(start=s, end=e, auto_adjust=True, actions=False)
                return _flatten_ohlcv(out)
            except Exception as err:
                last_err = err
                if _is_rate_limit(err):
                    note_rate_limit()
                    raise err
                time.sleep(0.4 * (i + 1))
        if last_err is not None:
            if _is_rate_limit(last_err):
                note_rate_limit()
            raise last_err
        return pd.DataFrame()

    if use_cache and cached is not None and not cached.empty:
        hit = _cache_slice_ok(cached, start_date, end)
        if hit is not None:
            return hit

    if use_cache and load_cached_ohlcv and merge_and_save:
        if cached is not None and not cached.empty:
            cached = _naive_index(cached)
            # Truncated / short-history cache: full refetch from start_date (not tail-only).
            # Tail-merge alone leaves multi-horizon heads starved (e.g. MSFT ~100 bars).
            need_full = _cache_slice_ok(cached, start_date, end) is None
            if need_full:
                try:
                    df = _hist(start_date, end)
                except Exception as e:
                    log.warning(
                        "[FEATURE] Yahoo full refetch failed for %s (%s); trying tail merge",
                        logical,
                        e,
                    )
                    df = pd.DataFrame()
                if df is not None and not df.empty:
                    df = _naive_index(df)
                    # Keep any older local bars that Yahoo omitted
                    merged = pd.concat([cached, df]).sort_index()
                    merged = merged[~merged.index.duplicated(keep="last")]
                    # Prefer the longer continuous history starting near start_date
                    start_ts = pd.Timestamp(start_date)
                    near = merged.loc[merged.index >= start_ts]
                    if len(near) >= max(len(cached), _min_price_rows()):
                        merge_and_save(cache_key, near)
                        return near
                    merge_and_save(cache_key, merged)
                    df = merged
                # fall through to tail merge if full refetch empty
            if df is None or df.empty:
                last = cached.index.max()
                bump = (last - pd.Timedelta(days=14)).strftime("%Y-%m-%d")
                if pd.Timestamp(bump) < pd.Timestamp(start_date):
                    bump = start_date
                try:
                    tail = _hist(bump, end)
                except Exception as e:
                    log.warning("[FEATURE] Yahoo failed for %s (%s), using cache/local fallback", logical, e)
                    tail = pd.DataFrame()
                if tail is not None and not tail.empty:
                    tail = _naive_index(tail)
                    merged = pd.concat([cached, tail]).sort_index()
                    merged = merged[~merged.index.duplicated(keep="last")]
                    merge_and_save(cache_key, merged)
                    df = merged
                else:
                    df = cached
        else:
            try:
                df = _hist(start_date, end)
            except Exception as e:
                log.warning("[FEATURE] Yahoo failed for %s (%s), using local fallback", logical, e)
                df = pd.DataFrame()
            if df is not None and not df.empty:
                df = _naive_index(df)
                merge_and_save(cache_key, df)
    else:
        try:
            df = _hist(start_date, end)
        except Exception as e:
            log.warning("[FEATURE] Yahoo failed for %s (%s), using cache/local fallback", logical, e)
            df = pd.DataFrame()
        if df is not None and not df.empty:
            df = _naive_index(df)

    if (df is None or df.empty) and cached is not None and not cached.empty:
        df = _naive_index(cached)
    if df is None or df.empty:
        local = _load_local_csv(cache_key)
        if local is None or local.empty:
            local = _load_local_csv(logical)
        if local is not None and not local.empty:
            df = local
    return df if df is not None else pd.DataFrame()


def _load_ibkr(logical: str, api_ticker: str, start_date: str, end: str, use_cache: bool) -> pd.DataFrame:
    try:
        from ibkr_history import fetch_daily_bars_ibkr, get_ib_price_client
    except ImportError:
        log.warning("[FEATURE] ibkr_history unavailable")
        return pd.DataFrame()

    if not _ibkr_bars_enabled:
        return pd.DataFrame()
    try:
        ib = get_ib_price_client()
    except Exception as e:
        _disable_ibkr_bars_once(e)
        return pd.DataFrame()
    df = pd.DataFrame()
    if use_cache and load_cached_ohlcv and merge_and_save:
        cached = load_cached_ohlcv(logical)
        if cached is not None and not cached.empty:
            cached = _naive_index(cached)
            last = cached.index.max()
            bump = (last - pd.Timedelta(days=21)).strftime("%Y-%m-%d")
            if pd.Timestamp(bump) < pd.Timestamp(start_date):
                bump = start_date
            tail = fetch_daily_bars_ibkr(ib, api_ticker, bump, end)
            tail = _naive_index(tail)
            if tail is not None and not tail.empty:
                merged = pd.concat([cached, tail]).sort_index()
                merged = merged[~merged.index.duplicated(keep="last")]
                merge_and_save(logical, merged)
                df = merged
            else:
                df = cached
        else:
            df = fetch_daily_bars_ibkr(ib, api_ticker, start_date, end)
            df = _naive_index(df)
            if df is not None and not df.empty:
                merge_and_save(logical, df)
    else:
        df = fetch_daily_bars_ibkr(ib, api_ticker, start_date, end)
        df = _naive_index(df)

    return df if df is not None else pd.DataFrame()


def _load_alpaca(logical: str, start_date: str, end: str, use_cache: bool) -> pd.DataFrame:
    from alpaca_broker import fetch_alpaca_daily_bars

    df = pd.DataFrame()
    if use_cache and load_cached_ohlcv and merge_and_save:
        cached = load_cached_ohlcv(logical)
        if cached is not None and not cached.empty:
            cached = _naive_index(cached)
            last = cached.index.max()
            bump = (last - pd.Timedelta(days=30)).strftime("%Y-%m-%d")
            if pd.Timestamp(bump) < pd.Timestamp(start_date):
                bump = start_date
            tail = fetch_alpaca_daily_bars(logical, bump, end)
            tail = _naive_index(tail)
            if tail is not None and not tail.empty:
                merged = pd.concat([cached, tail]).sort_index()
                merged = merged[~merged.index.duplicated(keep="last")]
                merge_and_save(logical, merged)
                df = merged
            else:
                df = cached
        else:
            df = fetch_alpaca_daily_bars(logical, start_date, end)
            df = _naive_index(df)
            if df is not None and not df.empty:
                merge_and_save(logical, df)
    else:
        df = fetch_alpaca_daily_bars(logical, start_date, end)
        df = _naive_index(df)
    return df if df is not None else pd.DataFrame()


def _load_polygon(logical: str, start_date: str, end: str, use_cache: bool) -> pd.DataFrame:
    from multi_source_data import fetch_polygon_daily

    df = pd.DataFrame()
    cached = load_cached_ohlcv(logical) if (use_cache and load_cached_ohlcv) else None
    if use_cache and cached is not None and not cached.empty:
        hit = _cache_slice_ok(cached, start_date, end)
        if hit is not None:
            return hit

    if use_cache and load_cached_ohlcv and merge_and_save:
        if cached is not None and not cached.empty:
            cached = _naive_index(cached)
            last = cached.index.max()
            bump = (last - pd.Timedelta(days=30)).strftime("%Y-%m-%d")
            if pd.Timestamp(bump) < pd.Timestamp(start_date):
                bump = start_date
            tail = fetch_polygon_daily(logical, bump, end)
            tail = _naive_index(tail)
            if tail is not None and not tail.empty:
                merged = pd.concat([cached, tail]).sort_index()
                merged = merged[~merged.index.duplicated(keep="last")]
                merge_and_save(logical, merged)
                df = merged
            else:
                df = cached
        else:
            df = fetch_polygon_daily(logical, start_date, end)
            df = _naive_index(df)
            if df is not None and not df.empty:
                merge_and_save(logical, df)
    else:
        df = fetch_polygon_daily(logical, start_date, end)
        df = _naive_index(df)

    if (df is None or df.empty) and cached is not None and not cached.empty:
        df = _naive_index(cached)
        if df is not None and not df.empty:
            return df.loc[df.index >= pd.Timestamp(start_date)] if start_date else df
    return df if df is not None else pd.DataFrame()


def _stitch_price_history(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Prefer the first (current) listing; fill earlier dates from former tickers."""
    kept: list[pd.DataFrame] = []
    for fr in frames:
        if fr is None or fr.empty:
            continue
        kept.append(_naive_index(fr))
    if not kept:
        return pd.DataFrame()
    out = kept[0]
    for extra in kept[1:]:
        extra = extra.loc[~extra.index.isin(out.index)]
        if extra.empty:
            continue
        out = pd.concat([extra, out]).sort_index()
    return out


def load_price_data(ticker: str, start_date: str, end_date: str | None = None) -> pd.DataFrame:
    from symbol_aliases import price_data_fallback_symbols

    logical = ticker.strip().upper()
    min_prefer = int(os.getenv("PRICE_MIN_BARS_PREFER", "60"))
    stitch = os.getenv("USE_TICKER_HISTORY_STITCH", "true").lower() in ("1", "true", "yes")
    tried = list(price_data_fallback_symbols(logical))
    former: list[str] = []
    try:
        from universe_lifecycle.corporate_actions import former_tickers, history_symbols

        former = list(former_tickers(logical) or [])
        for h in history_symbols(logical):
            if h not in tried:
                tried.append(h)
    except Exception:
        former = []
    do_stitch = stitch and bool(former)

    best: pd.DataFrame | None = None
    best_sym = ""
    frames: list[pd.DataFrame] = []
    for sym in tried:
        df = _load_price_data_once(sym, logical, start_date, end_date)
        if df is None or df.empty:
            continue
        frames.append(df)
        if best is None or len(df) > len(best):
            best, best_sym = df, sym
        if not do_stitch and len(df) >= min_prefer:
            if sym != logical:
                log.info(
                    "[FEATURE] Price data for %s via fallback symbol %s (rows=%d)",
                    logical,
                    sym,
                    len(df),
                )
            return df
    if do_stitch and frames:
        stitched = _stitch_price_history(frames)
        if stitched is not None and not stitched.empty:
            log.info(
                "[FEATURE] Stitched history for %s from %s (rows=%d former=%s)",
                logical,
                tried,
                len(stitched),
                former,
            )
            return stitched
    if best is not None and not best.empty:
        if best_sym != logical:
            log.info(
                "[FEATURE] Price data for %s via short fallback %s (rows=%d < prefer=%d)",
                logical,
                best_sym,
                len(best),
                min_prefer,
            )
        return best
    log.warning("[FEATURE] No price data for %s (tried %s)", logical, tried)
    return pd.DataFrame()


def _load_price_data_once(ticker: str, logical: str, start_date: str, end_date: str | None) -> pd.DataFrame:
    api_sym = price_feed_symbol(ticker)
    if api_sym != logical:
        log.debug("[FEATURE] Price API symbol %s → %s", logical, api_sym)

    try:
        from data_platform.network_data import use_replay_raw_first

        replay_ok = use_replay_raw_first()
    except ImportError:
        replay_ok = os.getenv("USE_REPLAY_RAW_FIRST", "false").lower() in ("1", "true", "yes")
    if replay_ok:
        try:
            from data_platform.replay_store import load_raw

            rep = load_raw(logical)
            if rep is not None and not rep.empty:
                rep = _naive_index(rep)
                rep = rep.loc[rep.index >= pd.Timestamp(start_date)]
                if not rep.empty:
                    if "Adj Close" not in rep.columns and "Close" in rep.columns:
                        rep["Adj Close"] = rep["Close"]
                    return rep
        except Exception:
            pass

    end = _default_end_date(end_date)
    try:
        from data_platform.network_data import use_price_cache

        use_cache = use_price_cache()
    except ImportError:
        use_cache = os.getenv("USE_PRICE_CACHE", "false").lower() in ("1", "true", "yes")
    src = _price_source()

    df = pd.DataFrame()
    if src == "ibkr":
        df = _load_ibkr(logical, api_sym, start_date, end, use_cache)
    elif src == "hybrid":
        df = _load_ibkr(logical, api_sym, start_date, end, use_cache)
        if df.empty:
            log.info("[FEATURE] IBKR empty for %s — falling back to Yahoo", logical)
            df = _load_yfinance(logical, api_sym, start_date, end, use_cache)
    elif src == "alpaca":
        df = _load_alpaca(logical, start_date, end, use_cache)
        if df.empty:
            log.info("[FEATURE] Alpaca empty for %s — falling back to Yahoo", logical)
            df = _load_yfinance(logical, api_sym, start_date, end, use_cache)
    elif src == "hybrid_alpaca":
        df = _load_alpaca(logical, start_date, end, use_cache)
        if df.empty and os.getenv("POLYGON_API_KEY", "").strip():
            df = _load_polygon(logical, start_date, end, use_cache)
        if df.empty and not _skip_yahoo_fallback():
            df = _load_yfinance(logical, api_sym, start_date, end, use_cache)
    elif src == "hybrid_polygon":
        df = _load_polygon(logical, start_date, end, use_cache)
        if df.empty and not _skip_yahoo_fallback():
            df = _load_yfinance(logical, api_sym, start_date, end, use_cache)
    else:
        # Yahoo-first path — if rate-limited / empty, fall through to Alpaca then Polygon
        # (never leave fortress with zero bars when paper keys exist).
        df = _load_yfinance(logical, api_sym, start_date, end, use_cache)
        if df is None or df.empty:
            try:
                from alpaca_broker import alpaca_bars_feed_active

                if alpaca_bars_feed_active() and os.getenv("ALPACA_API_KEY", "").strip():
                    df = _load_alpaca(logical, start_date, end, use_cache)
                    if df is not None and not df.empty:
                        log.info("[FEATURE] Yahoo empty/cooldown → Alpaca bars for %s rows=%d", logical, len(df))
            except Exception as e:
                log.debug("[FEATURE] Alpaca failover %s: %s", logical, e)
            if (df is None or df.empty) and os.getenv("POLYGON_API_KEY", "").strip():
                try:
                    df = _load_polygon(logical, start_date, end, use_cache)
                    if df is not None and not df.empty:
                        log.info("[FEATURE] Yahoo empty → Polygon bars for %s rows=%d", logical, len(df))
                except Exception as e:
                    log.debug("[FEATURE] Polygon failover %s: %s", logical, e)

    if df is None or df.empty:
        return pd.DataFrame()
    df = df.dropna(how="all")
    df = _naive_index(df)
    start_ts = pd.Timestamp(start_date)
    df = df.loc[df.index >= start_ts]
    if "Adj Close" not in df.columns and "Close" in df.columns:
        df["Adj Close"] = df["Close"]
    return df


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI, strictly bounded to [0, 100].

    Note: any "RSI = 1.7..." you may see in [FE] feature_scores logs is the
    SelectKBest F-statistic for the rsi column, not the raw RSI value itself.
    The raw RSI series here is always in [0, 100] by construction.
    """
    delta = close.diff()
    gain = delta.clip(lower=0).fillna(0)
    loss = (-delta.clip(upper=0)).fillna(0)

    # Wilder's smoothing == EMA with com = period - 1.
    avg_gain = gain.ewm(com=period - 1, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period, adjust=False).mean()

    rs = avg_gain / (avg_loss + 1e-10)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi.clip(lower=0.0, upper=100.0).fillna(50.0)


def load_earnings_dates(ticker: str, lookback_quarters: int = 8) -> list:
    sym = ticker.strip().upper()
    # Schema v2+: prefer shared historical_events / earnings_calendar (network-first OK)
    try:
        from intel.historical_events import earnings_event

        snap = earnings_event(sym)
        dates: list = []
        for key in ("recent", "upcoming"):
            for s in snap.get(key) or []:
                try:
                    from datetime import date as _date

                    dates.append(_date.fromisoformat(str(s)[:10]))
                except Exception:
                    pass
        if dates:
            return sorted(set(dates))
    except Exception:
        pass
    try:
        from intel.earnings_calendar import load_all_earnings_dates

        dates = load_all_earnings_dates(sym)
        if dates:
            return dates
    except Exception:
        pass
    # Default ON for schema v2 (was false — poisoned models with zero earnings cols)
    enable = os.getenv("ENABLE_EARNINGS_FEATURES", "true").lower() in ("1", "true", "yes")
    if not enable:
        return []
    tk = yf.Ticker(ticker)
    limit = max(lookback_quarters * 4, int(os.getenv("EARNINGS_YF_LIMIT", "24")))
    try:
        edf = tk.get_earnings_dates(limit=limit)
    except TypeError:
        try:
            edf = tk.get_earnings_dates()
        except Exception:
            return []
    except Exception:
        return []
    if edf is None or edf.empty:
        return []
    if "Earnings Date" in edf.columns:
        edf = edf.dropna(subset=["Earnings Date"]).reset_index(drop=True)
        return pd.to_datetime(edf["Earnings Date"]).dt.date.tolist()
    idx = edf.index
    if not isinstance(idx, pd.DatetimeIndex):
        idx = pd.to_datetime(pd.Series(idx), errors="coerce")
    return [pd.Timestamp(d).date() for d in idx if pd.notna(d)]


FEATURE_SCHEMA_VERSION = int(os.getenv("FEATURE_SCHEMA_VERSION", "2"))


def invalidate_stale_feature_cache(*, reason: str = "schema_bump") -> int:
    """Drop in-process feature build cache when schema upgrades (optimize, never remove)."""
    n = len(_FEATURE_BUILD_CACHE)
    _FEATURE_BUILD_CACHE.clear()
    try:
        from utils import log

        log.info("[FEATURE] invalidated %d cached frames (%s schema=v%d)", n, reason, FEATURE_SCHEMA_VERSION)
    except Exception:
        pass
    return n


def build_features(ticker: str, start_date: str, end_date: str | None = None) -> pd.DataFrame:
    logical = ticker.strip().upper()
    end_key = end_date or ""
    schema = FEATURE_SCHEMA_VERSION
    if os.getenv("FEATURE_BUILD_CACHE", "true").lower() in ("1", "true", "yes"):
        ttl = float(os.getenv("FEATURE_BUILD_CACHE_TTL_SEC", "3600"))
        cache_key = (logical, start_date, end_key, schema)
        hit = _FEATURE_BUILD_CACHE.get(cache_key)
        if hit is not None and (time.time() - hit[0]) < ttl:
            return hit[1]

    df = _build_features_uncached(logical, start_date, end_date)
    # Attach event features from shared store (same schema across pipelines)
    if not df.empty and os.getenv("USE_HISTORICAL_EVENTS", "true").lower() in ("1", "true", "yes"):
        try:
            from intel.historical_events import event_features

            ef = event_features(logical)
            if ef.get("earnings_avg_abs_move_1d") is not None and "earnings_avg_move_1d" not in df.columns:
                df["earnings_avg_move_1d"] = float(ef["earnings_avg_abs_move_1d"])
            if ef.get("earnings_avg_abs_move_5d") is not None and "earnings_avg_move_5d" not in df.columns:
                df["earnings_avg_move_5d"] = float(ef["earnings_avg_abs_move_5d"])
        except Exception:
            pass
    if (
        not df.empty
        and os.getenv("FEATURE_BUILD_CACHE", "true").lower() in ("1", "true", "yes")
    ):
        max_sz = int(os.getenv("FEATURE_BUILD_CACHE_SIZE", "256"))
        if len(_FEATURE_BUILD_CACHE) >= max_sz > 0:
            _FEATURE_BUILD_CACHE.pop(next(iter(_FEATURE_BUILD_CACHE)))
        _FEATURE_BUILD_CACHE[(logical, start_date, end_key, schema)] = (time.time(), df)
    return df


def _bench_spy_df(start_date: str, end_date: str | None) -> pd.DataFrame:
    end = end_date or _default_end_date(None)
    key = (start_date, end)
    hit = _SPY_BENCH_CACHE.get(key)
    if hit is not None:
        return hit
    try:
        from data_platform.price_fetch_policy import use_polygon_first
    except ImportError:
        use_polygon_first = lambda: False  # noqa: E731
    if use_polygon_first() or os.getenv("PAPER_SIM_ACTIVE_RUN", "false").lower() in ("1", "true", "yes"):
        spy = load_price_data("SPY", start_date, end)
    else:
        from multi_source_data import fetch_yahoo

        spy = fetch_yahoo("SPY", start_date, end)
    _SPY_BENCH_CACHE[key] = spy
    return spy


def _build_features_uncached(ticker: str, start_date: str, end_date: str | None = None) -> pd.DataFrame:
    df = load_price_data(ticker, start_date, end_date)
    if df.empty:
        return pd.DataFrame(columns=_expected_columns())

    if "Adj Close" not in df.columns and "Close" in df.columns:
        df["Adj Close"] = df["Close"]
    if "Adj Close" not in df.columns:
        log.warning(f"[FEATURE] No valid close for {ticker}")
        return pd.DataFrame(columns=_expected_columns())

    # Yahoo/Alpaca often append a same-session stub with NaN/0 OHLC — drop it so
    # last valid bar is used (otherwise returns/p_up and gates go blind).
    close_col = "Adj Close" if "Adj Close" in df.columns else "Close"
    valid = df[close_col].astype(float)
    df = df.loc[valid.notna() & (valid > 0)].copy()
    if df.empty:
        log.warning(f"[FEATURE] No positive closes for {ticker}")
        return pd.DataFrame(columns=_expected_columns())

    df["returns"] = df["Adj Close"].pct_change().fillna(0).clip(-0.5, 0.5)
    df["rsi"] = compute_rsi(df["Adj Close"])
    df["volatility"] = df["returns"].rolling(20, min_periods=5).std().fillna(0)
    df["vol_ch"] = df["volatility"].pct_change().replace([np.inf, -np.inf], 0).fillna(0).clip(-5.0, 5.0)

    if {"High", "Low", "Close"}.issubset(df.columns):
        df["price_range"] = ((df["High"] - df["Low"]) / df["Close"].replace(0, np.nan)).fillna(0).clip(0, 1.0)
    else:
        df["price_range"] = 0

    for lag in (1, 2, 3):
        df[f"lag_{lag}_return"] = df["returns"].shift(lag).fillna(0)

    # NOTE: sentiment columns stay 0.0 in the training matrix — NewsAPI/Finnhub
    # only cover a recent window, so historical sentiment would be leaky/empty.
    # Live fortress/paper apply sentiment as overlay gates, NOT as model inputs
    # (injecting live sentiment into a model trained on zeros is a distribution shift).
    for lag in (1, 2, 3):
        df[f"lag_{lag}_sentiment"] = 0.0
    df["sentiment"] = 0.0

    df["target_1d"] = (df["returns"].shift(-1) > 0).astype(int)
    # Daily trainer (`model_trainer`) overwrites `target` with SHORT_TARGET_HORIZON
    # (default 5d). Keep a 1d column for walk-forward / legacy `ml_model.train_model`.
    df["target"] = df["target_1d"]
    h_long = int(os.getenv("LONG_HORIZON_DAYS", "20"))
    thr = float(os.getenv("LONG_MOVE_THRESHOLD", "0.0"))
    fwd_long = df["Adj Close"].shift(-h_long) / df["Adj Close"].replace(0, np.nan) - 1.0
    df["target_long"] = np.where(fwd_long.notna(), (fwd_long > thr).astype(float), np.nan)

    df["date"] = pd.to_datetime(df.index).date
    earnings = load_earnings_dates(price_feed_symbol(ticker))
    df["is_earnings_day"] = df["date"].isin(earnings).astype(int)

    # Far-from-earnings neutral: avoids treating "no calendar" like "on top of an event"
    # (dte=0 would make earnings_decay=1.0 on every row and dominate the model).
    neutral_dte = float(os.getenv("EARNINGS_NEUTRAL_DTE", "90"))

    def days_to(d):
        if not earnings:
            return neutral_dte
        future = sorted((e - d).days for e in earnings if e >= d)
        if future:
            return float(future[0])
        past = sorted((d - e).days for e in earnings if e < d)
        if past:
            return float(-past[0])
        return neutral_dte

    df["days_to_earnings"] = df["date"].apply(days_to)
    dte_s = pd.to_numeric(df["days_to_earnings"], errors="coerce")
    df["event_pre_window"] = ((dte_s >= 0) & (dte_s <= 2)).astype(float)
    df["event_post_window"] = ((dte_s < 0) & (dte_s >= -3)).astype(float)
    df["event_dte_le1"] = ((dte_s >= 0) & (dte_s <= 1)).astype(float)
    df.drop(columns=["date"], inplace=True)

    for col in _expected_columns():
        if col not in df.columns:
            df[col] = 0

    df.replace([np.inf, -np.inf], 0, inplace=True)

    if os.getenv("USE_FEATURE_STORE", "true").lower() in ("1", "true", "yes"):
        try:
            from feature_store import enrich_features

            spy = _bench_spy_df(start_date, end_date)
            df = enrich_features(df, spy)
        except Exception as e:
            log.warning("[FEATURE] FeatureStore enrich skipped: %s", e)

    if os.getenv("USE_ADVANCED_FEATURES", "true").lower() in ("1", "true", "yes"):
        try:
            from analytics.feature_families import enrich_advanced_features

            spy = _bench_spy_df(start_date, end_date)
            df = enrich_advanced_features(df, bench_df=spy)
        except Exception as e:
            log.warning("[FEATURE] Advanced feature enrichment skipped: %s", e)

    if os.getenv("USE_CLASSIC_QUANT_FEATURES", "true").lower() in ("1", "true", "yes"):
        try:
            from analytics.classic_quant_features import enrich_classic_quant_features

            df = enrich_classic_quant_features(df)
        except Exception as e:
            log.warning("[FEATURE] Classic quant feature enrichment skipped: %s", e)

    if os.getenv("USE_CHART_STRUCTURE", "true").lower() in ("1", "true", "yes"):
        try:
            from analytics.chart_structure import enrich_chart_structure

            df = enrich_chart_structure(df)
        except Exception as e:
            log.warning("[FEATURE] Chart structure enrichment skipped: %s", e)
    for _c in ("vol_climax_z", "atr_channel_pos", "close_stretch_20", "wick_reject"):
        if _c not in df.columns:
            df[_c] = 0.0

    # Never drop rows for earnings: coerce + fill so the full price history stays aligned.
    nd = float(os.getenv("EARNINGS_NEUTRAL_DTE", "90"))
    if "days_to_earnings" in df.columns:
        df["days_to_earnings"] = (
            pd.to_numeric(df["days_to_earnings"], errors="coerce").fillna(nd).clip(-400, 400)
        )
    if "is_earnings_day" in df.columns:
        df["is_earnings_day"] = pd.to_numeric(df["is_earnings_day"], errors="coerce").fillna(0).clip(0, 1)
    if "earnings_decay" in df.columns:
        df["earnings_decay"] = pd.to_numeric(df["earnings_decay"], errors="coerce").fillna(0.0).clip(0.0, 1.0)

    if os.getenv("USE_TRAIN_SIGNAL_FEATURES", "true").lower() in ("1", "true", "yes"):
        try:
            from signals.train_feature_enrich import enrich_train_signals

            df = enrich_train_signals(df, start_date, end_date or _default_end_date(None), ticker)
        except Exception as e:
            log.warning("[FEATURE] train signal enrich skipped: %s", e)
            for c in ("ur_score", "fred_spread_10y2y"):
                if c not in df.columns:
                    df[c] = 0.0

    # Cached hidden-pattern scan → feature columns (model can learn underlying structure)
    if os.getenv("USE_HIDDEN_PATTERN_FEATURES", "true").lower() in ("1", "true", "yes"):
        try:
            from analytics.hidden_pattern_learn import attach_hidden_pattern_features

            df = attach_hidden_pattern_features(df, ticker)
        except Exception as e:
            log.debug("[FEATURE] hidden pattern features skipped: %s", e)

    try:
        from data_platform.network_data import save_replay_features

        do_save = save_replay_features()
    except ImportError:
        do_save = os.getenv("SAVE_REPLAY_FEATURES", "false").lower() in ("1", "true", "yes")
    if do_save:
        try:
            from data_platform.replay_store import save_features

            save_features(ticker, df)
        except Exception as e:
            log.debug("[FEATURE] replay feature save skipped %s: %s", ticker, e)

    log.info(f"[FEATURE] Built features for {ticker}, final shape: {df.shape}")
    return df


def _expected_columns():
    return [
        "returns",
        "rsi",
        "volatility",
        "vol_ch",
        "price_range",
        "lag_1_return",
        "lag_2_return",
        "lag_3_return",
        "lag_1_sentiment",
        "lag_2_sentiment",
        "lag_3_sentiment",
        "sentiment",
        "target",
        "target_long",
        "is_earnings_day",
        "days_to_earnings",
        "event_pre_window",
        "event_post_window",
        "event_dte_le1",
    ]
