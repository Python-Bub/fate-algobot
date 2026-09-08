#!/usr/bin/env python3
"""Watch IPO / new listings: queue symbols for daily model training when they appear."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "data/new_listing_train_queue.json"
WATCHLIST = ROOT / "data/ipo_watchlist.txt"

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
except Exception:
    pass

_NAME_TICKER = re.compile(r"\b([A-Z]{1,5})\b")

# Megacap / liquid names used only as AI-IPO *proxies* — never as "new listings"
# unless they somehow lack a model (handled in ai_ipo_autopilot, not here).
_DEFAULT_PROXY = frozenset(
    {"MSFT", "NVDA", "GOOGL", "GOOG", "AMZN", "META", "AMD", "AVGO", "ORCL", "AAPL", "TSLA"}
)

# Still private as of 2026 — never invent a ticker; watch for real listing via calendars/news.
_PRIVATE_WATCH = frozenset({"OPENAI", "ANTHROPIC", "SPACEX", "ANTH", "XAI"})


def _proxy_tickers() -> set[str]:
    try:
        from tools.ai_ipo_autopilot import proxy_tickers

        return set(proxy_tickers()) | _DEFAULT_PROXY
    except Exception:
        raw = os.getenv("AI_IPO_PROXY_TICKERS", "")
        extra = {s.strip().upper() for s in raw.split(",") if s.strip()}
        return extra | _DEFAULT_PROXY


def _load_watch_names() -> list[str]:
    try:
        from tools.ai_ipo_autopilot import watch_names

        return watch_names()
    except Exception:
        pass
    names: list[str] = []
    if WATCHLIST.is_file():
        for ln in WATCHLIST.read_text(encoding="utf-8", errors="replace").splitlines():
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            names.append(ln.split("#", 1)[0].strip())
    extra = os.getenv("IPO_WATCH_NAMES", "")
    names.extend(n.strip() for n in extra.split(",") if n.strip())
    return list(dict.fromkeys(names))


def _load_queue() -> dict:
    if not QUEUE.is_file():
        return {"symbols": [], "notes": []}
    try:
        return json.loads(QUEUE.read_text(encoding="utf-8"))
    except Exception:
        return {"symbols": [], "notes": []}


def _save_queue(doc: dict) -> None:
    QUEUE.parent.mkdir(parents=True, exist_ok=True)
    doc["updated_at"] = datetime.now(timezone.utc).isoformat()
    tmp = QUEUE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    os.replace(tmp, QUEUE)


def is_queueable_listing_ticker(symbol: str) -> bool:
    """Reject non-tickers, regulators, private brands, and modeled megacap proxies."""
    sys.path.insert(0, str(ROOT))
    from fortress_universe import is_core_trainable_equity, is_tradeable_equity
    from intel.ipo_news_discovery import is_denied_ticker

    s = str(symbol or "").upper().strip()
    if not s or is_denied_ticker(s):
        return False
    if not is_tradeable_equity(s) or not is_core_trainable_equity(s):
        return False
    # Megacap AI proxies are not "new listings"
    if s in _proxy_tickers():
        return False
    return True


def prune_listing_queue(*, drop_modeled: bool = True) -> dict:
    """Remove junk / regulators / proxies / already-trained names from the queue."""
    sys.path.insert(0, str(ROOT))
    from model_trainer import training_saved_model

    doc = _load_queue()
    before = [str(s).upper() for s in doc.get("symbols") or []]
    kept: list[str] = []
    removed: list[str] = []
    for s in before:
        if not is_queueable_listing_ticker(s):
            removed.append(s)
            continue
        if drop_modeled and training_saved_model(s):
            removed.append(s)
            continue
        kept.append(s)
    if removed:
        notes = list(doc.get("notes") or [])
        notes.append(
            f"pruned bogus={removed[:24]} remaining={len(kept)} "
            f"@ {datetime.now(timezone.utc).isoformat()}"
        )
        doc["symbols"] = sorted(set(kept))
        doc["notes"] = notes[-16:]
        _save_queue(doc)
    return {"removed": removed, "kept": kept}


def _discover_ipo_tickers() -> list[str]:
    sys.path.insert(0, str(ROOT))
    from intel.ipo_news_discovery import discover_from_news

    doc = discover_from_news()
    return list(doc.get("tickers") or [])


def _resolve_name_to_ticker(name: str) -> str | None:
    """Best-effort: company name → ticker via yfinance search."""
    # Never resolve private watchlist brands into proxy megacaps
    if name.strip().upper() in _PRIVATE_WATCH:
        return None
    try:
        import yfinance as yf

        q = yf.Search(name, max_results=8)
        quotes = getattr(q, "quotes", None) or []
        for item in quotes:
            if not isinstance(item, dict):
                continue
            sym = str(item.get("symbol", "")).upper()
            if sym and is_queueable_listing_ticker(sym):
                return sym
    except Exception:
        pass
    return None


def probe_private_company_listings(news_doc: dict | None = None) -> list[dict]:
    """Honesty check for private brands (SpaceX / OpenAI / Anthropic / xAI).

    Never map brands to random yfinance Search hits (false positives like SNK/MAJJ).
    Brands stay ``still_private`` until Finnhub/NewsAPI/Nasdaq emit a real distinct
    ticker; ``listing_watch`` then queues via ``is_queueable_listing_ticker``.
    """
    sys.path.insert(0, str(ROOT))
    if news_doc is None:
        from intel.ipo_news_discovery import discover_from_news

        news = discover_from_news()
    else:
        news = news_doc

    out: list[dict] = []
    cal = [str(t).upper() for t in (news.get("tickers") or [])]
    names = [str(n).upper() for n in (news.get("company_names") or [])]
    mention_blob = " ".join(names + cal).upper()

    watched = set(_PRIVATE_WATCH)
    for n in _load_watch_names():
        if n.strip().upper() in _PRIVATE_WATCH:
            watched.add(n.strip().upper())

    brand_phrases = {
        "SPACEX": ("SPACEX", "SPACE X", "SPACE EXPLORATION"),
        "OPENAI": ("OPENAI", "OPEN AI"),
        "ANTHROPIC": ("ANTHROPIC",),
        "ANTH": ("ANTHROPIC",),
        "XAI": ("XAI", "X.AI"),
    }

    for name in sorted(watched):
        phrases = brand_phrases.get(name, (name,))
        mentioned = any(p in mention_blob for p in phrases)
        note = "brand_token_is_not_a_ticker" if name in cal else ""
        out.append(
            {
                "name": name,
                "ticker": None,
                "status": "still_private",
                "mentioned_in_ipo_scan": mentioned,
                "note": note or None,
                "pickup_when_lists": (
                    "Finnhub IPO calendar + NewsAPI + Nasdaq calendar emit the real "
                    "ticker; listing_watch queues it automatically"
                ),
            }
        )
    return out


def collect_new_listing_candidates() -> list[str]:
    """Merge multi-source IPO discovery; exclude proxies & junk."""
    sys.path.insert(0, str(ROOT))
    from intel.ipo_news_discovery import discover_from_news
    from model_trainer import training_saved_model

    out: list[str] = []
    news_doc = discover_from_news()
    for sym in news_doc.get("tickers") or []:
        s = str(sym).upper()
        if is_queueable_listing_ticker(s) and not training_saved_model(s):
            out.append(s)

    for name in news_doc.get("company_names") or []:
        t = _resolve_name_to_ticker(str(name))
        if t and not training_saved_model(t):
            out.append(t)

    for name in _load_watch_names():
        if name.strip().upper() in _PRIVATE_WATCH:
            continue
        if len(name) <= 6 and name.upper().isalnum():
            s = name.upper()
            if is_queueable_listing_ticker(s) and not training_saved_model(s):
                out.append(s)
            continue
        t = _resolve_name_to_ticker(name)
        if t and not training_saved_model(t):
            out.append(t)

    # Observe-only — never enqueue Search false positives for private brands.
    _ = probe_private_company_listings(news_doc)

    return list(dict.fromkeys(out))


def queue_symbols(symbols: list[str]) -> list[str]:
    doc = _load_queue()
    # Always prune junk before adding
    prune_listing_queue(drop_modeled=True)
    doc = _load_queue()
    cur = {str(s).upper() for s in doc.get("symbols", [])}
    added = []
    for s in symbols:
        u = s.upper()
        if not is_queueable_listing_ticker(u):
            continue
        if u not in cur:
            cur.add(u)
            added.append(u)
    if added:
        notes = list(doc.get("notes", []))
        notes.append(f"queued {len(added)} @ {datetime.now(timezone.utc).isoformat()}")
        doc["symbols"] = sorted(cur)
        doc["notes"] = notes[-16:]
        _save_queue(doc)
    return added


def train_queued_if_idle(max_symbols: int | None = None) -> int:
    prune_listing_queue(drop_modeled=True)
    doc = _load_queue()
    pending = [s for s in doc.get("symbols", []) if is_queueable_listing_ticker(str(s))]
    if not pending:
        return 0
    cap = max_symbols or int(os.getenv("IPO_TRAIN_BATCH", "5"))
    batch = pending[:cap]
    sym_file = ROOT / "data/new_listing_batch.json"
    sym_file.write_text(json.dumps(batch), encoding="utf-8")
    py = ROOT / "venv/bin/python"
    env = os.environ.copy()
    env.update(
        {
            "TRAIN_SYMBOLS_FILE": str(sym_file),
            # parallel_train prefers TRAIN_TOP50/100_ONLY over TRAIN_SYMBOLS_FILE —
            # clear those so IPO batches actually train the queued listings.
            "TRAIN_TOP50_ONLY": "false",
            "TRAIN_TOP100_ONLY": "false",
            "TRAIN_TICKER_TIMEOUT_SEC": os.getenv("IPO_TRAIN_TIMEOUT_SEC", "600"),
            "AUTO_RETRAIN_LOW_TOP20": "false",
            "MULTI_HORIZON_TRAIN": "true",
        }
    )
    # --missing-only: do not skip via shared daily checkpoint (IPO names must train)
    rc = subprocess.call(
        [
            str(py),
            "-u",
            "parallel_train.py",
            "--pipeline",
            "daily",
            "--workers",
            "2",
            "--missing-only",
        ],
        cwd=ROOT,
        env=env,
    )
    # Always dequeue the attempted batch so the drain loop progresses.
    # Skipped/no-data names can re-enter via discover later; stuck forever blocks IPO training.
    rest = [s for s in pending if s.upper() not in {b.upper() for b in batch}]
    doc["symbols"] = rest
    notes = list(doc.get("notes", []))
    notes.append(f"trained batch {batch} rc={rc}")
    doc["notes"] = notes[-16:]
    doc["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save_queue(doc)
    return rc


def main() -> int:
    ap = argparse.ArgumentParser(description="IPO / new listing → model training queue")
    ap.add_argument("--train", action="store_true", help="Train up to IPO_TRAIN_BATCH queued symbols")
    ap.add_argument("--list", action="store_true", help="Print queue only")
    ap.add_argument("--prune", action="store_true", help="Prune junk/proxies from queue and exit")
    ap.add_argument(
        "--private-status",
        action="store_true",
        help="Report SpaceX/OpenAI/Anthropic listing probe (honesty check)",
    )
    args = ap.parse_args()
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))

    if args.list:
        doc = _load_queue()
        print(json.dumps(doc, indent=2))
        return 0

    if args.private_status:
        print(json.dumps(probe_private_company_listings(), indent=2))
        return 0

    if args.prune:
        print(json.dumps(prune_listing_queue(), indent=2))
        return 0

    pruned = prune_listing_queue()
    # Train queued IPO names first so NewsAPI/Yahoo discovery hangs cannot block batches.
    rc = 0
    if args.train and _load_queue().get("symbols"):
        rc = train_queued_if_idle()
        if rc == 0 and os.getenv("CLEANER_ON_LISTING", "true").lower() in ("1", "true", "yes"):
            try:
                from tools.change_cleaner import run_builtin_cleaner

                run_builtin_cleaner(reason="listing_watch_train")
            except Exception:
                pass

    skip_discover = os.getenv("IPO_TRAIN_SKIP_DISCOVER", "").lower() in ("1", "true", "yes")
    if skip_discover and args.train:
        print(
            f"[listing-watch] discover skipped (IPO_TRAIN_SKIP_DISCOVER) "
            f"pruned={len(pruned.get('removed') or [])} train_rc={rc}"
        )
        return rc

    found = collect_new_listing_candidates()
    added = queue_symbols(found)
    print(
        f"[listing-watch] discovered={len(found)} newly_queued={len(added)} "
        f"pruned={len(pruned.get('removed') or [])}"
    )
    for s in added[:30]:
        print(f"  + {s}")
    if args.train and added and not _load_queue().get("symbols"):
        # edge: symbols already drained
        pass
    elif args.train and _load_queue().get("symbols") and rc == 0:
        # Second pass if discover filled an empty queue
        rc = train_queued_if_idle()
    return rc if args.train else 0


if __name__ == "__main__":
    raise SystemExit(main())
