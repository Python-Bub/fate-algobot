"""
Alpaca Market Data (daily bars) + Trading REST.
Requires: ALPACA_API_KEY, ALPACA_SECRET_KEY in environment.
Paper: ALPACA_BASE_URL=https://paper-api.alpaca.markets (default)
Data: ALPACA_DATA_URL=https://data.alpaca.markets (default)
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

from utils import log

from symbol_aliases import price_feed_symbol


def _require_order_host() -> None:
    from order_role import orders_allowed_here

    if not orders_allowed_here():
        raise RuntimeError("order blocked (FATE_ORDER_ROLE — only GCP paper VM posts)")
from crypto_universe import is_crypto_symbol, alpaca_symbol

# Set False after HTTP 401/403 on data API (trading keys often lack Market Data subscription).
_alpaca_bars_enabled: bool = True


def alpaca_bars_feed_active() -> bool:
    return _alpaca_bars_enabled


def _disable_alpaca_bars_once(status: int, detail: str) -> None:
    global _alpaca_bars_enabled
    if not _alpaca_bars_enabled:
        return
    _alpaca_bars_enabled = False
    log.warning(
        "[ALPACA] Market data HTTP %s — disabling Alpaca bar requests for this process. "
        "Paper/live *trading* keys do not include data.alpaca.markets unless you subscribe "
        "to Alpaca Market Data; price features will use Yahoo fallback. "
        "To skip Alpaca attempts entirely: export PRICE_DATA_SOURCE=yfinance. Detail: %s",
        status,
        detail[:180].replace("\n", " "),
    )


def _keys() -> tuple[str, str]:
    k = os.getenv("ALPACA_API_KEY", "").strip()
    s = os.getenv("ALPACA_SECRET_KEY", "").strip()
    return k, s


def _request_with_retry(
    method: str,
    url: str,
    *,
    headers: dict | None = None,
    params: dict | None = None,
    json: dict | None = None,
    timeout: float = 20,
    max_attempts: int | None = None,
) -> requests.Response:
    """Light REST retry for blips / 429 / 5xx. Order POSTs use fewer attempts."""
    attempts = int(max_attempts if max_attempts is not None else os.getenv("ALPACA_REST_RETRIES", "3"))
    attempts = max(1, min(attempts, 5))
    last: requests.Response | None = None
    for i in range(attempts):
        try:
            last = requests.request(
                method.upper(),
                url,
                headers=headers,
                params=params,
                json=json,
                timeout=timeout,
            )
            if last.status_code == 429 or last.status_code >= 500:
                if i + 1 < attempts:
                    time.sleep(min(8.0, 0.4 * (2**i)))
                    continue
            return last
        except (requests.ConnectionError, requests.Timeout) as e:
            if i + 1 >= attempts:
                raise
            log.warning("[ALPACA] %s %s failed (%s) — retry %d/%d", method, url, e, i + 1, attempts)
            time.sleep(min(8.0, 0.4 * (2**i)))
    assert last is not None
    return last


def _normalize_base(url: str) -> str:
    base = (url or "").strip().rstrip("/")
    if base.endswith("/v2"):
        base = base[:-3]
    return base


def _data_headers() -> dict:
    k, s = _keys()
    return {"APCA-API-KEY-ID": k, "APCA-API-SECRET-KEY": s}


def _trade_headers() -> dict:
    return _data_headers()


def fetch_alpaca_daily_bars(
    symbol: str,
    start: str,
    end: str | None = None,
) -> pd.DataFrame:
    k, s = _keys()
    if not k or not s:
        log.warning("[ALPACA] Missing ALPACA_API_KEY / ALPACA_SECRET_KEY")
        return pd.DataFrame()
    if not _alpaca_bars_enabled:
        return pd.DataFrame()

    sym = price_feed_symbol(symbol)
    base = _normalize_base(os.getenv("ALPACA_DATA_URL", "https://data.alpaca.markets"))
    end_iso = end or (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    start_iso = pd.Timestamp(start).strftime("%Y-%m-%dT%H:%M:%SZ")

    rows: list[dict] = []
    idxs: list = []
    url = f"{base}/v2/stocks/{sym}/bars"
    params: dict = {
        "timeframe": "1Day",
        "start": start_iso,
        "end": end_iso,
        "adjustment": "all",
        "limit": 10000,
    }
    next_token = None

    for _ in range(500):
        if next_token:
            params["page_token"] = next_token
        try:
            r = requests.get(url, params=params, headers=_data_headers(), timeout=60)
            if r.status_code in (401, 403):
                _disable_alpaca_bars_once(r.status_code, r.text or "")
                return pd.DataFrame()
            r.raise_for_status()
        except Exception as e:
            log.warning("[ALPACA] bars request failed %s: %s", sym, e)
            break
        js = r.json()
        bars = js.get("bars") or []
        for b in bars:
            idxs.append(pd.to_datetime(b["t"]))
            rows.append(
                {
                    "Open": float(b["o"]),
                    "High": float(b["h"]),
                    "Low": float(b["l"]),
                    "Close": float(b["c"]),
                    "Volume": float(b.get("v", 0)),
                }
            )
        next_token = js.get("next_page_token")
        if not next_token:
            break

    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, index=pd.DatetimeIndex(idxs))
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="last")]
    idx = pd.to_datetime(df.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    df.index = idx
    if "Adj Close" not in df.columns:
        df["Adj Close"] = df["Close"]
    return df


def get_mid_price(symbol: str) -> float | None:
    q = get_quote_bid_ask(symbol)
    if q is None:
        return None
    bid, ask = q
    return (bid + ask) / 2.0


def get_crypto_quote_bid_ask(symbol: str) -> tuple[float, float] | None:
    """Alpaca crypto latest quote (separate from IEX stock quotes)."""
    k, _ = _keys()
    if not k:
        return None
    from crypto_universe import alpaca_symbol as _crypto_alpaca, yahoo_symbol as _crypto_yahoo

    routed = _crypto_alpaca(symbol)
    yahoo = _crypto_yahoo(symbol)
    try:
        from analytics.alpaca_limits import quote_cache_get, quote_cache_put

        cached = quote_cache_get(f"crypto:{routed}")
        if cached:
            return cached
    except Exception:
        pass
    base = _normalize_base(os.getenv("ALPACA_DATA_URL", "https://data.alpaca.markets"))
    try:
        r = requests.get(
            f"{base}/v1beta3/crypto/us/latest/quotes",
            headers=_data_headers(),
            params={"symbols": routed},
            timeout=15,
        )
        if r.status_code in (401, 403, 429):
            y = _yahoo_last_px(yahoo)
            return _nbbo_from_last(y) if y else None
        r.raise_for_status()
        body = r.json() if r.content else {}
        quotes = (body or {}).get("quotes") or {}
        q = quotes.get(routed) or quotes.get(routed.replace("/", "")) or {}
        if not q and quotes:
            q = next(iter(quotes.values()), {}) or {}
        bp, ap = q.get("bp"), q.get("ap")
        if bp and ap and float(bp) > 0 and float(ap) > 0:
            out = (float(bp), float(ap))
            try:
                from analytics.alpaca_limits import quote_cache_put

                quote_cache_put(f"crypto:{routed}", out[0], out[1])
            except Exception:
                pass
            return out
        y = _yahoo_last_px(yahoo)
        return _nbbo_from_last(y) if y else None
    except Exception as e:
        log.debug("[ALPACA] crypto quote %s: %s", routed, e)
        y = _yahoo_last_px(yahoo)
        return _nbbo_from_last(y) if y else None


def get_quote_bid_ask(symbol: str) -> tuple[float, float] | None:
    """Latest bid/ask from Alpaca IEX quote (rate-limited + cached — Basic plan 200 RPM)."""
    if is_crypto_symbol(symbol):
        return get_crypto_quote_bid_ask(symbol)
    k, s = _keys()
    if not k:
        return None
    sym = price_feed_symbol(symbol)
    try:
        from analytics.alpaca_limits import (
            acquire_data_token,
            honor_rate_limit_headers,
            note_data_429,
            quote_cache_get,
            quote_cache_put,
        )

        cached = quote_cache_get(sym)
        if cached:
            return cached
        gate = acquire_data_token(cost=1.0)
        if not gate.ok:
            # Serve any slightly stale cache rather than stampeding into more 429s
            stale = quote_cache_get(sym)
            if stale:
                return stale
            log.warning("[ALPACA] quote paced %s — %s retry_in=%.1fs", sym, gate.reason, gate.retry_after_sec)
            y = _yahoo_last_px(symbol)
            if y:
                out = _nbbo_from_last(y)
                if out:
                    return out
            return None
    except Exception:
        pass
    base = _normalize_base(os.getenv("ALPACA_DATA_URL", "https://data.alpaca.markets"))
    try:
        r = requests.get(
            f"{base}/v2/stocks/{sym}/quotes/latest",
            headers=_data_headers(),
            timeout=15,
        )
        try:
            from analytics.alpaca_limits import honor_rate_limit_headers, note_data_429

            honor_rate_limit_headers(r)
            if r.status_code == 429:
                note_data_429()
        except Exception:
            pass
        if r.status_code in (401, 403):
            _disable_alpaca_bars_once(r.status_code, r.text or "")
            return None
        if r.status_code == 429:
            log.warning("[ALPACA] quote 429 %s — cooling data API", sym)
            y = _yahoo_last_px(symbol)
            if y:
                out = _nbbo_from_last(y)
                if out:
                    return out
            return None
        r.raise_for_status()
        q = r.json().get("quote") or {}
        bp, ap = q.get("bp"), q.get("ap")
        if bp and ap and float(bp) > 0 and float(ap) > 0:
            out = (float(bp), float(ap))
            try:
                from analytics.alpaca_limits import quote_cache_put

                quote_cache_put(sym, out[0], out[1])
            except Exception:
                pass
            return out
        # Second call also costs a data token
        try:
            from analytics.alpaca_limits import acquire_data_token

            if not acquire_data_token(cost=1.0).ok:
                return None
        except Exception:
            pass
        r2 = requests.get(
            f"{base}/v2/stocks/{sym}/trades/latest",
            headers=_data_headers(),
            timeout=15,
        )
        try:
            from analytics.alpaca_limits import honor_rate_limit_headers, note_data_429

            honor_rate_limit_headers(r2)
            if r2.status_code == 429:
                note_data_429()
        except Exception:
            pass
        if r2.ok:
            p = float((r2.json().get("trade") or {}).get("p") or 0)
            if p > 0:
                out = (p - 0.01, p + 0.01)
                try:
                    from analytics.alpaca_limits import quote_cache_put

                    quote_cache_put(sym, out[0], out[1])
                except Exception:
                    pass
                return out
        y = _yahoo_last_px(symbol)
        if y and y > 0:
            out = _nbbo_from_last(y)
            if out:
                try:
                    from analytics.alpaca_limits import quote_cache_put

                    quote_cache_put(sym, out[0], out[1])
                except Exception:
                    pass
                log.info("[ALPACA] quote fallback yahoo last %s $%.2f", sym, y)
                return out
        return None
    except Exception as e:
        log.warning("[ALPACA] quote failed %s: %s", sym, e)
        y = _yahoo_last_px(symbol)
        if y and y > 0:
            out = _nbbo_from_last(y)
            if out:
                log.info("[ALPACA] quote fallback yahoo last %s $%.2f (after err)", sym, y)
                return out
        return None


def _tick_for_px(px: float) -> float:
    p = float(px)
    if p >= 1.0:
        return 0.01
    if p >= 0.1:
        return 0.001
    return 0.0001


def _floor_qty(qty: float, ndigits: int = 8) -> float:
    """Never round *up* past available crypto dust (Alpaca 40310000)."""
    import math

    q = float(qty)
    if q <= 0:
        return 0.0
    scale = 10 ** int(ndigits)
    return math.floor(q * scale + 1e-12) / scale


def _qty_str(qty: float, *, avail: float | None = None) -> str:
    q = float(qty)
    if avail is not None:
        try:
            q = min(q, float(avail))
        except (TypeError, ValueError):
            pass
    q = _floor_qty(q)
    if q <= 0:
        return "0"
    return f"{q:.8f}".rstrip("0").rstrip(".") or "0"


def _nbbo_from_last(px: float) -> tuple[float, float] | None:
    """Tight synthetic NBBO around last/model px when IEX has no bid/ask."""
    p = float(px)
    if not (p > 0):
        return None
    tick = _tick_for_px(p)
    return (max(tick, p - tick), p + tick)


def _yahoo_last_px(symbol: str) -> float | None:
    try:
        from analytics.day_trade_yahoo import fetch_yahoo_bars

        df = fetch_yahoo_bars(symbol)
        if df is None or df.empty or "Close" not in df.columns:
            return None
        v = float(df["Close"].iloc[-1])
        return v if v > 0 else None
    except Exception:
        return None


def _route_symbol(symbol: str) -> str:
    """Return the symbol in the format Alpaca expects.

    - Equities/ETFs: Alpaca class-share dots (BRK.B), with legacy alias mapping (SQ -> XYZ).
    - Crypto: BTC-USD (Yahoo) -> BTC/USD (Alpaca).
    """
    if is_crypto_symbol(symbol):
        return alpaca_symbol(symbol)
    try:
        from symbol_aliases import alpaca_equity_symbol

        return alpaca_equity_symbol(symbol)
    except Exception:
        return price_feed_symbol(symbol)


def _tif(symbol: str) -> str:
    """Crypto requires GTC; equities default to DAY (overridable via ALPACA_TIF)."""
    if is_crypto_symbol(symbol):
        return "gtc"
    return os.getenv("ALPACA_TIF", "day").lower()


_ACCT_CACHE: tuple[float, dict] | None = None
_POS_CACHE: tuple[float, list[dict]] | None = None
_ORDERS_CACHE: tuple[float, list[dict]] | None = None
_ORDERS_UNREADABLE_UNTIL = 0.0


def _rest_cache_sec() -> float:
    """TTL for account/position GET cache — long enough to dodge 429, short enough after fills."""
    try:
        return max(2.0, float(os.getenv("ALPACA_REST_CACHE_SEC", "8")))
    except (TypeError, ValueError):
        return 8.0


def invalidate_rest_cache() -> None:
    """Drop account/position/order cache after any order so buying_power is not stale."""
    global _ACCT_CACHE, _POS_CACHE, _ORDERS_CACHE
    _ACCT_CACHE = None
    _POS_CACHE = None
    _ORDERS_CACHE = None


def _stale_on_429(cache: tuple[float, dict] | tuple[float, list] | None):
    if cache and time.time() - cache[0] < max(120.0, _rest_cache_sec() * 6):
        return cache[1]
    return None


def list_positions() -> list[dict]:
    """Open positions from Alpaca trading API (empty list on error)."""
    global _POS_CACHE
    k, _ = _keys()
    if not k:
        return []
    now = time.time()
    if _POS_CACHE and now - _POS_CACHE[0] < _rest_cache_sec():
        return list(_POS_CACHE[1])
    base = _normalize_base(os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets"))
    try:
        r = _request_with_retry(
            "GET", f"{base}/v2/positions", headers=_trade_headers(), timeout=20
        )
        r.raise_for_status()
        body = r.json()
        out = list(body) if isinstance(body, list) else []
        _POS_CACHE = (now, out)
        return out
    except Exception as e:
        stale = _stale_on_429(_POS_CACHE)
        if stale is not None:
            return list(stale)
        log.warning("[ALPACA] list positions failed: %s", e)
        return []


def get_position(symbol: str) -> dict | None:
    """Single position dict (qty, avg_entry_price, unrealized_plpc, ...) or None."""
    sym = _route_symbol(symbol)
    want = str(symbol or "").strip().upper()
    for p in list_positions():
        ps = str(p.get("symbol", "") or "").upper()
        if ps == sym.upper() or ps == want:
            return p
        try:
            from crypto_universe import is_crypto_symbol, same_crypto

            if is_crypto_symbol(want) and is_crypto_symbol(ps) and same_crypto(ps, want):
                return p
        except Exception:
            pass
    return None


def _order_book_unreadable() -> bool:
    return time.time() < _ORDERS_UNREADABLE_UNTIL and _ORDERS_CACHE is None


def list_open_orders(symbol: str | None = None, status: str = "open") -> list[dict]:
    """Open/pending Alpaca orders; optional filter by symbol.

    Cached like positions so a fortress scan does not 429 the order book.
    On HTTP failure: return stale cache; if none, mark unreadable so buys skip
    (empty-list-on-error was submitting duplicates).
    """
    global _ORDERS_CACHE, _ORDERS_UNREADABLE_UNTIL
    base = _normalize_base(os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets"))
    params: dict[str, str] = {"status": status, "limit": "500"}
    now = time.time()
    want = _route_symbol(symbol) if symbol else None

    def _filter(rows: list[dict]) -> list[dict]:
        if not want:
            return list(rows)
        out = []
        for o in rows:
            osym = str(o.get("symbol") or "").upper()
            if osym == want:
                out.append(o)
                continue
            try:
                from crypto_universe import is_crypto_symbol, same_crypto

                if is_crypto_symbol(want) and is_crypto_symbol(osym) and same_crypto(osym, want):
                    out.append(o)
            except Exception:
                pass
        return out

    if status == "open" and _ORDERS_CACHE and now - _ORDERS_CACHE[0] < _rest_cache_sec():
        return _filter(_ORDERS_CACHE[1])
    try:
        r = requests.get(f"{base}/v2/orders", headers=_trade_headers(), params=params, timeout=20)
        r.raise_for_status()
        body = r.json()
        rows = list(body) if isinstance(body, list) else []
        if status == "open":
            _ORDERS_CACHE = (now, rows)
            _ORDERS_UNREADABLE_UNTIL = 0.0
        return _filter(rows)
    except Exception as e:
        log.warning("[ALPACA] list orders failed: %s", e)
        stale = _stale_on_429(_ORDERS_CACHE)
        if stale is not None:
            return _filter(list(stale))
        _ORDERS_UNREADABLE_UNTIL = now + max(15.0, _rest_cache_sec() * 2)
        return []


_HFT_CLIENT_PREFIXES = ("obi-", "flat-", "mr-", "earn-", "micro-", "scalp-")


def _is_hft_client_order(order: dict) -> bool:
    cid = str(order.get("client_order_id") or "").lower()
    return any(cid.startswith(p) for p in _HFT_CLIENT_PREFIXES)


def cancel_open_orders(
    symbol: str | None = None,
    *,
    keep_sells: bool = False,
    skip_hft: bool = False,
) -> int:
    """Cancel open orders (all or for one symbol). Returns count cancelled.

    skip_hft=True keeps HFT/micro resting buys alive (fortress resize must not wipe them).
    """
    base = _normalize_base(os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets"))
    n = 0
    for o in list_open_orders(symbol):
        if keep_sells and str(o.get("side", "")).lower() == "sell":
            continue
        if skip_hft and _is_hft_client_order(o):
            continue
        oid = o.get("id")
        if not oid:
            continue
        try:
            r = requests.delete(f"{base}/v2/orders/{oid}", headers=_trade_headers(), timeout=20)
            if r.status_code in (200, 204):
                n += 1
                log.warning("[ALPACA] cancelled order %s %s", o.get("symbol"), oid)
        except Exception as e:
            log.warning("[ALPACA] cancel order %s failed: %s", oid, e)
    return n


def cancel_all_open_orders(*, skip_hft: bool = False) -> int:
    """Wipe the working book (buys + sells). Bulk DELETE then per-id leftover."""
    if skip_hft:
        return cancel_open_orders(None, keep_sells=False, skip_hft=True)
    base = _normalize_base(os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets"))
    n = 0
    try:
        r = requests.delete(f"{base}/v2/orders", headers=_trade_headers(), timeout=30)
        if r.status_code in (200, 204, 207):
            body = r.json() if r.content else []
            if isinstance(body, list):
                n = len(body)
            log.warning("[ALPACA] bulk-cancelled open orders n=%s http=%s", n, r.status_code)
        else:
            log.warning("[ALPACA] bulk cancel HTTP %s: %s", r.status_code, (r.text or "")[:200])
    except Exception as e:
        log.warning("[ALPACA] bulk cancel failed: %s", e)
    leftover = cancel_open_orders(None, keep_sells=False, skip_hft=False)
    return n + leftover


def get_order(order_id: str) -> dict | None:
    """GET /v2/orders/{id}. None if missing / error."""
    oid = str(order_id or "").strip()
    if not oid:
        return None
    base = _normalize_base(os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets"))
    try:
        r = _request_with_retry(
            "GET",
            f"{base}/v2/orders/{oid}",
            headers=_trade_headers(),
            timeout=15,
        )
        if r.status_code == 404:
            return None
        r.raise_for_status()
        body = r.json()
        return body if isinstance(body, dict) else None
    except Exception as e:
        log.warning("[ALPACA] get order %s failed: %s", oid, e)
        return None


def cancel_order(order_id: str) -> bool:
    """DELETE /v2/orders/{id}. True if cancelled or already gone."""
    oid = str(order_id or "").strip()
    if not oid:
        return False
    base = _normalize_base(os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets"))
    try:
        r = requests.delete(f"{base}/v2/orders/{oid}", headers=_trade_headers(), timeout=20)
        if r.status_code in (200, 204, 404, 422):
            return True
        log.warning("[ALPACA] cancel order %s HTTP %s: %s", oid, r.status_code, (r.text or "")[:160])
        return False
    except Exception as e:
        log.warning("[ALPACA] cancel order %s failed: %s", oid, e)
        return False


def replace_limit_order(order_id: str, limit_price: float, *, qty: float | None = None) -> bool:
    """PATCH /v2/orders/{id} — reprice in place. One request, no cancel→reissue."""
    oid = str(order_id or "").strip()
    if not oid:
        return False
    try:
        lp = float(limit_price)
    except (TypeError, ValueError):
        return False
    if lp <= 0:
        return False
    base = _normalize_base(os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets"))
    body: dict = {"limit_price": _limit_price_str(lp)}
    if qty is not None:
        try:
            q = float(qty)
        except (TypeError, ValueError):
            q = 0.0
        if q > 0:
            body["qty"] = str(int(q) if q >= 1 else q)
    try:
        r = requests.patch(
            f"{base}/v2/orders/{oid}",
            headers=_trade_headers(),
            json=body,
            timeout=20,
        )
        if r.status_code in (200, 204):
            try:
                from analytics.fill_persist import record

                record("reprice")
            except Exception:
                pass
            return True
        log.warning("[ALPACA] replace order %s HTTP %s: %s", oid, r.status_code, (r.text or "")[:160])
        return False
    except Exception as e:
        log.warning("[ALPACA] replace order %s failed: %s", oid, e)
        return False


def position_qty_available(symbol: str) -> float | None:
    """Shares free to trade (excludes qty held by open orders)."""
    pos = get_position(symbol)
    if not pos:
        return None
    try:
        avail = pos.get("qty_available")
        if avail is not None:
            return abs(float(avail))
    except (TypeError, ValueError):
        pass
    try:
        from analytics.alpaca_limits import available_qty_for_sell

        held = 0.0
        try:
            held = float(pos.get("held_for_orders") or 0)
        except (TypeError, ValueError):
            held = 0.0
        open_sell = 0.0
        for o in open_sell_orders(symbol):
            try:
                open_sell += abs(float(o.get("qty") or 0) - float(o.get("filled_qty") or 0))
            except (TypeError, ValueError):
                pass
        return available_qty_for_sell(pos, open_sell_qty=max(held, open_sell))
    except Exception:
        pass
    try:
        return abs(float(pos.get("qty") or 0))
    except (TypeError, ValueError):
        return None


_ASSET_MEMO: dict[str, tuple[float, dict | None]] = {}


def fetch_asset(symbol: str) -> dict | None:
    """GET /v2/assets/{symbol} — fractionable, easy_to_borrow, etc. Cached ~1h."""
    sym = _route_symbol(symbol)
    now = time.time()
    hit = _ASSET_MEMO.get(sym)
    if hit and now - hit[0] < float(os.getenv("ALPACA_ASSET_CACHE_SEC", "3600")):
        return hit[1]
    k, _ = _keys()
    if not k:
        return None
    base = _normalize_base(os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets"))
    try:
        r = _request_with_retry(
            "GET", f"{base}/v2/assets/{sym}", headers=_trade_headers(), timeout=15
        )
        if not r.ok:
            _ASSET_MEMO[sym] = (now, None)
            return None
        js = r.json()
        _ASSET_MEMO[sym] = (now, js if isinstance(js, dict) else None)
        return _ASSET_MEMO[sym][1]
    except Exception as e:
        log.debug("[ALPACA] asset fetch %s: %s", sym, e)
        return None


def open_sell_orders(symbol: str | None = None) -> list[dict]:
    sym = _route_symbol(symbol) if symbol else None
    out: list[dict] = []
    for o in list_open_orders(sym):
        if str(o.get("side", "")).lower() != "sell":
            continue
        status = str(o.get("status", "")).lower()
        if status in ("accepted", "new", "pending_new", "partially_filled"):
            out.append(o)
    return out


def open_buy_orders(symbol: str | None = None) -> list[dict]:
    sym = _route_symbol(symbol) if symbol else None
    out: list[dict] = []
    for o in list_open_orders(sym):
        if str(o.get("side", "")).lower() != "buy":
            continue
        status = str(o.get("status", "")).lower()
        if status in ("accepted", "new", "pending_new", "partially_filled", "held", "accepted"):
            out.append(o)
    return out


def pending_buy_order(symbol: str) -> dict | None:
    if _order_book_unreadable():
        return {"id": "_unreadable", "symbol": str(symbol or "").upper(), "status": "unknown"}
    buys = open_buy_orders(symbol)
    return buys[0] if buys else None


def _duplicate_buy_blocked(symbol: str) -> bool:
    """True if an open buy exists or we just submitted the same ticket."""
    if pending_buy_order(symbol):
        return True
    try:
        from analytics.order_fingerprint import recently_submitted

        if recently_submitted(symbol, side="buy"):
            return True
    except Exception:
        pass
    return False


def _note_buy_submitted(symbol: str) -> None:
    try:
        from analytics.order_fingerprint import record_submit

        record_submit(symbol, side="buy")
    except Exception:
        pass


def cancel_extra_working_buys() -> int:
    """Keep the oldest working buy per symbol; cancel extras (repeat-FIRE residue)."""
    rows = list_open_orders(None)
    if _order_book_unreadable() and not rows:
        return 0
    by_sym: dict[str, list[dict]] = {}
    for o in rows:
        if str(o.get("side") or "").lower() != "buy":
            continue
        status = str(o.get("status") or "").lower()
        if status not in ("accepted", "new", "pending_new", "partially_filled", "held"):
            continue
        sym = str(o.get("symbol") or "").upper()
        if not sym:
            continue
        by_sym.setdefault(sym, []).append(o)
    n = 0
    base = _normalize_base(os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets"))
    for sym, buys in by_sym.items():
        if len(buys) <= 1:
            continue
        buys.sort(key=lambda o: str(o.get("created_at") or o.get("submitted_at") or ""))
        for o in buys[1:]:
            oid = o.get("id")
            if not oid:
                continue
            try:
                r = requests.delete(f"{base}/v2/orders/{oid}", headers=_trade_headers(), timeout=20)
                if r.status_code in (200, 204):
                    n += 1
                    log.warning("[ALPACA] cancelled extra working buy %s %s", sym, oid)
            except Exception as e:
                log.warning("[ALPACA] cancel extra buy %s failed: %s", oid, e)
    if n:
        invalidate_rest_cache()
    return n


def fortress_buy_should_cancel(
    order: dict,
    keep: set[str],
    *,
    skip_hft: bool = True,
) -> bool:
    """True if a resting buy is for a name that left the live ranked set.

    Default off: cancelling offlist names just so the next pass re-issues the
    same ticket is the cancel→repeat bleed. Set FORTRESS_CANCEL_OFFLIST=true
    to restore the old ranked-set sweeper.
    """
    if os.getenv("FORTRESS_CANCEL_OFFLIST", "false").lower() not in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return False
    if str(order.get("side", "")).lower() != "buy":
        return False
    if skip_hft and _is_hft_client_order(order):
        return False
    return str(order.get("symbol") or "").upper() not in keep


def cancel_buys_outside_keep(keep: set[str], *, skip_hft: bool = True) -> int:
    """Cancel non-HFT resting buys whose symbol is not in keep. Leaves working entries."""
    if not keep:
        return 0
    keep_u = {str(s).upper() for s in keep if s}
    min_age = float(os.getenv("FORTRESS_CANCEL_BUY_MIN_AGE_SEC", "180"))
    now = time.time()
    n = 0
    base = _normalize_base(os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets"))
    for o in list_open_orders(None):
        if not fortress_buy_should_cancel(o, keep_u, skip_hft=skip_hft):
            continue
        created = str(o.get("created_at") or o.get("submitted_at") or "")
        if min_age > 0 and created:
            try:
                from datetime import datetime, timezone

                ts = created.replace("Z", "+00:00")
                age = now - datetime.fromisoformat(ts).astimezone(timezone.utc).timestamp()
                if age < min_age:
                    continue
            except Exception:
                pass
        oid = o.get("id")
        if not oid:
            continue
        try:
            r = requests.delete(f"{base}/v2/orders/{oid}", headers=_trade_headers(), timeout=20)
            if r.status_code in (200, 204):
                n += 1
                log.info("[ALPACA] cancelled offlist buy %s %s", o.get("symbol"), oid)
                try:
                    from analytics.order_fingerprint import record_cancel

                    record_cancel(str(o.get("symbol") or ""), side="buy", reason="offlist")
                except Exception:
                    pass
        except Exception as e:
            log.warning("[ALPACA] cancel offlist buy %s failed: %s", oid, e)
    return n


def cancel_duplicate_sell_orders(symbol: str) -> int:
    """Keep one full close sell; cancel extras that cause 'insufficient qty' errors."""
    sells = open_sell_orders(symbol)
    if len(sells) <= 1:
        return 0
    sells.sort(key=lambda o: abs(float(o.get("qty") or 0)), reverse=True)
    base = _normalize_base(os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets"))
    n = 0
    for o in sells[1:]:
        oid = o.get("id")
        if not oid:
            continue
        try:
            r = requests.delete(f"{base}/v2/orders/{oid}", headers=_trade_headers(), timeout=20)
            if r.status_code in (200, 204):
                n += 1
                log.warning("[ALPACA] cancelled duplicate sell %s %s", o.get("symbol"), oid)
        except Exception as e:
            log.warning("[ALPACA] cancel duplicate sell %s failed: %s", oid, e)
    return n


def _order_age_sec(order: dict) -> float | None:
    raw = order.get("created_at") or order.get("submitted_at")
    if not raw:
        return None
    try:
        from datetime import datetime, timezone

        ts = str(raw).replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds())
    except Exception:
        return None


def cancel_stale_sell_orders(symbol: str, *, max_age_sec: int | None = None) -> int:
    """Cancel unfillable / off-touch sell *limits* so fortress can re-price.

    Never cancel market closes. Full-position closes ARE eligible. Fillable HFT
    flats stay; unfillable HFT DAY sells are cancelled so they can rest at the ask.
    """
    from analytics.limit_pricing import (
        sell_already_priced,
        sell_limit_unfillable,
        working_sell_needs_reprice,
    )

    max_age = max_age_sec if max_age_sec is not None else int(
        os.getenv("ALPACA_STALE_CLOSE_ORDER_SEC", "120")
    )
    min_unfill = float(os.getenv("ALPACA_UNFILLABLE_SELL_MIN_AGE_SEC", "30"))
    base = _normalize_base(os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets"))
    q = get_quote_bid_ask(symbol)
    bid = ask = 0.0
    if q:
        bid, ask = q
    entry = 0.0
    pos = get_position(symbol)
    if pos:
        try:
            entry = float(pos.get("avg_entry_price") or 0)
        except (TypeError, ValueError):
            entry = 0.0
    n = 0
    for o in open_sell_orders(symbol):
        if str(o.get("type", "")).lower() == "market":
            continue
        age = _order_age_sec(o)
        st = str(o.get("status", "")).lower()
        if st in ("filled", "canceled", "cancelled", "expired"):
            continue
        try:
            lp = float(o.get("limit_price") or 0)
        except (TypeError, ValueError):
            lp = 0.0
        # Leave fillable HFT flats alone. Unfillable HFT DAY sells (META/V above
        # the ask) get repriced here so they actually exit after an HFT restart.
        if _is_hft_client_order(o) and not (
            bid > 0 and ask > 0 and sell_limit_unfillable(lp, bid, ask)
        ):
            continue
        if bid > 0 and ask > 0:
            if not working_sell_needs_reprice(
                lp,
                bid,
                ask,
                age,
                max_age_sec=float(max_age),
                min_unfillable_age_sec=min_unfill,
                entry_px=entry,
            ):
                continue
            if sell_already_priced(lp, bid, ask, entry):
                continue
        elif age is None or age < max_age:
            continue
        oid = o.get("id")
        if not oid:
            continue
        try:
            r = requests.delete(f"{base}/v2/orders/{oid}", headers=_trade_headers(), timeout=20)
            if r.status_code in (200, 204):
                n += 1
                log.warning(
                    "[ALPACA] cancelled stale sell %s %s (age=%.0fs limit=%s bid=%.2f ask=%.2f status=%s)",
                    o.get("symbol"),
                    oid,
                    age if age is not None else -1,
                    o.get("limit_price"),
                    bid,
                    ask,
                    st,
                )
        except Exception as e:
            log.warning("[ALPACA] cancel stale sell %s failed: %s", oid, e)
    if n:
        invalidate_rest_cache()
    return n


def reprice_working_sells(symbol: str) -> int:
    """Cancel an unfillable/stale non-HFT sell and rest a fillable sell-high ticket."""
    n = cancel_stale_sell_orders(symbol)
    if n <= 0:
        return 0
    # Cancel → qty_available=0 is a race. Brief unlock wait, then place anyway.
    time.sleep(float(os.getenv("ALPACA_SELL_UNLOCK_SLEEP_SEC", "0.6")))
    invalidate_rest_cache()
    pos = get_position(symbol)
    if not pos or abs(float(pos.get("qty") or 0)) <= 1e-8:
        return n
    leftover = [
        o
        for o in open_sell_orders(symbol)
        if str(o.get("status") or "").lower() not in ("pending_cancel", "pending_replace")
    ]
    if leftover:
        log.info(
            "[ALPACA] reprice %s — %d sell(s) still working after cancel, skip place",
            symbol,
            len(leftover),
        )
        return n
    q = get_quote_bid_ask(symbol)
    if not q:
        log.warning("[ALPACA] reprice %s — no quote after cancel, will retry next pass", symbol)
        return n
    bid, ask = q
    from analytics.limit_pricing import exit_limit_px, quote_is_sane

    entry = float(pos.get("avg_entry_price") or 0)
    lp = exit_limit_px("sell", bid, ask, entry, forced_loss=False)
    if lp is None or lp <= 0:
        log.warning("[ALPACA] reprice %s — no fillable limit (bid=%.2f ask=%.2f)", symbol, bid, ask)
        return n
    if entry > 0 and float(lp) + 1e-12 < entry:
        log.warning(
            "[ALPACA] skip reprice place %s — would sell below entry (lp=%s entry=%.2f)",
            symbol,
            _limit_price_str(lp),
            entry,
        )
        return n
    if not quote_is_sane(bid, ask) and not (bid <= float(lp) <= ask):
        log.warning(
            "[ALPACA] skip reprice place %s — quote too wide (bid=%.2f ask=%.2f lp=%s)",
            symbol,
            bid,
            ask,
            _limit_price_str(lp),
        )
        return n
    qty = abs(float(pos.get("qty") or 0))
    avail = position_qty_available(symbol)
    if avail is not None and avail > 1e-8:
        qty = min(qty, avail)
    if qty <= 1e-8:
        # We just cancelled the lock — still submit broker qty.
        qty = abs(float(pos.get("qty") or 0))
    if qty <= 1e-8:
        return n
    try:
        submit_limit_order(symbol, qty, "sell", lp)
        _mark_close_attempt(symbol)
        log.warning(
            "[ALPACA] repriced sell %s qty=%.4f @ %s (bid=%.2f ask=%.2f entry=%.2f)",
            _route_symbol(symbol),
            qty,
            _limit_price_str(lp),
            bid,
            ask,
            entry,
        )
    except Exception as e:
        log.warning("[ALPACA] reprice place %s failed: %s", symbol, e)
    return n


def cancel_stale_unfillable_buys() -> int:
    """Reprice (or cancel) fortress buys that cannot lift; never stack when add-on is off.

    Fill-persist: PATCH the limit to the bid instead of DELETE+POST. That is
    what kept us cancelling without ever using the 200/min fill budget.
    """
    from analytics.limit_pricing import buy_limit_unfillable

    min_age = float(os.getenv("ALPACA_STALE_UNFILLABLE_BUY_SEC", "900"))
    allow_addon = os.getenv("FORTRESS_ALLOW_ADD_ON", "false").lower() in ("1", "true", "yes")
    allow_dca = os.getenv("FORTRESS_ALLOW_DCA", "false").lower() in ("1", "true", "yes")
    base = _normalize_base(os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets"))
    n = 0
    for o in open_buy_orders(None):
        if _is_hft_client_order(o):
            continue
        sym = str(o.get("symbol") or "").replace("/", "-").upper()
        if not sym:
            continue
        age = _order_age_sec(o)
        if age is None or age < min_age:
            continue
        oid = o.get("id")
        if not oid:
            continue
        held = False
        try:
            pos = get_position(sym)
            held = bool(pos and abs(float(pos.get("qty") or 0)) > 1e-8)
        except Exception:
            held = False
        unfillable = False
        try:
            lp = float(o.get("limit_price") or 0)
        except (TypeError, ValueError):
            lp = 0.0
        q = get_quote_bid_ask(sym)
        bid = ask = 0.0
        if q and lp > 0:
            bid, ask = q
            unfillable = buy_limit_unfillable(lp, bid, ask)
        held_no_addon = bool(held and not allow_addon and not allow_dca)
        if not unfillable and not held_no_addon:
            continue
        if unfillable and not held_no_addon and q:
            try:
                from analytics.fill_persist import may_cancel_stale_buy, reprice_buy_limit

                new_lp = reprice_buy_limit(lp, bid, ask)
                if new_lp is not None and replace_limit_order(str(oid), new_lp):
                    log.info(
                        "[ALPACA] repriced stale buy %s %s @ %s → %s (age=%.0fs)",
                        sym,
                        oid,
                        o.get("limit_price"),
                        new_lp,
                        age,
                    )
                    continue
                if not may_cancel_stale_buy(unfillable=True, held_no_addon=False):
                    continue
            except Exception as e:
                log.debug("[ALPACA] reprice stale buy %s: %s", oid, e)
        try:
            r = requests.delete(f"{base}/v2/orders/{oid}", headers=_trade_headers(), timeout=20)
            if r.status_code in (200, 204):
                n += 1
                why = "held_no_addon" if held_no_addon else "unfillable"
                log.warning(
                    "[ALPACA] cancelled stale buy %s %s (%s age=%.0fs limit=%s)",
                    sym,
                    oid,
                    why,
                    age,
                    o.get("limit_price"),
                )
                try:
                    from analytics.fill_persist import record

                    record("cancel")
                except Exception:
                    pass
        except Exception as e:
            log.warning("[ALPACA] cancel stale buy %s failed: %s", oid, e)
    if n:
        invalidate_rest_cache()
    return n


def _stuck_extended_market_close(order: dict, symbol: str) -> bool:
    """Market close without extended_hours cannot fill in pre/after-hours.

    Only treat as stuck after ALPACA_STUCK_MARKET_CLOSE_SEC (default 15m) so we
    don't cancel/reissue every hygiene tick (that caused the SBUX/AMZN cancel storm).
    """
    if str(order.get("type", "")).lower() != "market":
        return False
    if not _extended_hours_enabled(symbol):
        return False
    if order.get("extended_hours") in (True, "true", 1):
        return False
    st = str(order.get("status", "")).lower()
    if st not in ("accepted", "new", "pending_new", "partially_filled"):
        return False
    age = _order_age_sec(order)
    min_age = float(os.getenv("ALPACA_STUCK_MARKET_CLOSE_SEC", "900"))
    if age is None or age < min_age:
        return False
    return True


_CLOSE_ATTEMPT: dict[str, float] = {}


def _close_cooldown_path(symbol: str) -> Path:
    """Cross-process close cooldown (hygiene + fortress + day-trade share this)."""
    root = Path(os.getenv("FATE_ROOT") or Path(__file__).resolve().parent)
    d = root / "data" / "ops" / "close_cooldown"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{_route_symbol(symbol)}.ts"


def _close_cooldown_ok(symbol: str) -> bool:
    """Rate-limit close submissions per symbol (default 5 min, file + memory)."""
    sym = _route_symbol(symbol)
    gap = float(os.getenv("ALPACA_CLOSE_ATTEMPT_COOLDOWN_SEC", "300"))
    now = time.time()
    last = _CLOSE_ATTEMPT.get(sym, 0.0)
    try:
        p = _close_cooldown_path(sym)
        if p.is_file():
            last = max(last, float(p.read_text(encoding="utf-8").strip() or 0))
    except Exception:
        pass
    if gap > 0 and now - last < gap:
        log.info(
            "[ALPACA] close cooldown %s — last attempt %.0fs ago (gap=%.0fs)",
            sym,
            now - last,
            gap,
        )
        return False
    return True


def _mark_close_attempt(symbol: str) -> None:
    sym = _route_symbol(symbol)
    now = time.time()
    _CLOSE_ATTEMPT[sym] = now
    try:
        _close_cooldown_path(sym).write_text(f"{now:.3f}\n", encoding="utf-8")
    except Exception:
        pass


def pending_close_order(symbol: str) -> dict | None:
    """Return an open flatten order (sell for longs, buy-to-cover for shorts)."""
    pos = get_position(symbol)
    if not pos:
        return None
    pos_qty = abs(float(pos.get("qty") or 0))
    if pos_qty <= 0:
        return None
    avail = position_qty_available(symbol)
    is_short = str(pos.get("side") or "").lower() == "short" or float(pos.get("qty") or 0) < 0
    working = open_buy_orders(symbol) if is_short else open_sell_orders(symbol)
    if not working:
        return None
    best = max(working, key=lambda o: abs(float(o.get("qty") or 0)))
    try:
        best_qty = abs(float(best.get("qty") or 0))
    except (TypeError, ValueError):
        best_qty = 0.0
    # All shares locked in pending sells (Alpaca UI "available: 0").
    if avail is not None and avail <= max(pos_qty * 0.02, 1e-6):
        return best
    if best_qty >= pos_qty * 0.95:
        return best
    # Market/limit sells often sit "accepted"/"new" before qty_available drops — still a close.
    st = str(best.get("status") or "").lower()
    if st in ("accepted", "new", "pending_new", "accepted_for_bidding") and best_qty >= pos_qty * 0.5:
        return best
    return None


def close_position_alpaca(
    symbol: str,
    *,
    force: bool = False,
    qty: float | None = None,
    head: str | None = None,
) -> bool:
    """Close position — sleeve-scoped when `qty`/`head` set (never wipe overnight inventory)."""
    sym = _route_symbol(symbol)
    base = _normalize_base(os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets"))
    # Any open flatten (sell long / buy-to-cover short) — wait (unless force + stuck).
    pos0 = get_position(symbol)
    is_short0 = bool(
        pos0
        and (
            str(pos0.get("side") or "").lower() == "short"
            or float(pos0.get("qty") or 0) < 0
        )
    )
    working = open_buy_orders(symbol) if is_short0 else open_sell_orders(symbol)
    if working and not force:
        if not is_short0:
            try:
                reprice_working_sells(sym)
            except Exception as e:
                log.debug("[ALPACA] reprice working sells %s: %s", sym, e)
            working = open_sell_orders(symbol)
        if working:
            log.info(
                "[ALPACA] close already has %d open flatten order(s) for %s — waiting (no cancel/reissue)",
                len(working),
                sym,
            )
            return True
    cancel_duplicate_sell_orders(symbol)
    queued = pending_close_order(symbol)
    if queued and not force:
        if _stuck_extended_market_close(queued, symbol):
            oid = queued.get("id")
            if oid and _close_cooldown_ok(symbol):
                try:
                    r = requests.delete(
                        f"{base}/v2/orders/{oid}",
                        headers=_trade_headers(),
                        timeout=20,
                    )
                    if r.status_code in (200, 204):
                        log.warning(
                            "[ALPACA] cancelled stuck pre-market market close %s %s — re-placing as extended limit",
                            sym,
                            oid,
                        )
                        queued = None
                        _mark_close_attempt(symbol)
                except Exception as e:
                    log.warning("[ALPACA] cancel stuck market close %s failed: %s", oid, e)
            elif queued:
                log.info(
                    "[ALPACA] stuck market close %s still cooling down — leave order %s",
                    sym,
                    queued.get("id"),
                )
                return True
        if queued:
            log.info(
                "[ALPACA] close already queued for %s (order %s status=%s) — waiting for fill",
                sym,
                queued.get("id"),
                queued.get("status"),
            )
            return True
    if not force and not _close_cooldown_ok(symbol):
        return True
    avail = position_qty_available(symbol)
    if avail is not None and avail <= 1e-8 and queued and not force:
        return True
    pos = get_position(symbol)
    broker_qty = abs(float(pos.get("qty") or 0)) if pos else 0.0
    leg_side = str(pos.get("side", "")).lower() if pos else "long"
    # Sleeve scope: day_trade/micro/hft must not sell fortress/weekly/longterm shares.
    close_qty = broker_qty
    if qty is not None and float(qty) > 0:
        close_qty = min(broker_qty, float(qty))
    elif head:
        try:
            from analytics.portfolio_slots import sellable_qty_for_head

            close_qty = sellable_qty_for_head(sym, head, broker_qty=broker_qty)
        except Exception:
            close_qty = broker_qty
    if close_qty <= 1e-8:
        log.info("[ALPACA] sleeve-scoped close %s head=%s — nothing sellable (protected)", sym, head)
        return False
    qty = close_qty
    # Sell-high exit routing. The raw DELETE /v2/positions below is a MARKET close
    # → sells at the bid (sell low). During extended hours Alpaca requires a limit;
    # during RTH we also prefer a limit (ALPACA_RTH_PREFER_LIMIT) so a profit-taking
    # close rests at the ask (sell high). A forced close (stop/risk) passes
    # forced_loss=True → marketable limit that crosses so the cut still fills.
    _ext_close = _extended_hours_enabled(symbol)
    _rth_limit_close = os.getenv("ALPACA_RTH_PREFER_LIMIT", "true").lower() in ("1", "true", "yes")
    if qty > 0 and (_ext_close or _rth_limit_close):
        from analytics.limit_pricing import exit_limit_px

        q = get_quote_bid_ask(symbol)
        entry = float(pos.get("avg_entry_price") or 0) if pos else 0.0
        if q:
            bid, ask = q
            # Winners rest at the touch (sell high). Underwater closes stay
            # at/above entry until green — do not auto-dump at the bid.
            if leg_side == "short":
                _forced = bool(force)
                lp = exit_limit_px("buy", bid, ask, entry, forced_loss=_forced)
                close_side = "buy"
            else:
                _forced = bool(force)
                lp = exit_limit_px("sell", bid, ask, entry, forced_loss=_forced)
                close_side = "sell"
        else:
            lp = None
            close_side = "buy" if leg_side == "short" else "sell"
        if lp and lp > 0:
            try:
                submit_limit_order(symbol, qty, close_side, lp)
                _mark_close_attempt(symbol)
                log.warning(
                    "[ALPACA] Extended limit close %s %s qty=%.4f @ %s (bid=%.2f ask=%.2f entry=%.2f)",
                    sym,
                    close_side,
                    qty,
                    _limit_price_str(lp),
                    q[0] if q else 0,
                    q[1] if q else 0,
                    entry,
                )
                return True
            except Exception as e:
                log.warning("[ALPACA] extended limit close %s failed: %s — trying DELETE", sym, e)

    # Never cancel a working full-close sell just to re-issue (QCOM thrash).
    queued2 = pending_close_order(symbol)
    if queued2 and not force:
        log.info(
            "[ALPACA] close already working for %s (order %s) — skip cancel/reissue",
            sym,
            queued2.get("id"),
        )
        return True
    cancelled = cancel_open_orders(
        sym,
        keep_sells=bool(queued2 and not force),
        skip_hft=True,
    )
    if cancelled:
        log.warning("[ALPACA] cancelled %d blocking order(s) for %s before close", cancelled, sym)
    # Overnight / closed session: Alpaca accepts market DELETE as "accepted" but they sit
    # unfilled until RTH — leave stuck open orders. Prefer defer unless exchange is open.
    try:
        from analytics.market_session import current_session, Session

        if current_session() == Session.CLOSED:
            crypto = False
            try:
                from crypto_universe import is_crypto_symbol

                crypto = is_crypto_symbol(symbol)
            except Exception:
                crypto = False
            if not crypto:
                log.warning(
                    "[ALPACA] defer market DELETE close %s — session closed (avoid stuck overnight sells)",
                    sym,
                )
                return False
    except Exception:
        pass
    # Partial sleeve close — never DELETE full broker position when qty < broker_qty
    if qty + 1e-6 < broker_qty:
        close_side = "buy" if leg_side == "short" else "sell"
        try:
            from analytics.limit_pricing import exit_limit_px

            q = get_quote_bid_ask(symbol)
            entry = float(pos.get("avg_entry_price") or 0) if pos else 0.0
            if q:
                bid, ask = q
                lp = exit_limit_px(
                    close_side,
                    bid,
                    ask,
                    entry,
                    forced_loss=bool(force),
                )
                submit_limit_order(symbol, qty, close_side, lp)
            else:
                submit_market_order(symbol, qty, close_side)
            log.warning(
                "[ALPACA] Sleeve-scoped close %s %s qty=%.4f (broker=%.4f head=%s) — overnight protected",
                sym,
                close_side,
                qty,
                broker_qty,
                head,
            )
            return True
        except Exception as e:
            log.warning("[ALPACA] sleeve-scoped close %s failed: %s", sym, e)
            return False
    # Market DELETE sells at the bid. Never dump a red long unless this is an
    # explicit force/stop — that's how TSLA was sold below the fill.
    if not force and leg_side != "short":
        try:
            entry_chk = float(pos.get("avg_entry_price") or 0) if pos else 0.0
        except (TypeError, ValueError):
            entry_chk = 0.0
        qdel = get_quote_bid_ask(symbol)
        if entry_chk > 0 and qdel:
            bid_d, _ask_d = qdel
            if bid_d + 1e-12 < entry_chk:
                log.warning(
                    "[ALPACA] skip market DELETE close %s — bid %.2f < entry %.2f (wait for green)",
                    sym,
                    bid_d,
                    entry_chk,
                )
                return False
    try:
        r = requests.delete(f"{base}/v2/positions/{sym}", headers=_trade_headers(), timeout=30)
        if r.status_code in (200, 204):
            log.warning("[ALPACA] Closed position %s", sym)
            return True
        body = r.text or ""
        # Shares locked in pending orders — cancel all and retry once
        if r.status_code == 403 and ("held_for_orders" in body or "insufficient" in body.lower()):
            cancel_open_orders(sym, keep_sells=False)
            import time

            time.sleep(0.5)
            r2 = requests.delete(f"{base}/v2/positions/{sym}", headers=_trade_headers(), timeout=30)
            if r2.status_code in (200, 204):
                log.warning("[ALPACA] Closed position %s (after order unlock)", sym)
                return True
            log.warning("[ALPACA] close position %s HTTP %s: %s", sym, r2.status_code, r2.text[:200])
            return False
        log.warning("[ALPACA] close position %s HTTP %s: %s", sym, r.status_code, body[:200])
    except Exception as e:
        log.warning("[ALPACA] close position %s failed: %s", sym, e)
    return False


def get_account() -> dict | None:
    """GET /v2/account — cash, equity, buying_power (Alpaca live JSON).

    Fields we size from: cash, equity, last_equity, buying_power,
    regt_buying_power, non_marginable_buying_power, long_market_value.
    PDT aliases (daytrading_buying_power) were removed 2026-07-06.
    """
    global _ACCT_CACHE
    k, _ = _keys()
    if not k:
        return None
    now = time.time()
    if _ACCT_CACHE and now - _ACCT_CACHE[0] < _rest_cache_sec():
        return dict(_ACCT_CACHE[1])
    base = _normalize_base(os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets"))
    try:
        r = _request_with_retry(
            "GET", f"{base}/v2/account", headers=_trade_headers(), timeout=15
        )
        r.raise_for_status()
        js = r.json()
        _ACCT_CACHE = (now, js)
        return js
    except Exception as e:
        stale = _stale_on_429(_ACCT_CACHE)
        if stale is not None:
            return dict(stale)
        log.warning("[ALPACA] account fetch failed: %s", e)
        return None


def get_portfolio_history(
    *,
    period: str | None = None,
    timeframe: str | None = None,
    extended_hours: bool = True,
) -> dict | None:
    """
    Read-only Alpaca portfolio equity history.

    GET /v2/account/portfolio/history — does not place orders.
    period examples: 1D, 1W, 1M, 3M, 6M, 1A, 2A, all
    timeframe examples: 1Min, 5Min, 15Min, 1H, 1D (Alpaca constrains by period length)
    """
    k, _ = _keys()
    if not k:
        return None
    base = _normalize_base(os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets"))
    params: dict[str, str | bool] = {}
    if period:
        params["period"] = period
    if timeframe:
        params["timeframe"] = timeframe
    if extended_hours:
        params["extended_hours"] = True
    try:
        r = _request_with_retry(
            "GET",
            f"{base}/v2/account/portfolio/history",
            headers=_trade_headers(),
            params=params,
            timeout=30,
        )
        r.raise_for_status()
        js = r.json()
        return js if isinstance(js, dict) else None
    except Exception as e:
        log.warning("[ALPACA] portfolio history fetch failed: %s", e)
        return None


def intraday_buying_power(acct: dict | None = None) -> float:
    """
    Available margin for intraday sizing (Alpaca 2026 intraday margin framework).

    Deprecated API fields (removed July 6, 2026): daytrading_buying_power,
    last_daytrading_buying_power — both now mirror buying_power; use buying_power only.
    """
    if acct is None:
        acct = get_account()
    if not acct:
        return 0.0
    # Prefer live buying_power; fall back to deprecated alias then cash.
    for key in ("buying_power", "daytrading_buying_power", "last_daytrading_buying_power", "cash"):
        try:
            v = acct.get(key)
            if v is not None and float(v) > 0:
                return float(v)
        except (TypeError, ValueError):
            continue
    return 0.0


def _extended_hours_enabled(symbol: str) -> bool:
    if is_crypto_symbol(symbol):
        return False
    return os.getenv("ALPACA_EXTENDED_HOURS", "false").lower() in ("1", "true", "yes")


def _round_limit_price(price: float) -> float:
    """Alpaca rejects sub-penny limits on most US equities."""
    p = float(price)
    if p <= 0:
        return p
    if p >= 1.0:
        return round(p, 2)
    if p >= 0.1:
        return round(p, 3)
    return round(p, 4)


def _limit_price_str(price: float) -> str:
    lp = _round_limit_price(price)
    if lp >= 1.0:
        return f"{lp:.2f}"
    if lp >= 0.1:
        return f"{lp:.3f}"
    return f"{lp:.4f}"


def _submit_notional_as_limit(
    symbol: str,
    side: str,
    notional: float,
    *,
    fallback_px: float | None = None,
) -> dict:
    """Extended session: Alpaca requires DAY/GTC limit orders (no market)."""
    from analytics.limit_pricing import entry_limit_px

    try:
        from analytics.alpaca_limits import preflight_buy, snap_qty_for_asset
    except ImportError:
        snap_qty_for_asset = None  # type: ignore
        preflight_buy = None  # type: ignore

    q = get_quote_bid_ask(symbol)
    overnight = False
    try:
        from analytics.market_session import Session, current_session

        overnight = current_session() != Session.REGULAR
    except Exception:
        overnight = False
    if q is not None:
        try:
            from analytics.limit_pricing import spread_pct

            bid0, ask0 = float(q[0] or 0), float(q[1] or 0)
            max_sp = float(
                os.getenv(
                    "ALPACA_MAX_ENTRY_SPREAD_PCT",
                    os.getenv("ALPACA_MAX_QUOTE_SPREAD_PCT", "0.015"),
                )
            )
            if bid0 <= 0 or ask0 <= 0 or (overnight and spread_pct(bid0, ask0) > max_sp):
                q = None
        except Exception:
            pass
    if q is None and fallback_px and float(fallback_px) > 0:
        q = _nbbo_from_last(float(fallback_px))
        log.info("[ALPACA] limit-notional using model px %s $%.2f", symbol, float(fallback_px))
    if q is None:
        raise ValueError(f"no quote for limit-notional {symbol}")
    bid, ask = q
    lp = entry_limit_px(side, bid, ask)
    if (lp is None or lp <= 0) and overnight and fallback_px and float(fallback_px) > 0:
        q = _nbbo_from_last(float(fallback_px))
        if q:
            bid, ask = q
            lp = entry_limit_px(side, bid, ask)
            log.info("[ALPACA] overnight wide-quote fallback %s px=%.2f", symbol, float(fallback_px))
    if lp is None or lp <= 0:
        raise ValueError(f"bad limit for {symbol}")
    qty = float(notional) / lp
    # Non-fractionable assets reject fractional qty (40310000)
    frac = True
    try:
        asset = fetch_asset(symbol)
        if asset is not None:
            frac = bool(asset.get("fractionable", True))
    except Exception:
        pass
    if snap_qty_for_asset is not None:
        qty = snap_qty_for_asset(qty, fractionable=frac)
    if qty <= 0:
        raise ValueError(f"notional too small for {symbol} @ {lp} (fractionable={frac})")
    if side.lower() == "buy" and preflight_buy is not None:
        try:
            acct = get_account() or {}
            bp = float(acct.get("buying_power") or acct.get("cash") or 0)
            chk = preflight_buy(
                symbol=symbol, notional=float(notional), buying_power=bp, fractionable=frac
            )
            if not chk.ok:
                raise RuntimeError(f"preflight_buy blocked: {chk.reason}")
        except RuntimeError:
            raise
        except Exception:
            pass
    return submit_limit_order(symbol, qty, side, lp)


_LAST_POST_SYNC_TS = 0.0


def _post_order_sync(symbol: str) -> None:
    """Background cooldown sync after any submitted order (watchdog runs full verify).

    Debounced: at high trade rates, spawning a sync subprocess per order hammers the
    Alpaca REST API and trips 429 rate limits (which then break account/position/order
    calls). Only run at most once per POST_ORDER_SYNC_MIN_SEC across all orders.
    """
    if os.getenv("POST_ORDER_SYNC", "true").lower() not in ("1", "true", "yes"):
        return
    global _LAST_POST_SYNC_TS
    import time as _t

    min_gap = float(os.getenv("POST_ORDER_SYNC_MIN_SEC", "20"))
    now = _t.time()
    if now - _LAST_POST_SYNC_TS < min_gap:
        return
    _LAST_POST_SYNC_TS = now
    try:
        import subprocess
        import sys
        import threading
        from pathlib import Path

        root = Path(__file__).resolve().parent

        def _bg() -> None:
            try:
                subprocess.run(
                    [sys.executable, "-u", str(root / "tools/sync_recent_trades.py")],
                    cwd=root,
                    check=False,
                    timeout=30,
                )
            except Exception:
                pass

        threading.Thread(target=_bg, daemon=True, name=f"sync-{symbol}").start()
    except Exception:
        pass


def _session_order_side(symbol: str, order_side: str) -> str:
    """Buy-to-cover a short is an exit, not a new long (must not wait for 06:00)."""
    side = (order_side or "buy").lower()
    if side != "buy":
        return side
    try:
        pos = get_position(symbol)
        if pos and str(pos.get("side") or "").lower() == "short" and float(pos.get("qty") or 0) < 0:
            return "close"
        if pos and float(pos.get("qty") or 0) < 0:
            return "close"
    except Exception:
        pass
    return side


def submit_market_order(
    symbol: str,
    qty: float | int | None = None,
    side: str = "buy",
    notional: float | None = None,
    *,
    for_hft: bool = False,
) -> dict:
    """Submit a market order. Either `qty` (whole or fractional shares) or `notional`
    (USD amount, fractional under the hood) must be set, but not both.
    """
    from analytics.market_session import log_session_block, orders_allowed

    _require_order_host()
    side_l = side.lower()
    order_side = "sell" if side_l == "sell" else "buy"
    sess_side = _session_order_side(symbol, order_side)
    ok, reason = orders_allowed(sess_side, for_hft=for_hft, symbol=symbol)
    if not ok:
        log_session_block("ALPACA", sess_side)
        raise RuntimeError(f"order blocked ({reason})")

    if order_side == "buy" and sess_side != "close":
        from intel.algo_risk_filter import gate_buy_order

        if not gate_buy_order(symbol, source="alpaca_market"):
            raise RuntimeError(f"order blocked (algo_risk {symbol})")

    sell_avail = None
    if order_side == "sell" and qty is not None:
        avail = position_qty_available(symbol)
        if avail is not None and avail <= 1e-8 and pending_close_order(symbol):
            log.info(
                "[ALPACA] sell skipped for %s — shares already in pending close order (do not re-liquidate in UI)",
                symbol,
            )
            return {"status": "pending_close", "symbol": _route_symbol(symbol)}
        if avail is not None and float(qty) > avail + 1e-6:
            log.warning(
                "[ALPACA] sell qty %.8f > available %.8f for %s — using available",
                float(qty),
                avail,
                symbol,
            )
            qty = avail
        if avail is not None and qty is not None:
            qty = _floor_qty(min(float(qty), float(avail)))
            sell_avail = float(avail)

    if (qty is None and notional is None) or (qty is not None and notional is not None):
        raise ValueError("submit_market_order: pass exactly one of qty / notional")

    try:
        from analytics.alpaca_limits import can_submit_order_pace

        pace = can_submit_order_pace()
        if not pace.ok:
            raise RuntimeError(f"order paced ({pace.reason})")
    except ImportError:
        pass

    # Buy-low / sell-high routing. A true market order pays the full spread
    # (buy the ask, sell the bid) → structural "buy high / sell low". Convert to a
    # bid/ask-anchored limit whenever we have a quote. Extended hours REQUIRES limit;
    # during RTH this is on by default (ALPACA_RTH_PREFER_LIMIT) and uses an
    # aggressive (marketable) limit so urgent fills still cross, but never worse than
    # ~ALPACA_LIMIT_SLIP_BPS past the touch instead of an uncapped market sweep.
    _ext = _extended_hours_enabled(symbol)
    _rth_limit = os.getenv("ALPACA_RTH_PREFER_LIMIT", "true").lower() in ("1", "true", "yes")
    if (_ext or _rth_limit) and not is_crypto_symbol(symbol):
        if notional is not None:
            try:
                return _submit_notional_as_limit(symbol, side, notional)
            except Exception:
                if _ext:
                    raise  # extended hours cannot fall back to market
        else:
            from analytics.limit_pricing import entry_limit_px

            q = get_quote_bid_ask(symbol)
            if q is not None:
                bid, ask = q
                # RTH: aggressive marketable limit (capped slippage) so the fill is
                # near-certain; extended: passive bid/ask anchor.
                lp = entry_limit_px(side, bid, ask, aggressive=(_rth_limit and not _ext))
                if lp and lp > 0:
                    return submit_limit_order(symbol, qty, side, lp)
            elif _ext:
                raise ValueError(f"no quote for extended-hours limit {symbol}")

    sym = _route_symbol(symbol)
    base = _normalize_base(os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets"))

    payload: dict = {
        "symbol": sym,
        "side": side.lower(),
        "type": "market",
        "time_in_force": _tif(symbol),
    }
    if qty is not None:
        payload["qty"] = _qty_str(qty, avail=sell_avail)
    else:
        payload["notional"] = f"{float(notional):.2f}"

    r = _request_with_retry(
        "POST",
        f"{base}/v2/orders",
        json=payload,
        headers=_trade_headers(),
        timeout=30,
        max_attempts=int(os.getenv("ALPACA_ORDER_RETRIES", "2")),
    )
    if not r.ok:
        log.warning("[ALPACA] order rejected %s %s: %s", side, sym, r.text[:240])
    r.raise_for_status()
    try:
        from analytics.slippage_audit import audit_slippage

        q = get_quote_bid_ask(symbol)
        mid = None
        if q is not None:
            bid, ask = q
            mid = (float(bid) + float(ask)) / 2.0 if bid and ask else None
        # Market: expect mid; adverse is crossing to ask (buy) / bid (sell).
        touch = None
        if q is not None:
            bid, ask = q
            touch = float(ask) if side_l == "buy" else float(bid)
        audit_slippage(
            symbol,
            side,
            expected_px=mid,
            submitted_px=touch or mid,
            qty=float(qty) if qty is not None else None,
            notional=float(notional) if notional is not None else None,
            source="alpaca_market",
        )
    except Exception:
        pass
    invalidate_rest_cache()
    _post_order_sync(symbol)
    return r.json()


def submit_limit_order(
    symbol: str,
    qty: float | int,
    side: str,
    limit_price: float,
    *,
    for_hft: bool = False,
    time_in_force: str | None = None,
) -> dict:
    from analytics.market_session import log_session_block, orders_allowed

    _require_order_host()
    side_l = side.lower()
    order_side = "sell" if side_l == "sell" else "buy"
    sess_side = _session_order_side(symbol, order_side)
    ok, reason = orders_allowed(sess_side, for_hft=for_hft, symbol=symbol)
    if not ok:
        log_session_block("ALPACA", sess_side)
        raise RuntimeError(f"order blocked ({reason})")

    if order_side == "buy" and sess_side != "close":
        from intel.algo_risk_filter import gate_buy_order

        if not gate_buy_order(symbol, source="alpaca_limit"):
            raise RuntimeError(f"order blocked (algo_risk {symbol})")

    # Unlock qty before sell — Alpaca 403 held_for_orders if a prior sell still open
    qty_f = float(qty)
    if order_side == "sell":
        if open_sell_orders(symbol):
            cancel_duplicate_sell_orders(symbol)
            # Unlock leftover non-HFT sells only — never wipe HFT flat-/close- tickets.
            cancel_open_orders(symbol, keep_sells=False, skip_hft=True)
            time.sleep(float(os.getenv("ALPACA_SELL_UNLOCK_SLEEP_SEC", "0.6")))
        avail = position_qty_available(symbol)
        if avail is not None:
            if avail <= 1e-8:
                if pending_close_order(symbol):
                    log.info("[ALPACA] limit sell skipped %s — close already queued / qty locked", symbol)
                    return {"status": "skipped_locked", "symbol": symbol}
                raise RuntimeError(f"insufficient qty available for sell {symbol}")
            qty_f = min(qty_f, avail)
            qty_f = _floor_qty(qty_f)
        try:
            asset = fetch_asset(symbol)
            if asset is not None and not bool(asset.get("fractionable", True)):
                qty_f = float(int(qty_f))
        except Exception:
            pass
        if qty_f <= 0:
            raise RuntimeError(f"sell qty snapped to 0 for {symbol}")

    try:
        from analytics.alpaca_limits import can_submit_order_pace

        pace = can_submit_order_pace()
        if not pace.ok:
            raise RuntimeError(f"order paced ({pace.reason})")
    except ImportError:
        pass

    sym = _route_symbol(symbol)
    base = _normalize_base(os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets"))
    lp = _round_limit_price(float(limit_price))
    tif = (time_in_force or _tif(symbol)).lower()
    # Alpaca rejects IOC/FOK in extended hours only — do not force DAY in RTH
    # just because ALPACA_EXTENDED_HOURS=true (that jammed HFT in-flight slots).
    try:
        from analytics.market_session import Session, current_session

        sess = current_session()
        if sess in (Session.PRE_MARKET, Session.POST_MARKET) and tif in ("ioc", "fok"):
            tif = "day"
    except Exception:
        if _extended_hours_enabled(symbol) and tif in ("ioc", "fok"):
            tif = "day"
    payload = {
        "symbol": sym,
        "qty": _qty_str(qty_f),
        "side": side.lower(),
        "type": "limit",
        "limit_price": _limit_price_str(lp),
        "time_in_force": tif,
    }
    if _extended_hours_enabled(symbol):
        payload["extended_hours"] = True
    r = _request_with_retry(
        "POST",
        f"{base}/v2/orders",
        json=payload,
        headers=_trade_headers(),
        timeout=30,
        max_attempts=int(os.getenv("ALPACA_ORDER_RETRIES", "2")),
    )
    if not r.ok:
        log.warning("[ALPACA] limit order rejected %s %s: %s", side, sym, r.text[:240])
        # One more unlock+retry on held_for_orders
        body = r.text or ""
        if r.status_code == 403 and ("held_for_orders" in body or "insufficient" in body.lower()):
            cancel_open_orders(symbol, keep_sells=False)
            time.sleep(0.7)
            avail2 = position_qty_available(symbol)
            if avail2 and avail2 > 0:
                payload["qty"] = _qty_str(qty_f, avail=avail2)
                r = _request_with_retry(
                    "POST",
                    f"{base}/v2/orders",
                    json=payload,
                    headers=_trade_headers(),
                    timeout=30,
                    max_attempts=1,
                )
                if not r.ok:
                    log.warning("[ALPACA] limit sell retry rejected %s: %s", sym, r.text[:200])
    r.raise_for_status()
    try:
        from analytics.slippage_audit import audit_slippage

        q = get_quote_bid_ask(symbol)
        mid = None
        if q is not None:
            bid, ask = q
            mid = (float(bid) + float(ask)) / 2.0 if bid and ask else None
        audit_slippage(
            symbol,
            side,
            expected_px=mid,
            submitted_px=float(lp),
            qty=float(qty_f),
            source="alpaca_limit",
        )
    except Exception:
        pass
    invalidate_rest_cache()
    _post_order_sync(symbol)
    return r.json()


def place_market_alpaca(symbol: str, qty: float | int, action: str) -> bool:
    if action.upper() == "SELL":
        if pending_close_order(symbol):
            log.info("[ALPACA] Market sell skipped for %s — close already queued", symbol)
            return True
        return close_position_alpaca(symbol)
    side = "buy"
    submit_market_order(symbol, qty=qty, side=side)
    log.warning("[ALPACA] Market %s %s x%s submitted", side, symbol, qty)
    return True


def place_limit_notional_alpaca(
    symbol: str,
    dollars: float,
    limit_price: float,
    action: str = "BUY",
) -> bool:
    """Limit buy/sell by notional at a fixed limit price (GTC/day per symbol rules)."""
    if dollars <= 0 or limit_price <= 0:
        return False
    side = "buy" if action.upper() == "BUY" else "sell"
    qty = float(dollars) / float(limit_price)
    if qty <= 0:
        return False
    submit_limit_order(symbol, qty, side, float(limit_price))
    log.warning(
        "[ALPACA] Limit %s %s $%.2f @ %s (~%.4f sh)",
        side,
        symbol,
        dollars,
        _limit_price_str(_round_limit_price(limit_price)),
        qty,
    )
    if side == "buy":
        _note_buy_submitted(symbol)
    return True


def place_smart_buy_alpaca(
    symbol: str,
    dollars: float,
    *,
    constraints: dict | None = None,
    fallback_px: float | None = None,
) -> bool:
    """Route buy as limit band (panic drop / sympathy) or default notional market."""
    # Never stack identical buy orders — causes held_for_orders / double notional spam
    if _duplicate_buy_blocked(symbol):
        log.info("[ALPACA] BUY skipped %s — duplicate open/recent buy", symbol)
        return False
    c = constraints or {}
    if str(c.get("entry_order_type", "")).lower() == "limit":
        lp = float(c.get("limit_price") or c.get("limit_high") or 0.0)
        lo = float(c.get("limit_low") or 0.0)
        hi = float(c.get("limit_high") or lp)
        if lp <= 0 and lo > 0 and hi >= lo:
            lp = (lo + hi) / 2.0
        if lp > 0:
            if lo > 0 and hi >= lo:
                log.info(
                    "[ALGO_RISK] %s LIMIT entry band $%.2f-$%.2f target $%.2f (not market open)",
                    symbol,
                    lo,
                    hi,
                    lp,
                )
            return place_limit_notional_alpaca(symbol, dollars, lp, "BUY")
    return place_notional_alpaca(symbol, dollars, "BUY", fallback_px=fallback_px)


def place_notional_alpaca(
    symbol: str,
    dollars: float,
    action: str,
    *,
    fallback_px: float | None = None,
) -> bool:
    """Fractional-share entry/exit by USD notional — limit at bid/ask when ALPACA_BUY_LOW=true."""
    if dollars <= 0:
        return False
    side = "buy" if action.upper() == "BUY" else "sell"
    if side == "buy":
        hard_max = float(os.getenv("HARD_MAX_ORDER_NOTIONAL", "0") or 0)
        if hard_max <= 0:
            hard_max = 0.0
        if hard_max > 0 and dollars > hard_max:
            log.warning(
                "[ALPACA] clamp BUY %s $%.0f → $%.0f (HARD_MAX_ORDER_NOTIONAL)",
                symbol,
                dollars,
                hard_max,
            )
            dollars = hard_max
        if dollars <= 0:
            return False
    if side == "buy" and _duplicate_buy_blocked(symbol):
        log.info("[ALPACA] notional BUY skipped %s — duplicate open buy", symbol)
        return False
    if side == "sell" and pending_close_order(symbol):
        log.info("[ALPACA] notional SELL skipped %s — close already queued", symbol)
        return True
    if os.getenv("ALPACA_BUY_LOW", "true").lower() in ("1", "true", "yes"):
        try:
            _submit_notional_as_limit(symbol, side, dollars, fallback_px=fallback_px)
            log.warning("[ALPACA] Limit-notional %s %s $%.2f submitted", side, symbol, dollars)
            if side == "buy":
                _note_buy_submitted(symbol)
            return True
        except Exception as e:
            sess = "unknown"
            try:
                from analytics.market_session import Session, current_session

                sess = str(current_session().value)
                if current_session() != Session.REGULAR:
                    log.warning(
                        "[ALPACA] limit-notional failed %s %s: %s — skip market fallback (%s)",
                        side,
                        symbol,
                        e,
                        sess,
                    )
                    return False
            except Exception:
                log.warning("[ALPACA] limit-notional failed %s %s: %s — skip market fallback", side, symbol, e)
                return False
            log.warning("[ALPACA] limit-notional failed %s %s: %s — market fallback", side, symbol, e)
    submit_market_order(symbol, side=side, notional=dollars)
    log.warning("[ALPACA] Notional %s %s $%.2f submitted", side, symbol, dollars)
    if side == "buy":
        _note_buy_submitted(symbol)
    return True


def place_short_alpaca(symbol: str, qty: float | int) -> bool:
    """Short open: simply submit a `sell` market order with no existing long.
    Alpaca requires the account to be margin-enabled and the asset to be shortable;
    crypto cannot be shorted directly (you'd need a perp on a different venue).
    """
    if is_crypto_symbol(symbol):
        log.warning("[ALPACA] Refused short on crypto %s (not supported on Alpaca spot)", symbol)
        return False
    submit_market_order(symbol, qty=qty, side="sell")
    log.warning("[ALPACA] SHORT open %s x%s submitted", symbol, qty)
    return True


def place_limit_mid_alpaca(symbol: str, qty: float | int, action: str) -> None:
    from analytics.limit_pricing import entry_limit_px

    q = get_quote_bid_ask(symbol)
    if q is None:
        place_market_alpaca(symbol, qty, action)
        return
    bid, ask = q
    side = "buy" if action.upper() == "BUY" else "sell"
    lp = entry_limit_px(side, bid, ask)
    if lp is None or lp <= 0:
        place_market_alpaca(symbol, qty, action)
        return
    submit_limit_order(symbol, qty, side, lp)
    log.info("[ALPACA] Limit %s %s @ %s (bid=%.2f ask=%.2f)", side, symbol, _limit_price_str(lp), bid, ask)


def place_is_zero_alpaca(
    symbol: str,
    target_notional: float,
    action: str,
    *,
    volatility: float = 0.02,
    volume_ratio: float = 1.0,
) -> bool:
    """IS-Zero style adaptive participation execution.

    Heuristic:
    - higher volatility -> reduce child order size (lower participation)
    - stronger volume_ratio -> increase participation
    - submit multiple midpoint attempts before fallback market notional
    """
    if target_notional <= 0:
        return False
    side = "buy" if action.upper() == "BUY" else "sell"
    vol = max(0.0, float(volatility))
    vr = max(0.2, float(volume_ratio))
    participation = max(0.08, min(0.35, 0.20 * vr / (1.0 + vol * 25.0)))
    child = max(25.0, target_notional * participation)
    remaining = float(target_notional)
    max_slices = int(os.getenv("IS_ZERO_MAX_SLICES", "8"))

    for _ in range(max_slices):
        if remaining <= 1.0:
            break
        chunk = min(child, remaining)
        mid = get_mid_price(symbol)
        try:
            if mid is not None and not is_crypto_symbol(symbol):
                # use qty for midpoint equity execution
                q = max(1e-6, chunk / max(mid, 1e-9))
                submit_limit_order(symbol, q, side, mid)
            else:
                # crypto + fallback routes use notional market child
                submit_market_order(symbol, side=side, notional=chunk)
            remaining -= chunk
        except Exception as e:
            log.warning("[ALPACA][IS_ZERO] child failed %s %s: %s", symbol, side, e)
            break

    if remaining > 1.0:
        # final sweep, guarantee completion
        submit_market_order(symbol, side=side, notional=remaining)
    log.info(
        "[ALPACA][IS_ZERO] %s %s target=%.2f participation=%.3f slices<=%d",
        side, symbol, target_notional, participation, max_slices
    )
    return True
