"""Jim Cramer pick extractor + confidence boost.

Reads transcripts from `data/replay/transcripts/CRAMER.jsonl` (one JSON per line; field
`text` required, optional `ts` / `date` for time-weighting). Extracts mentioned tickers
and tags each as bullish / bearish using simple verb + sentiment heuristics.

Provides a per-ticker score in `[-1, 1]` (recent-mention-weighted) for live scoring:

- `score_symbol_from_cramer(symbol)` -> {`final_factor`, `mentions`, `recent_bullish`, ...}
- `cramer_boost_for(symbol)` -> float in `[-1, 1]` already smoothed and clipped.

Two ways to supply Cramer content (no API key required):
1. **YouTube transcripts**: pipe Mad Money episode transcripts (auto-generated captions are fine)
   into `data/replay/transcripts/CRAMER.jsonl` with `{"text": "<full transcript>", "ts": "YYYY-MM-DD"}`.
2. **News headlines**: every news fetch already runs a Cramer query
   (`sentiment_pipeline.fetch_cramer_mentions`) which feeds the same factor engine.

This module is **agnostic to the input source** — it just needs JSONL lines of plain text.
"""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from utils import log

CRAMER_FILE_DEFAULT = "data/replay/transcripts/CRAMER.jsonl"

# Ticker pattern: 1-5 uppercase letters preceded by $ OR mentioned in caps with context.
# We require $TICKER (cashtag) OR an obvious 3-5 letter cap word adjacent to a buy/sell verb.
CASHTAG_RE = re.compile(r"(?<![A-Z])\$([A-Z]{1,5})\b")
BARE_TICKER_RE = re.compile(r"(?<![A-Z])([A-Z]{2,5})(?![A-Z])")

BULL_VERBS = re.compile(
    r"\b(buy|buying|own|owned|long|bullish|accumulate|love|favorite|pick|recommend|upgrade|target raised|breakout|own this|own that|outperform)\b",
    re.I,
)
BEAR_VERBS = re.compile(
    r"\b(sell|selling|short|bearish|avoid|trim|trimming|downgrade|cut target|underperform|sell now|sell sell sell|dump)\b",
    re.I,
)

# Table-pounding / high-conviction phrases. When Cramer goes into "screaming buy" mode
# (Solstice, Marvell, Apple at the lows, etc.), he usually frames it like one of these.
# Matching any one of these inside the sentence(s) that mention the ticker promotes the
# pick to `high_conviction=True` and saturates `final_factor` at +1 / -1 accordingly.
STRONG_BUY_PHRASES = re.compile(
    r"\b(buy buy buy|screaming buy|table[- ]pound(ing|er)?|"
    r"do not miss|don't miss|must own|gotta own|got to own|"
    r"home run|to the moon|massive winner|huge winner|biggest winner|"
    r"this is the one|this stock is a buy|i'm pounding the table|"
    r"will go up a lot|going to soar|going to skyrocket|"
    r"this week|next week|one week|in a week|in seven days|"
    r"double in a (week|month)|guaranteed|100\s*%|"
    r"low risk high reward|best name in)\b",
    re.I,
)
STRONG_SELL_PHRASES = re.compile(
    r"\b(sell sell sell|get out (now|of)|dump it|run for the hills|"
    r"never own|absolutely (avoid|sell)|trim aggressively|"
    r"this is a sell|i am pounding the table on selling)\b",
    re.I,
)

# Discard ultra-common all-caps words that aren't tickers but show up as bare patterns.
STOP_TICKERS = {
    "CEO", "CFO", "COO", "IPO", "GDP", "NYSE", "FED", "FOMC", "ETF", "USA",
    "AI", "EPS", "PE", "ROE", "USD", "EUR", "GBP", "JPY", "USA", "OK",
    "OPEN", "CLOSE", "HIGH", "LOW", "ETFS",
    # Mad Money "boos and buys" segment chants etc.
    "BOO", "BUY", "SELL", "HOLD",
}


def _file_path() -> Path:
    return Path(os.getenv("CRAMER_TRANSCRIPT_FILE", CRAMER_FILE_DEFAULT))


def _parse_ts(raw) -> date | None:
    if raw is None:
        return None
    try:
        if isinstance(raw, (int, float)):
            return datetime.fromtimestamp(int(raw), tz=timezone.utc).date()
        s = str(raw)[:10]
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def _decay_weight(d: date | None, half_life_days: float) -> float:
    if d is None or half_life_days <= 0:
        return 1.0
    age = max(0.0, (date.today() - d).days)
    return 0.5 ** (age / half_life_days)


def _load_entries() -> list[tuple[date | None, str]]:
    p = _file_path()
    if not p.is_file():
        return []
    out: list[tuple[date | None, str]] = []
    with open(p, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                obj = json.loads(ln)
            except Exception:
                continue
            txt = str(obj.get("text") or "").strip()
            if not txt:
                continue
            d = _parse_ts(obj.get("ts") or obj.get("date") or obj.get("publishedAt") or obj.get("published_at"))
            out.append((d, txt))
    return out


def _candidate_tickers(text: str) -> set[str]:
    cash = set(CASHTAG_RE.findall(text))
    bare = set(BARE_TICKER_RE.findall(text))
    syms = (cash | bare) - STOP_TICKERS
    # Drop very short bare-cap words that look like initialisms
    return {s for s in syms if (s in cash) or (len(s) >= 3)}


_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def _sentence_chunks_containing(text: str, sym: str) -> list[str]:
    """Return only sentences that mention sym ($SYM or bare SYM)."""
    sents = _SENT_SPLIT.split(text)
    out: list[str] = []
    pat = re.compile(rf"\${sym}\b|\b{sym}\b")
    for s in sents:
        if pat.search(s):
            out.append(s)
    return out


def _surrounding(text: str, sym: str, window: int = 80) -> str:
    """Prefer sentences containing the symbol; fall back to char windows."""
    sents = _sentence_chunks_containing(text, sym)
    if sents:
        return " | ".join(sents)
    chunks: list[str] = []
    for m in re.finditer(rf"\${sym}\b|\b{sym}\b", text):
        s = max(0, m.start() - window)
        e = min(len(text), m.end() + window)
        chunks.append(text[s:e])
    return " | ".join(chunks)


def _score_chunk(chunk: str) -> tuple[float, bool, bool]:
    """Return `(score, strong_buy, strong_sell)`.

    Score is the normalised bull/bear verb balance; the strong flags are True only
    when an explicit table-pounding phrase appears in the same sentence(s).
    """
    bulls = len(BULL_VERBS.findall(chunk))
    bears = len(BEAR_VERBS.findall(chunk))
    sb = bool(STRONG_BUY_PHRASES.search(chunk))
    ss = bool(STRONG_SELL_PHRASES.search(chunk))
    tot = bulls + bears
    if tot == 0:
        # No verbs but a high-conviction phrase still expresses direction.
        if sb and not ss:
            return 1.0, True, False
        if ss and not sb:
            return -1.0, False, True
        return 0.0, False, False
    base = float((bulls - bears) / tot)
    if sb and not ss:
        base = max(base, 1.0)
    if ss and not sb:
        base = min(base, -1.0)
    return base, sb, ss


def extract_picks(entries: list[tuple[date | None, str]] | None = None) -> dict[str, dict]:
    """Aggregate Cramer text into per-ticker recency-weighted scores + conviction flags."""
    if entries is None:
        entries = _load_entries()
    half_life = float(os.getenv("CRAMER_DECAY_HALF_LIFE_DAYS", "10"))
    accum: dict[str, dict] = defaultdict(
        lambda: {
            "weight": 0.0,
            "score_w": 0.0,
            "mentions": 0,
            "bull": 0,
            "bear": 0,
            "strong_buy": 0,
            "strong_sell": 0,
            "last_date": None,
            "last_strong_date": None,
        }
    )
    for d, txt in entries:
        w = _decay_weight(d, half_life)
        for sym in _candidate_tickers(txt):
            ctx = _surrounding(txt, sym)
            s, sb, ss = _score_chunk(ctx)
            row = accum[sym]
            row["mentions"] += 1
            if s > 0:
                row["bull"] += 1
            elif s < 0:
                row["bear"] += 1
            if sb:
                row["strong_buy"] += 1
                if d is not None and (row["last_strong_date"] is None or d > row["last_strong_date"]):
                    row["last_strong_date"] = d
            if ss:
                row["strong_sell"] += 1
            row["weight"] += w
            row["score_w"] += w * s
            if d is not None and (row["last_date"] is None or d > row["last_date"]):
                row["last_date"] = d

    out: dict[str, dict] = {}
    for sym, r in accum.items():
        w = float(r["weight"]) or 1e-9
        score = float(r["score_w"]) / w
        out[sym] = {
            "score": max(-1.0, min(1.0, score)),
            "mentions": int(r["mentions"]),
            "bullish_mentions": int(r["bull"]),
            "bearish_mentions": int(r["bear"]),
            "strong_buy_mentions": int(r["strong_buy"]),
            "strong_sell_mentions": int(r["strong_sell"]),
            "high_conviction_buy": bool(_within_recent_window(r["last_strong_date"]))
            and int(r["strong_buy"]) > int(r["strong_sell"]),
            "weight_total": float(r["weight"]),
            "last_date": r["last_date"].isoformat() if r["last_date"] else None,
            "last_strong_date": r["last_strong_date"].isoformat() if r["last_strong_date"] else None,
        }
    return out


def _within_recent_window(d: date | None) -> bool:
    if d is None:
        return False
    max_age = int(os.getenv("CRAMER_STRONG_MAX_AGE_DAYS", "14"))
    return (date.today() - d).days <= max_age


def score_symbol_from_cramer(symbol: str) -> dict:
    if os.getenv("USE_CRAMER_SIGNAL", "true").lower() not in ("1", "true", "yes"):
        return {
            "final_factor": 0.0,
            "mentions": 0,
            "bullish_mentions": 0,
            "bearish_mentions": 0,
            "high_conviction_buy": False,
        }
    sym = symbol.strip().upper()
    picks = extract_picks()
    info = picks.get(sym, {})
    if not info:
        return {
            "final_factor": 0.0,
            "mentions": 0,
            "bullish_mentions": 0,
            "bearish_mentions": 0,
            "high_conviction_buy": False,
        }
    return {
        "final_factor": float(info.get("score", 0.0)),
        "mentions": int(info.get("mentions", 0)),
        "bullish_mentions": int(info.get("bullish_mentions", 0)),
        "bearish_mentions": int(info.get("bearish_mentions", 0)),
        "strong_buy_mentions": int(info.get("strong_buy_mentions", 0)),
        "strong_sell_mentions": int(info.get("strong_sell_mentions", 0)),
        "high_conviction_buy": bool(info.get("high_conviction_buy", False)),
        "last_date": info.get("last_date"),
        "last_strong_date": info.get("last_strong_date"),
        "weight_total": float(info.get("weight_total", 0.0)),
    }


def cramer_boost_for(symbol: str) -> float:
    """Bounded boost in `[-1, 1]`; signal/math only — never letter/name favoritism.

    Layers (strongest wins blend):
      1. Hot picks / push-downs (operator or distilled Mad Money) — high gain
      2. Transcript extract + post-market Mad Money
      3. Investor succession alternates when primary feed is stale
    """
    info = score_symbol_from_cramer(symbol)
    gain = float(os.getenv("CRAMER_BOOST_GAIN", "0.6"))
    base = float(info.get("final_factor", 0.0) * gain)
    try:
        from intel.cramer_post_market import post_market_boost_for

        pm = float(post_market_boost_for(symbol))
    except Exception:
        pm = 0.0
    try:
        from intel.cramer_hot_picks import hot_boost_for

        hot = float(hot_boost_for(symbol))
    except Exception:
        hot = 0.0
    try:
        from intel.investor_succession import succession_boost_for

        alt = float(succession_boost_for(symbol))
    except Exception:
        alt = 0.0

    # Prefer the stronger directional signal; hot picks dominate when present.
    if abs(hot) >= 0.05:
        out = 0.70 * hot + 0.20 * (0.75 * base + 0.25 * pm) + 0.10 * alt
    elif abs(pm) >= abs(base):
        out = 0.55 * pm + 0.35 * base + 0.10 * alt
    else:
        out = 0.70 * base + 0.20 * pm + 0.10 * alt
    return max(-1.0, min(1.0, out))


# Imported lazily-friendly shim only kept for backward compat if pandas is wanted later.
pd = None  # type: ignore[assignment]


def ingest_text_lines(lines: list[str], ts: str | None = None, append: bool = True) -> int:
    """Helper to add raw transcript chunks to the Cramer file (one JSON per line)."""
    if not lines:
        return 0
    p = _file_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    n = 0
    with open(p, mode, encoding="utf-8") as f:
        for ln in lines:
            ln = (ln or "").strip()
            if not ln:
                continue
            obj = {"text": ln}
            if ts:
                obj["ts"] = ts
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
            n += 1
    log.info("[CRAMER] Ingested %d lines into %s", n, p)
    return n
