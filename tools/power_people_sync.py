#!/usr/bin/env python3
"""Ingest public headlines about market-moving people; optionally calibrate vs SPY.

Usage:
  ./run_all.sh power-people-sync
  python -u tools/power_people_sync.py --calibrate
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")
scale = ROOT / "data" / "deploy_scale.env"
if scale.is_file():
    load_dotenv(scale, override=True)

QUERIES = (
    ("trump", 'Donald Trump stock OR Tesla OR "buy this" OR "get rich"'),
    ("powell", "Jerome Powell Federal Reserve stock market"),
    ("yellen", "Janet Yellen Treasury stock market"),
    ("bessent", "Scott Bessent Treasury stock"),
    ("musk", "Elon Musk Tesla stock OR Cybertruck"),
    ("buffett", "Warren Buffett stock buy OR Berkshire"),
    ("ackman", "Bill Ackman stock"),
    ("lutnick", "Howard Lutnick Commerce stock"),
)


def ingest(*, when: str = "2d", limit: int = 10) -> dict:
    from intel.algo_memory import bootstrap_corporate_memory
    from intel.cramer_email_fetcher import fetch_google_news_rss
    from intel.power_people import append_hits, extract_mentions

    report: dict = {"ingested": 0, "items": 0, "by_speaker": {}, "memory_bootstrap": 0}
    try:
        report["memory_bootstrap"] = int(bootstrap_corporate_memory() or 0)
    except Exception:
        report["memory_bootstrap"] = 0
    seen: set[tuple[str, str, str]] = set()
    for speaker, q in QUERIES:
        try:
            items = fetch_google_news_rss(q, when=when) or []
        except Exception:
            items = []
        n_this = 0
        for it in items[:limit]:
            title = str(it.get("title") or "")
            desc = str(it.get("description") or "")
            blob = f"{title}. {desc}".strip()
            pub = it.get("published")
            mentions = extract_mentions(blob, speaker_hint=speaker, ts=pub)
            fresh = []
            for m in mentions:
                key = (str(m.get("speaker")), str(m.get("ticker")), str(m.get("quote"))[:80])
                if key in seen:
                    continue
                seen.add(key)
                fresh.append(m)
            if fresh:
                n_this += append_hits(fresh, source=f"rss:{speaker}")
        report["by_speaker"][speaker] = n_this
        report["ingested"] += n_this
        report["items"] += len(items)
    return report


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--when", default=os.getenv("POWER_PEOPLE_RSS_WHEN", "2d"))
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--calibrate", action="store_true")
    p.add_argument("--ingest", action="store_true", default=True)
    p.add_argument("--no-ingest", action="store_true")
    args = p.parse_args()
    out: dict = {}
    if not args.no_ingest:
        out["ingest"] = ingest(when=args.when, limit=args.limit)
    if args.calibrate:
        from intel.power_people import calibrate_hits

        out["calibration"] = calibrate_hits()
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
