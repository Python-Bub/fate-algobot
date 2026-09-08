#!/usr/bin/env python3
"""06:00 ET morning prefetch — warm news/price caches before RTH (minimal API spend)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def _watchlist() -> list[str]:
    syms: list[str] = []
    playbook = ROOT / os.getenv("MONDAY_PLAYBOOK_PATH", "data/monday_playbook.json")
    if playbook.is_file():
        try:
            doc = json.loads(playbook.read_text(encoding="utf-8"))
            for p in doc.get("preorders") or []:
                t = str(p.get("ticker") or "").upper()
                if t:
                    syms.append(t)
        except Exception:
            pass
    try:
        from fortress_universe import load_top100_symbols

        syms.extend(load_top100_symbols()[:30])
    except Exception:
        pass
    out: list[str] = []
    seen: set[str] = set()
    for s in syms:
        u = s.strip().upper()
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    max_n = int(os.getenv("MORNING_PREFETCH_MAX_SYMBOLS", "24"))
    return out[:max_n]


def run_prefetch() -> dict:
    from analytics.market_session import intel_window_open, now_et
    from intel.api_coverage import coverage_report, match_symbols_in_texts

    ok, reason = intel_window_open()
    if not ok:
        return {"skipped": True, "reason": reason}

    symbols = _watchlist()
    report: dict = {
        "at_et": now_et().isoformat(),
        "symbols": symbols,
        "finnhub_general": 0,
        "finnhub_sentiment": 0,
        "headlines_warmed": 0,
        "polygon_snapshots": 0,
        "llm_batch": False,
    }

    # 1) One Finnhub general-news call → fan out to watchlist
    from intel.finnhub_batch import fetch_general_news

    general = fetch_general_news()
    report["finnhub_general"] = len(general)
    if general:
        texts = [
            f"{g.get('headline', '')} {g.get('summary', '')}".strip()
            for g in general
            if isinstance(g, dict)
        ]
        mapped = match_symbols_in_texts(texts, set(symbols))
        from intel.api_budget import cache_set

        for sym, lines in mapped.items():
            if lines:
                cache_set("headlines", f"{sym}:morning_general", lines, ttl_sec=1800)

    # 2) Sentiment + headline cache per symbol (Finnhub sentiment-first loophole)
    from intel.finnhub_batch import fetch_sentiment
    from intel.headline_fetch_parallel import fetch_headline_groups_parallel

    for sym in symbols:
        sent = fetch_sentiment(sym)
        if sent:
            report["finnhub_sentiment"] += 1
        fh, na, cr = fetch_headline_groups_parallel(sym, finnhub_limit=15, news_limit=8, cramer_limit=0)
        if fh or na or cr:
            report["headlines_warmed"] += 1

    # 3) Polygon batch snapshots (optional)
    if os.getenv("POLYGON_API_KEY", "").strip():
        from intel.polygon_batch import fetch_snapshots

        snaps = fetch_snapshots(symbols)
        report["polygon_snapshots"] = len(snaps)

    # 4) Alpaca read-only mid prices (free data API during intel window)
    if os.getenv("MORNING_PREFETCH_ALPACA_QUOTES", "true").lower() in ("1", "true", "yes"):
        try:
            from alpaca_broker import get_mid_price

            for sym in symbols[:12]:
                get_mid_price(sym)
        except Exception:
            pass

    # 5) One batched LLM call for playbook top names
    if os.getenv("MORNING_LLM_BATCH", "true").lower() in ("1", "true", "yes") and symbols:
        try:
            from intel.api_coverage import allow_provider
            from intel.llm_signal_agent import score_text_with_llm

            ok_llm, _ = allow_provider("llm", context="morning")
            if ok_llm:
                top = symbols[: int(os.getenv("MORNING_LLM_BATCH_SIZE", "8"))]
                blob = "\n".join(f"- {s}" for s in top)
                score_text_with_llm(
                    f"Pre-market watchlist for US equities Monday open:\n{blob}\n"
                    "Summarize sector tone and risk for these names.",
                    symbol="WATCHLIST",
                )
                report["llm_batch"] = True
        except Exception:
            pass

    # 6) Cramer Investing Club — auto-fetch online + conviction refresh
    if os.getenv("MORNING_CLUB_AUTO_INGEST", "true").lower() in ("1", "true", "yes"):
        try:
            from intel.morning_club_intel import auto_ingest, load_latest

            club = auto_ingest() or load_latest()
            if club:
                report["morning_club"] = {
                    "tone": club.get("market_tone"),
                    "tickers": len(club.get("tickers") or {}),
                    "date": club.get("date"),
                    "parser": club.get("parser"),
                }
        except Exception as e:
            report["morning_club_error"] = str(e)[:120]

    # 7) Power people — public RSS, high-precision extractor, then remember()
    if os.getenv("MORNING_POWER_PEOPLE", "true").lower() in ("1", "true", "yes"):
        try:
            from tools.power_people_sync import ingest

            report["power_people"] = ingest(when=os.getenv("POWER_PEOPLE_RSS_WHEN", "1d"), limit=8)
        except Exception as e:
            report["power_people_error"] = str(e)[:120]

    report["coverage"] = coverage_report()
    out_path = ROOT / "data" / "morning_prefetch_latest.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return report


def main() -> int:
    os.chdir(ROOT)
    run_prefetch()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
