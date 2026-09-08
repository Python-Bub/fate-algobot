"""Historical news features for training + live (Finnhub company-news backfill).

Live paths (`paper_sim`, `fortress_live`) already call `composite_sentiment()` which uses
Finnhub + NewsAPI + Cramer **for the last few days only**. Offline `build_features()` had
sentiment columns hard-coded to 0.0 (no historical NewsAPI backfill). This module pulls
**Finnhub company-news** over `[start_date, end_date]` in small chunks (causal: articles
only affect their **publication day** and rolling windows after that day).

Requires `FINNHUB_API_KEY`. If missing or on fetch failure, all columns are zeros.

Toggle: `USE_TRAIN_NEWS_HISTORY=true` (default on when Finnhub key present — actually default true with zeros if no key).

Columns added to the feature frame (also listed in `ml_model.FEATURES`):

- `news_sent_roll_5d` — mean of daily mean headline sentiments over last 5 calendar days.
- `news_intensity_roll_5d` — rolling sum of article counts (5d), tanh-normalised to ~[0,1].
- `news_sent_trend_10d` — change in `news_sent_roll_5d` vs 10 days ago (momentum of tone).

Optional dated transcripts: `data/replay/transcripts/{SYM}.jsonl` lines with `ts` or `date`
ISO fields contribute `transcript_sent_roll_5d` (else column is zeros).
"""

from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests

from symbol_aliases import price_feed_symbol
from utils import log

FINNHUB_NEWS = "https://finnhub.io/api/v1/company-news"


def _b(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes")


def _chunk_days() -> int:
    return max(7, min(60, int(os.getenv("TRAIN_NEWS_CHUNK_DAYS", "30"))))


def _sleep_between_chunks() -> None:
    time.sleep(float(os.getenv("TRAIN_NEWS_HTTP_PAUSE_SEC", "0.15")))


def _article_day(item: dict[str, Any]) -> date | None:
    ts = item.get("datetime")
    try:
        if ts is None:
            return None
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(int(ts), tz=timezone.utc).date()
        s = str(ts)[:10]
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def _article_text(item: dict[str, Any]) -> str:
    h = (item.get("headline") or "").strip()
    s = (item.get("summary") or "").strip()
    return (h + " " + s).strip()


def fetch_finnhub_company_news_range(api_symbol: str, d0: date, d1: date) -> list[dict]:
    key = os.getenv("FINNHUB_API_KEY", "").strip()
    if not key or d0 > d1:
        return []
    out: list[dict] = []
    step = timedelta(days=_chunk_days())
    cur = d0
    while cur <= d1:
        chunk_end = min(cur + step - timedelta(days=1), d1)
        try:
            r = requests.get(
                FINNHUB_NEWS,
                params={
                    "symbol": api_symbol,
                    "from": cur.isoformat(),
                    "to": chunk_end.isoformat(),
                    "token": key,
                },
                timeout=float(os.getenv("TRAIN_NEWS_HTTP_TIMEOUT", "12")),
            )
            if r.status_code in (401, 403, 429):
                log.warning("[NEWS_HIST] Finnhub HTTP %s for %s", r.status_code, api_symbol)
                break
            r.raise_for_status()
            js = r.json()
            if isinstance(js, list):
                out.extend(js)
        except Exception as e:
            log.warning("[NEWS_HIST] Finnhub chunk %s..%s failed: %s", cur, chunk_end, e)
        cur = chunk_end + timedelta(days=1)
        _sleep_between_chunks()
    return out


def _daily_news_series(
    articles: list[dict], day_index: pd.DatetimeIndex
) -> tuple[pd.Series, pd.Series]:
    """Return (daily_article_count, daily_mean_sentiment) indexed by calendar day."""
    counts = np.zeros(len(day_index), dtype=np.float64)
    sent_sum = np.zeros(len(day_index), dtype=np.float64)
    day_to_i = {d.normalize(): i for i, d in enumerate(day_index)}

    from news_reader import analyze_sentiment

    for it in articles:
        d = _article_day(it)
        if d is None:
            continue
        ts = pd.Timestamp(d).normalize()
        if ts not in day_to_i:
            continue
        i = day_to_i[ts]
        txt = _article_text(it)
        if not txt:
            continue
        try:
            s = float(analyze_sentiment(txt))
        except Exception:
            s = 0.0
        counts[i] += 1.0
        sent_sum[i] += s

    mean_sent = np.zeros_like(counts)
    nz = counts > 0
    mean_sent[nz] = sent_sum[nz] / counts[nz]
    idx = day_index
    c_ser = pd.Series(counts, index=idx)
    # Use NaN where no articles so rolling mean ignores empty days correctly
    m_ser = pd.Series(mean_sent, index=idx)
    m_ser = m_ser.replace(0.0, np.nan)
    m_ser = m_ser.where(c_ser > 0)
    return c_ser, m_ser


def _load_transcript_daily(symbol: str, day_index: pd.DatetimeIndex) -> tuple[pd.Series, pd.Series]:
    """If jsonl lines include ISO date in `ts`, `date`, or `publishedAt`, build daily counts + mean sentiment."""
    p = Path("data/replay/transcripts") / f"{symbol.upper().replace('/', '_')}.jsonl"
    if not p.is_file():
        return (
            pd.Series(0.0, index=day_index),
            pd.Series(np.nan, index=day_index),
        )
    from news_reader import analyze_sentiment

    by_day: dict[str, list[str]] = defaultdict(list)
    with open(p, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                obj = json.loads(ln)
            except Exception:
                continue
            txt = str(obj.get("text", "")).strip()
            if not txt:
                continue
            raw = obj.get("ts") or obj.get("date") or obj.get("publishedAt") or obj.get("published_at")
            if raw is None:
                continue
            try:
                if isinstance(raw, (int, float)):
                    d = datetime.fromtimestamp(int(raw), tz=timezone.utc).date()
                else:
                    d = pd.Timestamp(str(raw)[:10]).date()
            except Exception:
                continue
            by_day[d.isoformat()].append(txt)

    counts = np.zeros(len(day_index), dtype=np.float64)
    sent_sum = np.zeros(len(day_index), dtype=np.float64)
    for i, ts in enumerate(day_index):
        key = ts.date().isoformat()
        texts = by_day.get(key) or []
        if not texts:
            continue
        counts[i] = float(len(texts))
        sent_sum[i] = sum(float(analyze_sentiment(t)) for t in texts)

    mean_sent = np.zeros_like(counts)
    nz = counts > 0
    mean_sent[nz] = sent_sum[nz] / counts[nz]
    c_ser = pd.Series(counts, index=day_index)
    m_ser = pd.Series(mean_sent, index=day_index)
    m_ser = m_ser.replace(0.0, np.nan)
    m_ser = m_ser.where(c_ser > 0)
    return c_ser, m_ser


def enrich_news_history_features(
    df: pd.DataFrame,
    logical_symbol: str,
    start_date: str,
    end_date: str | None,
) -> pd.DataFrame:
    if not _b("USE_TRAIN_NEWS_HISTORY", True):
        out = df.copy()
        for c in ("news_sent_roll_5d", "news_intensity_roll_5d", "news_sent_trend_10d", "transcript_sent_roll_5d"):
            if c not in out.columns:
                out[c] = 0.0
        return out

    out = df.copy()
    if df.empty or "Adj Close" not in out.columns and "Close" not in out.columns:
        for c in ("news_sent_roll_5d", "news_intensity_roll_5d", "news_sent_trend_10d", "transcript_sent_roll_5d"):
            out[c] = 0.0
        return out

    idx = pd.DatetimeIndex(pd.to_datetime(out.index, errors="coerce"))
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    d_min = idx.min().normalize().date()
    d_max = idx.max().normalize().date()
    if end_date:
        try:
            d_max = min(d_max, pd.Timestamp(str(end_date)[:10]).date())
        except Exception:
            pass
    try:
        d0 = max(d_min, pd.Timestamp(str(start_date)[:10]).date())
    except Exception:
        d0 = d_min
    cap = int(os.getenv("TRAIN_NEWS_MAX_CALENDAR_DAYS", "0"))
    if cap > 0:
        d0 = max(d0, d_max - timedelta(days=cap))

    day_index = pd.date_range(pd.Timestamp(d0), pd.Timestamp(d_max), freq="D")

    api_sym = price_feed_symbol(logical_symbol.strip().upper())
    articles = fetch_finnhub_company_news_range(api_sym, d0, d_max)
    if not articles and os.getenv("FINNHUB_API_KEY", "").strip():
        log.debug("[NEWS_HIST] No Finnhub articles for %s in range", api_sym)

    n_day, s_day = _daily_news_series(articles, day_index)
    win = int(os.getenv("TRAIN_NEWS_ROLL_DAYS", "5"))
    roll_n = n_day.rolling(win, min_periods=1).sum()
    # Mean of daily mean sentiments in window (skip NaN days)
    roll_sent = s_day.rolling(win, min_periods=1).mean()
    roll_sent = roll_sent.ffill(limit=int(os.getenv("TRAIN_NEWS_FFILL_LIMIT", "21"))).fillna(0.0)
    intensity = np.tanh(roll_n.astype(float) / max(1.0, float(os.getenv("TRAIN_NEWS_INTENSITY_SCALE", "8.0"))))

    trend = roll_sent - roll_sent.shift(int(os.getenv("TRAIN_NEWS_TREND_LAG", "10"))).fillna(0.0)

    panel = pd.DataFrame(
        {
            "news_sent_roll_5d": roll_sent.reindex(day_index).fillna(0.0),
            "news_intensity_roll_5d": pd.Series(intensity, index=day_index).fillna(0.0),
            "news_sent_trend_10d": trend.reindex(day_index).fillna(0.0),
        },
        index=day_index,
    )

    # --- Optional dated transcripts (replay jsonl) ---
    _tn, ts_ = _load_transcript_daily(logical_symbol.strip().upper(), day_index)
    tw = int(os.getenv("TRAIN_TRANSCRIPT_ROLL_DAYS", "5"))
    tr_sent = ts_.rolling(tw, min_periods=1).mean().ffill(limit=21).fillna(0.0)
    panel["transcript_sent_roll_5d"] = tr_sent

    # Align to equity bar index (normalize to calendar date)
    bar_days = idx.normalize()
    sub = panel.reindex(bar_days)
    sub.index = out.index
    for c in ("news_sent_roll_5d", "news_intensity_roll_5d", "news_sent_trend_10d", "transcript_sent_roll_5d"):
        out[c] = sub[c].astype(np.float64).values

    out.replace([np.inf, -np.inf], 0, inplace=True)
    out.fillna({c: 0.0 for c in ("news_sent_roll_5d", "news_intensity_roll_5d", "news_sent_trend_10d", "transcript_sent_roll_5d")}, inplace=True)
    return out
