"""Power-people signal: presidents, Fed chairs, CEOs with market-moving reach.

Accuracy rules (do not hallucinate a ticker from vibes):
  1. Speaker must be identified in the text.
  2. Ticker must be a cashtag, an unambiguous company name, or a two-cue
     subtext rule (e.g. Elon + Cybertruck → TSLA). Sector words alone never
     pick a winner.
  3. Direction comes from buy/sell verbs or strong phrases ("wanna get rich,
     buy this"). A name-drop with no direction is score 0.
  4. Live weight is shrunk by *historical* 5-day excess return vs SPY for that
     speaker. Until n≥min_n we use a modest prior — not "always right".
"""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from utils import log

ROOT = Path(__file__).resolve().parents[1]
HITS_PATH = ROOT / "data" / "intel" / "power_people_hits.jsonl"
CAL_PATH = ROOT / "data" / "intel" / "power_people_calibration.json"

# Longest names first so "JP Morgan" wins over stray tokens.
COMPANY_NAMES: tuple[tuple[str, str], ...] = (
    ("johnson & johnson", "JNJ"),
    ("johnson and johnson", "JNJ"),
    ("lockheed martin", "LMT"),
    ("goldman sachs", "GS"),
    ("bank of america", "BAC"),
    ("american express", "AXP"),
    ("general motors", "GM"),
    ("general electric", "GE"),
    ("ford motor", "F"),
    ("coca-cola", "KO"),
    ("coca cola", "KO"),
    ("berkshire hathaway", "BRK-B"),
    ("advanced micro devices", "AMD"),
    ("taiwan semiconductor", "TSM"),
    ("eli lilly", "LLY"),
    ("jp morgan", "JPM"),
    ("jpmorgan", "JPM"),
    ("morgan stanley", "MS"),
    ("truth social", "DJT"),
    ("trump media", "DJT"),
    ("home depot", "HD"),
    ("procter & gamble", "PG"),
    ("procter and gamble", "PG"),
    ("unitedhealth", "UNH"),
    ("exxon mobil", "XOM"),
    ("exxonmobil", "XOM"),
    ("alphabet", "GOOGL"),
    ("microsoft", "MSFT"),
    ("berkshire", "BRK-B"),
    ("nvidia", "NVDA"),
    ("netflix", "NFLX"),
    ("amazon", "AMZN"),
    ("google", "GOOGL"),
    ("facebook", "META"),
    ("broadcom", "AVGO"),
    ("palantir", "PLTR"),
    ("tesla", "TSLA"),
    ("apple", "AAPL"),
    ("oracle", "ORCL"),
    ("costco", "COST"),
    ("walmart", "WMT"),
    ("chevron", "CVX"),
    ("exxon", "XOM"),
    ("boeing", "BA"),
    ("disney", "DIS"),
    ("paypal", "PYPL"),
    ("meta", "META"),
    ("tsmc", "TSM"),
)

CASHTAG_RE = re.compile(r"(?<![A-Z])\$([A-Z]{1,5})\b")
STOP_TICKERS = {
    "CEO", "CFO", "IPO", "GDP", "NYSE", "FED", "FOMC", "ETF", "USA", "AI", "EPS",
    "USD", "THE", "AND", "FOR", "ARE", "BUT", "NOT", "YOU", "ALL", "CAN", "BUY",
    "SELL", "HOLD", "CEO", "USA", "US", "UK", "EU", "UN", "TV", "AM", "PM",
}

# speaker_id → (regex, prior_hit_rate used only when n is small)
SPEAKERS: tuple[tuple[str, re.Pattern[str], float], ...] = (
    ("trump", re.compile(r"\b(donald\s+j\.?\s+trump|president\s+trump|donald\s+trump|\btrump\b)\b", re.I), 0.56),
    ("powell", re.compile(r"\b(jerome\s+powell|jay\s+powell|fed(?:eral reserve)?\s+chair(?:man)?\s+powell|\bpowell\b)\b", re.I), 0.54),
    ("yellen", re.compile(r"\b(janet\s+yellen|\byellen\b)\b", re.I), 0.53),
    ("bessent", re.compile(r"\b(scott\s+bessent|\bbessent\b)\b", re.I), 0.54),
    ("lutnick", re.compile(r"\b(howard\s+lutnick|\blutnick\b)\b", re.I), 0.53),
    ("musk", re.compile(r"\b(elon\s+musk|\bmusk\b|\belon\b)\b", re.I), 0.55),
    ("buffett", re.compile(r"\b(warren\s+buffett|\bbuffett\b)\b", re.I), 0.57),
    ("ackman", re.compile(r"\b(bill\s+ackman|\backman\b)\b", re.I), 0.53),
    ("dalio", re.compile(r"\b(ray\s+dalio|\bdalio\b)\b", re.I), 0.52),
    ("biden", re.compile(r"\b(joe\s+biden|president\s+biden|\bbiden\b)\b", re.I), 0.52),
    ("vance", re.compile(r"\b(j\.?\s*d\.?\s+vance|\bjd\s+vance\b)\b", re.I), 0.52),
)

# Two independent cues required (unless the first pattern is marked unique).
# Never map "chips" or "cars" alone to a single name.
TWO_CUE: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("TSLA", (r"\belon\b", r"\bcybertruck\b")),
    ("TSLA", (r"\belon\b", r"\bmodel [3sxy]\b")),
    ("DJT", (r"\btruth social\b",)),
    ("NVDA", (r"\bjensen huang\b", r"\b(gpu|cuda)\b")),
)

BULL_VERBS = re.compile(
    r"\b(buy|buying|bought|own|long|bullish|accumulate|recommend|upgrade|"
    r"take a look at|load up|get in|don't miss|do not miss)\b",
    re.I,
)
BEAR_VERBS = re.compile(
    r"\b(sell|selling|sold|short|bearish|avoid|dump|get out|stay away|"
    r"downgrade|trim|don't buy|do not buy)\b",
    re.I,
)
STRONG_BULL = re.compile(
    r"\b(wanna get rich|want to get rich|want to be rich|get rich|"
    r"buy this|buy now|can't miss|cannot miss|to the moon|going to boom|"
    r"going to soar|massive winner|huge winner|all in|"
    r"take my word|trust me on this|this is the one)\b",
    re.I,
)
STRONG_BEAR = re.compile(
    r"\b(get out now|never own|stay the hell away|dead money|"
    r"going to zero|sell everything)\b",
    re.I,
)

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def _enabled() -> bool:
    return os.getenv("USE_POWER_PEOPLE", "true").lower() in ("1", "true", "yes")


def _hits_path() -> Path:
    raw = os.getenv("POWER_PEOPLE_HITS_FILE", "")
    return Path(raw) if raw.strip() else HITS_PATH


def _cal_path() -> Path:
    raw = os.getenv("POWER_PEOPLE_CAL_FILE", "")
    return Path(raw) if raw.strip() else CAL_PATH


def _parse_ts(raw: Any) -> date | None:
    if raw is None:
        return None
    try:
        if isinstance(raw, datetime):
            return raw.date()
        if isinstance(raw, date):
            return raw
        s = str(raw).strip()
        if not s:
            return None
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        if "T" in s:
            return datetime.fromisoformat(s[:19]).date()
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def detect_speakers(text: str) -> list[str]:
    found: list[str] = []
    for sid, pat, _prior in SPEAKERS:
        if pat.search(text) and sid not in found:
            found.append(sid)
    return found


def _name_tickers(text: str) -> dict[str, str]:
    """Map ticker → matched company phrase (longest names first)."""
    low = f" {text.lower()} "
    hits: dict[str, str] = {}
    for name, sym in COMPANY_NAMES:
        if re.search(rf"(?<![a-z0-9]){re.escape(name.lower())}(?![a-z0-9])", low):
            hits.setdefault(sym, name)
    return hits


def _cashtags(text: str) -> set[str]:
    return {s for s in CASHTAG_RE.findall(text.upper()) if s not in STOP_TICKERS and 1 < len(s) <= 5}


def _two_cue_tickers(text: str) -> dict[str, str]:
    low = text.lower()
    out: dict[str, str] = {}
    for sym, cues in TWO_CUE:
        ok = True
        for cue in cues:
            if not re.search(cue, low, re.I):
                ok = False
                break
        if ok:
            out.setdefault(sym, "two_cue:" + "+".join(cues))
    return out


def _direction(chunk: str) -> tuple[float, bool]:
    bulls = len(BULL_VERBS.findall(chunk))
    bears = len(BEAR_VERBS.findall(chunk))
    sb = bool(STRONG_BULL.search(chunk))
    ss = bool(STRONG_BEAR.search(chunk))
    if sb and not ss:
        return 1.0, True
    if ss and not sb:
        return -1.0, True
    tot = bulls + bears
    if tot == 0:
        return 0.0, False
    return float((bulls - bears) / tot), False


def _chunks_for_ticker(text: str, ticker: str, name: str) -> str:
    bits: list[str] = []
    for sent in _SENT_SPLIT.split(text):
        if not sent.strip():
            continue
        if re.search(rf"\${ticker}\b", sent, re.I) or re.search(rf"\b{re.escape(name)}\b", sent, re.I):
            bits.append(sent)
    return " ".join(bits) if bits else text[:400]


def extract_mentions(text: str, *, speaker_hint: str | None = None, ts: Any = None) -> list[dict[str, Any]]:
    """Return high-precision mentions. Empty if speaker or ticker is ambiguous."""
    blob = str(text or "").strip()
    if not blob:
        return []
    speakers = detect_speakers(blob)
    if speaker_hint:
        h = speaker_hint.strip().lower()
        # Never invent a speaker who is not in the text. Hint only *filters*
        # RSS buckets so a Trump query does not also credit Powell.
        speakers = [s for s in speakers if s == h]
    if not speakers:
        return []
    names = _name_tickers(blob)
    cash = _cashtags(blob)
    cues = _two_cue_tickers(blob)
    tickers: dict[str, str] = {}
    for sym in cash:
        tickers[sym] = "cashtag"
    for sym, how in names.items():
        tickers.setdefault(sym, f"name:{how}")
    for sym, how in cues.items():
        tickers.setdefault(sym, how)
    if not tickers:
        return []
    d = _parse_ts(ts)
    out: list[dict[str, Any]] = []
    for sym, how in tickers.items():
        chunk = _chunks_for_ticker(blob, sym, names.get(sym, sym))
        direction, strong = _direction(chunk)
        if direction == 0.0 and not strong:
            # Name-drop only — do not invent a buy.
            continue
        for spk in speakers:
            out.append(
                {
                    "speaker": spk,
                    "ticker": sym,
                    "direction": direction,
                    "strong": strong,
                    "how": how,
                    "date": d.isoformat() if d else None,
                    "quote": chunk.strip()[:280],
                }
            )
    return out


def load_calibration() -> dict[str, Any]:
    p = _cal_path()
    if not p.is_file():
        return {"speakers": {}}
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {"speakers": {}}
    except Exception:
        return {"speakers": {}}


def speaker_reliability(speaker: str) -> float:
    """Map historical hit-rate to [-1, 1], shrunk until enough samples."""
    sid = str(speaker or "").strip().lower()
    prior = 0.53
    for name, _pat, p in SPEAKERS:
        if name == sid:
            prior = p
            break
    cal = load_calibration().get("speakers") or {}
    row = cal.get(sid) or {}
    n = int(row.get("n") or 0)
    hr = float(row.get("hit_rate_5d") if row.get("hit_rate_5d") is not None else prior)
    min_n = max(1, int(os.getenv("POWER_PEOPLE_MIN_N", "8")))
    shrink = min(1.0, n / float(min_n))
    # Blend prior with empirical until min_n; then empirical only.
    blended = (1.0 - shrink) * prior + shrink * hr
    edge = (blended - 0.5) * 2.0
    # Speakers who lose vs SPY after enough samples get near-zero / negative weight.
    return max(-1.0, min(1.0, edge))


def append_hits(mentions: list[dict[str, Any]], *, source: str = "") -> int:
    if not mentions:
        return 0
    path = _hits_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("a", encoding="utf-8") as f:
        for m in mentions:
            row = dict(m)
            row["source"] = source
            row["logged_at_utc"] = datetime.now(timezone.utc).isoformat()
            f.write(json.dumps(row, default=str) + "\n")
            n += 1
            try:
                from intel.algo_memory import remember

                remember(
                    "power_people",
                    str(m.get("ticker") or ""),
                    f"{m.get('speaker')}: {m.get('quote') or ''}".strip()[:400],
                    source=f"power_people:{m.get('speaker')}",
                    extra={
                        "direction": float(m.get("direction") or 0.0),
                        "strong": bool(m.get("strong")),
                        "speaker": m.get("speaker"),
                    },
                )
            except Exception:
                pass
    return n


def _load_hits(*, max_age_days: int | None = None) -> list[dict[str, Any]]:
    path = _hits_path()
    if not path.is_file():
        return []
    cutoff = None
    if max_age_days is not None:
        cutoff = date.today() - timedelta(days=int(max_age_days))
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-4000:]
    except Exception:
        return []
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            obj = json.loads(ln)
        except Exception:
            continue
        d = _parse_ts(obj.get("date") or obj.get("logged_at_utc"))
        if cutoff is not None and d is not None and d < cutoff:
            continue
        rows.append(obj)
    return rows


def score_symbol_from_power_people(symbol: str) -> dict[str, Any]:
    empty = {
        "final_factor": 0.0,
        "mentions": 0,
        "speakers": [],
        "strong": False,
        "reliability": 0.0,
    }
    if not _enabled():
        return {**empty, "disabled": True}
    sym = str(symbol or "").strip().upper()
    if not sym:
        return empty
    try:
        from universe_lifecycle.corporate_actions import related_symbols

        aliases = {s.upper() for s in related_symbols(sym)} | {sym}
    except Exception:
        aliases = {sym}
    half = float(os.getenv("POWER_PEOPLE_DECAY_HALF_LIFE_DAYS", "12"))
    max_age = int(os.getenv("POWER_PEOPLE_MAX_AGE_DAYS", "21"))
    w_sum = 0.0
    s_sum = 0.0
    n = 0
    speakers: set[str] = set()
    strong = False
    rel_acc = 0.0
    for hit in _load_hits(max_age_days=max_age):
        t = str(hit.get("ticker") or "").upper()
        if t not in aliases:
            continue
        spk = str(hit.get("speaker") or "").lower()
        if not spk:
            continue
        d = _parse_ts(hit.get("date") or hit.get("logged_at_utc"))
        age = max(0.0, (date.today() - d).days) if d else 3.0
        decay = 0.5 ** (age / half) if half > 0 else 1.0
        rel = speaker_reliability(spk)
        direction = float(hit.get("direction") or 0.0)
        if bool(hit.get("strong")):
            direction = 1.0 if direction >= 0 else -1.0
            strong = True
            decay *= float(os.getenv("POWER_PEOPLE_STRONG_MULT", "1.25"))
        w = decay * max(0.05, abs(rel))
        s_sum += w * direction * (1.0 if rel >= 0 else -1.0) * abs(rel)
        w_sum += w
        n += 1
        speakers.add(spk)
        rel_acc += rel
    if n == 0 or w_sum <= 0:
        return empty
    factor = max(-1.0, min(1.0, s_sum / w_sum))
    return {
        "final_factor": factor,
        "mentions": n,
        "speakers": sorted(speakers),
        "strong": strong,
        "reliability": rel_acc / n,
    }


def power_people_boost_for(symbol: str) -> float:
    return float(score_symbol_from_power_people(symbol).get("final_factor") or 0.0)


def _fwd_excess(ticker: str, asof: date, horizon: int = 5) -> float | None:
    """Ticker return minus SPY over the next `horizon` trading days. None if incomplete."""
    try:
        import yfinance as yf
        import pandas as pd
    except Exception:
        return None
    start = asof.isoformat()
    end = (asof + timedelta(days=horizon * 3 + 8)).isoformat()
    try:
        tk = yf.download([ticker, "SPY"], start=start, end=end, auto_adjust=True, progress=False)
        if tk is None or tk.empty:
            return None
        close = tk["Close"] if "Close" in tk else tk
        if isinstance(close, pd.Series):
            return None
        if ticker not in close.columns or "SPY" not in close.columns:
            # yfinance may use the single-ticker layout
            return None
        px_t = close[ticker].dropna()
        px_s = close["SPY"].dropna()
        aligned = pd.concat([px_t, px_s], axis=1, join="inner").dropna()
        aligned.columns = ["t", "s"]
        # First row on/after asof
        aligned = aligned.loc[aligned.index.date >= asof]
        if len(aligned) < horizon + 1:
            return None
        t0, s0 = float(aligned["t"].iloc[0]), float(aligned["s"].iloc[0])
        t1, s1 = float(aligned["t"].iloc[horizon]), float(aligned["s"].iloc[horizon])
        if t0 <= 0 or s0 <= 0:
            return None
        return (t1 / t0 - 1.0) - (s1 / s0 - 1.0)
    except Exception as e:
        log.debug("[POWER] fwd %s %s: %s", ticker, asof, e)
        return None


def calibrate_hits(*, horizon: int = 5, lookback_days: int = 400) -> dict[str, Any]:
    """Score past mentions vs SPY. Speakers who do not beat the market get less weight."""
    cutoff = date.today() - timedelta(days=lookback_days)
    by_spk: dict[str, list[float]] = defaultdict(list)
    scored = 0
    skipped = 0
    for hit in _load_hits():
        spk = str(hit.get("speaker") or "").lower()
        t = str(hit.get("ticker") or "").upper()
        d = _parse_ts(hit.get("date"))
        direction = float(hit.get("direction") or 0.0)
        if not spk or not t or d is None or d < cutoff:
            skipped += 1
            continue
        # Need the horizon to have elapsed
        if (date.today() - d).days < horizon + 1:
            skipped += 1
            continue
        if direction == 0:
            skipped += 1
            continue
        excess = _fwd_excess(t, d, horizon=horizon)
        if excess is None:
            skipped += 1
            continue
        # A bullish call is a hit if excess > 0; a bearish call is a hit if excess < 0.
        signed = excess if direction > 0 else -excess
        by_spk[spk].append(signed)
        scored += 1
    speakers_out: dict[str, Any] = {}
    for spk, xs in by_spk.items():
        n = len(xs)
        hits = sum(1 for x in xs if x > 0)
        speakers_out[spk] = {
            "n": n,
            "hits": hits,
            "hit_rate_5d": round(hits / n, 4) if n else None,
            "avg_exret_5d": round(sum(xs) / n, 6) if n else None,
        }
    doc = {
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "horizon_days": horizon,
        "scored": scored,
        "skipped": skipped,
        "speakers": speakers_out,
    }
    path = _cal_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return doc
