"""Jim Cramer Investing Club — Top 10 Morning Thoughts email → structured AI intel.

Ingest paths (any one):
  1. Drop `.txt` / `.eml` in `data/inbox/morning_club/`
  2. `./run_all.sh ingest-morning-club --file path` or `--stdin`
  3. IMAP auto-fetch when `CLUB_EMAIL_IMAP_*` env vars are set

Parsed intel is written to `data/intel/morning_club_latest.json` and appended to
`data/replay/transcripts/CRAMER.jsonl` so existing `cramer_boost_for()` keeps working.
"""

from __future__ import annotations

import email
import imaplib
import json
import os
import re
from datetime import date, datetime, timezone
from email.header import decode_header
from pathlib import Path

from utils import log

ROOT = Path(__file__).resolve().parents[1]
LATEST_PATH = ROOT / "data" / "intel" / "morning_club_latest.json"
INBOX_DIR = ROOT / "data" / "inbox" / "morning_club"
ARCHIVE_DIR = INBOX_DIR / "processed"

# Common name → ticker (email prose often omits cashtags).
NAME_TO_TICKER = {
    "ALPHABET": "GOOGL",
    "GOOGLE": "GOOGL",
    "AMAZON": "AMZN",
    "APPLE": "AAPL",
    "MICRON": "MU",
    "ORACLE": "ORCL",
    "JOHNSON & JOHNSON": "JNJ",
    "JOHNSON AND JOHNSON": "JNJ",
    "ELI LILLY": "LLY",
    "NUVALENT": "NUVL",
    "WELLTOWER": "WELL",
    "LOWE'S": "LOW",
    "LOWES": "LOW",
    "INTUITIVE SURGICAL": "ISRG",
    "S&P GLOBAL": "SPGI",
    "SP GLOBAL": "SPGI",
    "SPACEX": "SPACE",  # not listed — filtered at trade time
    "OPENAI": "OPENAI",
    "ANTHROPIC": "ANTH",
}

CASHTAG_RE = re.compile(r"\$([A-Z]{1,5})\b")
BARE_TICKER_RE = re.compile(r"\b([A-Z]{2,5})\b")
STOP = {
    "CEO", "CFO", "IPO", "GDP", "NYSE", "FED", "ETF", "USA", "AI", "EPS", "USD",
    "THE", "AND", "FOR", "ARE", "BUT", "NOT", "YOU", "ALL", "CAN", "HAD", "HER",
    "WAS", "ONE", "OUR", "OUT", "DAY", "GET", "HAS", "HIM", "HIS", "HOW", "ITS",
    "MAY", "NEW", "NOW", "OLD", "SEE", "WAY", "WHO", "BOY", "DID", "LET", "PUT",
    "SAY", "SHE", "TOO", "USE", "CLUB", "CNBC", "TOP", "ET", "AM", "PM", "UK", "US",
}


def _enabled() -> bool:
    return os.getenv("USE_MORNING_CLUB_INTEL", "true").lower() in ("1", "true", "yes")


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return json.loads(text)
    i, j = text.find("{"), text.rfind("}")
    if i >= 0 and j > i:
        return json.loads(text[i : j + 1])
    return {}


def _clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _candidate_tickers(text: str) -> set[str]:
    cash = set(CASHTAG_RE.findall(text))
    bare = {t for t in BARE_TICKER_RE.findall(text) if t not in STOP and len(t) >= 2}
    upper = text.upper()
    for name, sym in NAME_TO_TICKER.items():
        if name in upper:
            bare.add(sym)
    return (cash | bare) - STOP


BULL_PHRASES = re.compile(
    r"\b(higher open|recover|rally|buy rating|boosted|positive on|outperform|staying the course|"
    r"well ahead|kept their .+ buy|hiked its price target|price target on|"
    r"reports earnings tomorrow|earnings tomorrow night|tomorrow night)\b",
    re.I,
)
BEAR_PHRASES = re.compile(
    r"\b(selloff|under pressure|dilution|worried|fear|sold \$|massive selloff|"
    r"influx of shares|offset ai spending|gave up gains|turned negative|"
    r"high-grade bonds)\b",
    re.I,
)
CLUB_OWN_RE = re.compile(
    r"\b(?:club,? we own|for the club,? we own|club holding|club stock)\b([^.\n]{0,120})",
    re.I,
)
SKIP_SYMS = frozenset({"SPACE", "OPENAI", "ANTH", "GPT", "TD", "UBS", "GSK", "OK", "IPO", "AI"})


def _context_for_symbol(item: str, sym: str) -> str:
    """Score only sentences naming this company — avoids cross-ticker bleed (AMZN vs ORCL)."""
    names = {sym}
    for name, mapped in NAME_TO_TICKER.items():
        if mapped == sym:
            names.add(name)
    sents = re.split(r"(?<=[.!?])\s+|\n+", item)
    chunks: list[str] = []
    for i, sent in enumerate(sents):
        hit = any(re.search(rf"\b{re.escape(name)}\b", sent, re.I) for name in names)
        if not hit:
            continue
        chunks.append(sent.strip())
        if i + 1 < len(sents) and re.search(
            r"\b(the tech company|the company)\b", sents[i + 1], re.I
        ):
            chunks.append(sents[i + 1].strip())
    if sym == "AAPL" and re.search(r"\bapple\b", item, re.I) and re.search(r"\bclub stock\b", item, re.I):
        chunks = [item]
        if re.search(r"\bstaying the course\b", item, re.I):
            return item
    if not chunks:
        from intel.cramer_picks import _sentence_chunks_containing

        chunks = _sentence_chunks_containing(item, sym)
    return " | ".join(chunks[:3])


def _score_chunk(chunk: str) -> tuple[float, str, bool]:
    bulls = len(BULL_PHRASES.findall(chunk))
    bears = len(BEAR_PHRASES.findall(chunk))
    tot = bulls + bears
    if tot == 0:
        return 0.0, "low", False
    sent = _clip((bulls - bears) / tot, -1, 1)
    conv = "high" if tot >= 2 and abs(sent) >= 0.5 else ("medium" if tot >= 1 else "low")
    block = bears >= 2 and bulls == 0
    return sent, conv, block


def _items_from_email(text: str) -> list[str]:
    parts = re.split(r"\n\s*(?=\d+\.\s)", text.strip())
    if len(parts) <= 1:
        parts = re.split(r"(?<=\.)\s+(?=[A-Z])", text.strip())
    return [p.strip() for p in parts if len(p.strip()) > 40]


def _club_owns_from_text(text: str) -> list[str]:
    owns: list[str] = []
    for m in re.finditer(r"\bwe own\b([^.\n]{0,160})", text, re.I):
        frag = m.group(1)
        upper = frag.upper()
        for name, sym in NAME_TO_TICKER.items():
            if name in upper:
                owns.append(sym)
        for sym in CASHTAG_RE.findall(frag):
            owns.append(sym.upper())
    for m in re.finditer(r"\bclub stock\b", text, re.I):
        # e.g. "price target on the Club stock" → Apple in same numbered item
        start = max(0, m.start() - 200)
        ctx = text[start : m.end() + 40].upper()
        for name, sym in NAME_TO_TICKER.items():
            if name in ctx:
                owns.append(sym)
    return list(dict.fromkeys(owns))


def _heuristic_parse(text: str) -> dict:
    """Rule-based parser when LLM unavailable (429 / offline)."""
    from intel.cramer_picks import extract_picks

    tickers: dict[str, dict] = {}
    for item in _items_from_email(text) or [text]:
        for sym in _candidate_tickers(item):
            if sym in SKIP_SYMS:
                continue
            ctx = _context_for_symbol(item, sym)
            if not ctx:
                continue
            sent, conv, block = _score_chunk(ctx)
            imminent = bool(
                re.search(r"earnings tomorrow|tomorrow night|reports earnings tomorrow", ctx, re.I)
            )
            if imminent:
                sent = max(sent, 0.72)
                conv = "high"
            elif re.search(r"\bbuy rating\b|well ahead of guidance|positive on both", ctx, re.I):
                sent = max(sent, 0.55)
                conv = "high" if sent >= 0.6 else conv
            prev = tickers.get(sym)
            if prev and abs(float(prev["sentiment"])) >= abs(sent):
                continue
            tickers[sym] = {
                "sentiment": sent,
                "action_bias": sent,
                "conviction": conv,
                "club_held": False,
                "thesis": ctx[:200].replace("\n", " "),
                "block_long": block,
                "catalyst": "earnings" if imminent else "",
            }

    for sym, info in extract_picks([(date.today(), text)]).items():
        if sym in SKIP_SYMS:
            continue
        cs = float(info.get("score", 0.0))
        if sym not in tickers or abs(cs) > abs(float(tickers[sym]["sentiment"])):
            tickers[sym] = {
                "sentiment": cs,
                "action_bias": cs,
                "conviction": "high" if info.get("high_conviction_buy") else "medium",
                "club_held": False,
                "thesis": tickers.get(sym, {}).get("thesis", ""),
                "block_long": cs < -0.35,
            }

    club_owns = _club_owns_from_text(text)
    for item in _items_from_email(text) or [text]:
        owns_here = [s for s in club_owns if s in _candidate_tickers(item)]
        if not owns_here:
            continue
        item_sent, item_conv, _ = _score_chunk(item)
        if re.search(r"\bpositive on\b|\bwe own\b", item, re.I):
            item_sent = max(item_sent, 0.55)
            item_conv = "high"
        for sym in owns_here:
            row = tickers.setdefault(
                sym,
                {
                    "sentiment": 0.35,
                    "action_bias": 0.3,
                    "conviction": "medium",
                    "club_held": True,
                    "thesis": "Club holding",
                    "block_long": False,
                },
            )
            row["club_held"] = True
            if item_sent >= float(row.get("sentiment", 0)):
                row["sentiment"] = item_sent
                row["action_bias"] = item_sent
                row["conviction"] = item_conv
                row["thesis"] = item[:200].replace("\n", " ")

    for sym in club_owns:
        row = tickers.get(sym)
        if not row:
            tickers[sym] = {
                "sentiment": 0.35,
                "action_bias": 0.3,
                "conviction": "medium",
                "club_held": True,
                "thesis": "Club holding",
                "block_long": False,
            }
        else:
            row["club_held"] = True

    macro_bull = len(BULL_PHRASES.findall(text))
    macro_bear = len(BEAR_PHRASES.findall(text))
    tone = "mixed"
    if macro_bull > macro_bear + 1:
        tone = "risk_on"
    elif macro_bear > macro_bull + 1:
        tone = "risk_off"
    risks: list[str] = []
    if re.search(r"spacex|ipo", text, re.I):
        risks.append("SpaceX IPO supply")
    if re.search(r"dilution|sell \$\d+ billion in stock", text, re.I):
        risks.append("Megacap dilution / equity supply")

    return {
        "market_tone": tone,
        "market_sentiment": _clip((macro_bull - macro_bear) / max(1, macro_bull + macro_bear), -1, 1),
        "macro_themes": ["AI capex", "IPO wave"] if re.search(r"\bAI\b|IPO", text) else [],
        "macro_risks": risks[:6],
        "club_owns": club_owns,
        "tickers": tickers,
        "parser": "heuristic",
    }


def _llm_parse(text: str) -> dict | None:
    if os.getenv("USE_LLM_SIGNAL", "false").lower() not in ("1", "true", "yes"):
        return None
    key = (os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        return None
    try:
        from intel.api_budget import allow_provider

        ok, _ = allow_provider("llm", context="morning")
        if not ok:
            return None
    except Exception:
        pass

    from intel.llm_signal_agent import _post_chat

    system = (
        "You parse Jim Cramer CNBC Investing Club 'Top 10 Morning Thoughts' emails for a US equity trading bot. "
        "Return strict JSON with keys:\n"
        "market_tone (risk_on|risk_off|mixed),\n"
        "market_sentiment (-1..1),\n"
        "macro_themes (array of short strings),\n"
        "macro_risks (array: IPO supply, dilution, rates, etc.),\n"
        "club_owns (array of US ticker symbols Jim says the Club owns),\n"
        "tickers (object: TICKER -> {sentiment -1..1, action_bias -1..1, conviction low|medium|high, "
        "club_held bool, block_long bool, thesis string}).\n"
        "Map company names to tickers (Alphabet->GOOGL, Amazon->AMZN, Micron->MU, Apple->AAPL, "
        "Johnson & Johnson->JNJ, Eli Lilly->LLY). Skip private names (SpaceX, OpenAI, Anthropic) unless "
        "there is a clear listed sympathy trade. Separate bullish catalysts from dilution/IPO supply risks."
    )
    user = f"Morning email text:\n{text[:12000]}"
    try:
        raw = _post_chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}]
        )
        obj = _extract_json(raw)
        if not obj:
            return None
        tickers_in = obj.get("tickers") or {}
        tickers: dict[str, dict] = {}
        if isinstance(tickers_in, dict):
            for k, v in tickers_in.items():
                sym = str(k).strip().upper()
                if not sym or sym in STOP or len(sym) > 5:
                    continue
                if not isinstance(v, dict):
                    continue
                tickers[sym] = {
                    "sentiment": _clip(float(v.get("sentiment", 0.0)), -1, 1),
                    "action_bias": _clip(float(v.get("action_bias", v.get("sentiment", 0.0))), -1, 1),
                    "conviction": str(v.get("conviction") or "medium").lower(),
                    "club_held": bool(v.get("club_held", False)),
                    "thesis": str(v.get("thesis") or "")[:240],
                    "block_long": bool(v.get("block_long", False)),
                }
        owns = [str(x).strip().upper() for x in (obj.get("club_owns") or []) if str(x).strip()]
        for sym in owns:
            if sym in tickers:
                tickers[sym]["club_held"] = True
            else:
                tickers[sym] = {
                    "sentiment": 0.35,
                    "action_bias": 0.25,
                    "conviction": "medium",
                    "club_held": True,
                    "thesis": "Club holding per morning email",
                    "block_long": False,
                }
        tone = str(obj.get("market_tone") or "mixed").lower()
        if tone not in ("risk_on", "risk_off", "mixed"):
            tone = "mixed"
        return {
            "market_tone": tone,
            "market_sentiment": _clip(float(obj.get("market_sentiment", 0.0)), -1, 1),
            "macro_themes": [str(x)[:120] for x in (obj.get("macro_themes") or [])[:8]],
            "macro_risks": [str(x)[:120] for x in (obj.get("macro_risks") or [])[:8]],
            "club_owns": owns,
            "tickers": tickers,
            "parser": "llm",
        }
    except Exception as e:
        log.debug("[MORNING_CLUB] LLM parse failed: %s", e)
        return None


def parse_morning_email(text: str) -> dict:
    body = (text or "").strip()
    if not body:
        return {}
    heuristic = _heuristic_parse(body)
    ai_doc = None
    try:
        from intel.cramer_ai_analyzer import analyze_cramer_top10, merge_ai_and_heuristic

        ai_doc = analyze_cramer_top10(body)
    except Exception as e:
        log.debug("[MORNING_CLUB] Cramer AI analyzer failed: %s", e)
    if ai_doc and ai_doc.get("tickers"):
        parsed = merge_ai_and_heuristic(ai_doc, heuristic)
    else:
        parsed = _llm_parse(body) or heuristic
    # Ensure any cashtag in raw text is represented.
    for sym in _candidate_tickers(body):
        if sym in SKIP_SYMS:
            continue
        if sym not in parsed.get("tickers", {}):
            parsed.setdefault("tickers", {})[sym] = {
                "sentiment": 0.0,
                "action_bias": 0.0,
                "conviction": "low",
                "club_held": False,
                "thesis": "mentioned in email",
                "block_long": False,
            }
    return parsed


def ingest_morning_email(text: str, *, source: str = "manual") -> dict:
    """Parse, persist, and feed Cramer transcript replay."""
    parsed = parse_morning_email(text)
    if not parsed:
        return {}
    doc = {
        "source": source,
        "ingested_at_utc": datetime.now(timezone.utc).isoformat(),
        "date": date.today().isoformat(),
        "raw_chars": len(text),
        **parsed,
    }
    LATEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    LATEST_PATH.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    try:
        from intel.cramer_picks import ingest_text_lines

        ingest_text_lines([text[:50000]], ts=date.today().isoformat(), append=True)
    except Exception as e:
        log.debug("[MORNING_CLUB] cramer ingest: %s", e)
    log.info(
        "[MORNING_CLUB] ingested %s — tone=%s tickers=%d parser=%s",
        source,
        doc.get("market_tone"),
        len(doc.get("tickers") or {}),
        doc.get("parser"),
    )
    return doc


def load_latest() -> dict:
    if not LATEST_PATH.is_file():
        return {}
    try:
        return json.loads(LATEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _stale() -> bool:
    doc = load_latest()
    if not doc:
        return True
    max_age = int(os.getenv("MORNING_CLUB_MAX_AGE_HOURS", "36"))
    try:
        ts = datetime.fromisoformat(str(doc.get("ingested_at_utc", "")).replace("Z", "+00:00"))
        age_h = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
        return age_h > max_age
    except Exception:
        return True


def _email_boost(symbol: str) -> float:
    if not _enabled() or _stale():
        return 0.0
    sym = symbol.strip().upper()
    doc = load_latest()
    info = (doc.get("tickers") or {}).get(sym)
    if not info:
        return 0.0
    # Prefer AI action bias when present (from cramer_ai_analyzer merge).
    if info.get("ai_action_bias") is not None:
        sent = float(info.get("ai_action_bias", 0.0))
        ai_w = float(os.getenv("CRAMER_AI_ACTION_WEIGHT", "0.65"))
        sent = ai_w * sent + (1 - ai_w) * float(info.get("action_bias", info.get("sentiment", 0.0)))
    else:
        sent = float(info.get("action_bias", info.get("sentiment", 0.0)))
    conv = str(info.get("conviction") or "medium").lower()
    mult = {"high": 1.25, "medium": 1.0, "low": 0.55}.get(conv, 1.0)
    if info.get("club_held"):
        mult *= float(os.getenv("MORNING_CLUB_OWNED_MULT", "1.15"))
    if info.get("catalyst") == "earnings":
        mult *= float(os.getenv("MORNING_CLUB_EARNINGS_MULT", "1.2"))
    ai_conf = float(info.get("ai_confidence") or doc.get("ai_confidence") or 0.0)
    if ai_conf >= float(os.getenv("MORNING_CLUB_AI_CONFIDENCE_MIN", "0.45")):
        mult *= 1.0 + 0.25 * (ai_conf - 0.45)
    if sym in (doc.get("top_buys") or []):
        mult *= float(os.getenv("CRAMER_AI_TOP_BUY_MULT", "1.18"))
    if sym in (doc.get("top_avoids") or []):
        sent = min(sent, -0.2)
    gain = float(os.getenv("MORNING_CLUB_BOOST_GAIN", "0.75"))
    return _clip(sent * mult * gain, -1.0, 1.0)


def _earnings_calendar_boost(symbol: str) -> float:
    """Pre-earnings / earnings-day tilt — only when email flagged or calendar ≤1d."""
    if os.getenv("USE_EARNINGS_CATALYST_BOOST", "true").lower() not in ("1", "true", "yes"):
        return 0.0
    sym = symbol.strip().upper()
    email_flag = (load_latest().get("tickers") or {}).get(sym, {}).get("catalyst") == "earnings"
    try:
        from intel.earnings_calendar import earnings_snapshot

        snap = earnings_snapshot(sym)
        dte = snap.get("days_to_earnings")
        if dte is None:
            return 0.0
        dte = int(dte)
        if dte == 0 and email_flag:
            return float(os.getenv("EARNINGS_DAY_BOOST", "0.35"))
        if dte == 1 and email_flag:
            return float(os.getenv("EARNINGS_EVE_BOOST", "0.28"))
    except Exception:
        pass
    return 0.0


def _split_csv(raw: str) -> list[str]:
    return [t.strip().upper() for t in (raw or "").split(",") if t.strip()]


def morning_club_boost_for(symbol: str) -> float:
    """Email + proven picks + earnings calendar — bounded [-1, 1]."""
    sym = symbol.strip().upper()
    total = _email_boost(sym)
    try:
        from intel.club_proven_picks import proven_pick_boost

        total += proven_pick_boost(sym)
    except Exception:
        pass
    total += _earnings_calendar_boost(sym)
    return _clip(total, -1.0, 1.0)


def morning_club_block_long(symbol: str) -> bool:
    if not _enabled() or _stale():
        return False
    sym = symbol.strip().upper()
    doc = load_latest()
    if sym in (doc.get("top_avoids") or []):
        return True
    info = (doc.get("tickers") or {}).get(sym) or {}
    if info.get("block_long"):
        return True
    if info.get("horizon") == "avoid":
        return True
    bad = float(info.get("bad_news_score", 0.0))
    good = float(info.get("good_news_score", 0.0))
    if bad >= 0.62 and bad > good + 0.2:
        return True
    return float(info.get("sentiment", 0.0)) <= -0.55


def cramer_day_trade_bias() -> float:
    """Overall intraday tilt from AI (-1..1)."""
    doc = load_latest()
    if _stale():
        return 0.0
    return _clip(float(doc.get("day_trade_bias", doc.get("market_sentiment", 0.0))), -1, 1)


def market_tone() -> str:
    return str(load_latest().get("market_tone") or "mixed")


def _decode_part(payload: bytes, charset: str | None) -> str:
    for enc in (charset, "utf-8", "latin-1"):
        if not enc:
            continue
        try:
            return payload.decode(enc, errors="replace")
        except Exception:
            continue
    return payload.decode("utf-8", errors="replace")


def _email_body(msg: email.message.Message) -> str:
    parts: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype not in ("text/plain", "text/html"):
                continue
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            parts.append(_decode_part(payload, part.get_content_charset()))
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            parts.append(_decode_part(payload, msg.get_content_charset()))
    text = "\n".join(parts)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def fetch_imap_latest() -> str | None:
    """Fetch newest matching Club email via IMAP (optional)."""
    host = os.getenv("CLUB_EMAIL_IMAP_HOST", "").strip()
    user = os.getenv("CLUB_EMAIL_USER", "").strip()
    password = os.getenv("CLUB_EMAIL_PASSWORD", "").strip()
    if not (host and user and password):
        return None
    folder = os.getenv("CLUB_EMAIL_FOLDER", "INBOX")
    sender_filter = os.getenv(
        "CLUB_EMAIL_FROM_FILTER",
        "investing club|cramer|morning thoughts|homestretch|mad money|trade alert",
    )
    subject_filter = os.getenv("CLUB_EMAIL_SUBJECT_FILTER", "morning thoughts|top 10")
    try:
        timeout = int(float(os.getenv("CLUB_EMAIL_IMAP_TIMEOUT_SEC", "12")))
        mail = imaplib.IMAP4_SSL(host, timeout=timeout)
        mail.login(user, password)
        mail.select(folder)
        _, data = mail.search(None, "ALL")
        ids = data[0].split()
        for mid in reversed(ids[-40:]):
            _, msg_data = mail.fetch(mid, "(RFC822)")
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)
            subj = ""
            for part in decode_header(msg.get("Subject", "")):
                subj += part[0].decode(part[1] or "utf-8") if isinstance(part[0], bytes) else str(part[0])
            frm = str(msg.get("From", ""))
            if sender_filter and not re.search(sender_filter, frm, re.I):
                continue
            if subject_filter and not re.search(subject_filter, subj, re.I):
                continue
            body = _email_body(msg)
            mail.logout()
            return body if len(body) > 200 else None
        mail.logout()
    except Exception as e:
        log.warning("[MORNING_CLUB] IMAP fetch failed: %s", e)
    return None


def ingest_inbox_folder() -> dict | None:
    """Ingest newest unprocessed file from data/inbox/morning_club/."""
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(
        [p for p in INBOX_DIR.iterdir() if p.is_file() and p.suffix.lower() in (".txt", ".eml", ".html")],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not files:
        return None
    path = files[0]
    raw = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() == ".eml":
        try:
            msg = email.message_from_string(raw)
            raw = _email_body(msg) or raw
        except Exception:
            pass
    doc = ingest_morning_email(raw, source=f"inbox:{path.name}")
    try:
        path.rename(ARCHIVE_DIR / f"{date.today().isoformat()}_{path.name}")
    except Exception:
        pass
    return doc


def auto_ingest() -> dict | None:
    """Online Cramer fetch → IMAP → inbox drop; then refresh dynamic conviction picks."""
    if not _enabled():
        return None
    try:
        from intel.cramer_email_fetcher import sync_daily_cramer_intel

        sync_daily_cramer_intel()
    except Exception as e:
        log.debug("[MORNING_CLUB] online fetch: %s", e)
    if _stale():
        body = fetch_imap_latest()
        if body:
            ingest_morning_email(body, source="imap")
        else:
            ingest_inbox_folder()
    try:
        # Fast path on unpause/bootstrap — never block the trading stack
        if os.getenv("CONVICTION_FAST", "true").lower() in ("1", "true", "yes"):
            os.environ.setdefault("CONVICTION_GATE_CANDIDATES", "24")
            os.environ.setdefault("CONVICTION_MAX_PICKS", "12")
        from intel.club_conviction_engine import refresh_dynamic_conviction

        refresh_dynamic_conviction()
    except Exception as e:
        log.debug("[MORNING_CLUB] conviction refresh: %s", e)
    doc = load_latest()
    return doc if doc else None
