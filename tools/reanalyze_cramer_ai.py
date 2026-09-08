#!/usr/bin/env python3
"""Re-run AI analysis on today's (or a given) CNBC Top 10 article and refresh conviction picks."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser(description="Re-analyze Cramer Top 10 with AI")
    ap.add_argument("--date", help="YYYY-MM-DD (default: today ET)")
    ap.add_argument("--force", action="store_true", help="Bypass AI cache")
    ap.add_argument("--file", help="Plain-text article file instead of CNBC fetch")
    args = ap.parse_args()

    if args.file:
        text = Path(args.file).read_text(encoding="utf-8")
        source = f"file:{args.file}"
    else:
        from intel.cramer_cnbc_top10 import fetch_cnbc_top10, now_et

        d = date.fromisoformat(args.date) if args.date else now_et().date()
        hit = fetch_cnbc_top10(d)
        if not hit:
            print(json.dumps({"ok": False, "reason": "article_not_found", "date": d.isoformat()}))
            return 1
        source, text = f"cnbc:{hit[0]}", hit[1]

    from intel.cramer_ai_analyzer import analyze_cramer_top10, merge_ai_and_heuristic
    from intel.morning_club_intel import _heuristic_parse, ingest_morning_email

    heuristic = _heuristic_parse(text)
    ai_doc = analyze_cramer_top10(text, force_refresh=args.force)
    if ai_doc and ai_doc.get("tickers"):
        merged = merge_ai_and_heuristic(ai_doc, heuristic)
        doc = {
            "source": source,
            "ingested_at_utc": datetime.now().isoformat(),
            "date": date.today().isoformat(),
            "raw_chars": len(text),
            **merged,
        }
        from intel.morning_club_intel import LATEST_PATH

        LATEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        LATEST_PATH.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    else:
        doc = ingest_morning_email(text, source=source)

    try:
        from intel.club_conviction_engine import refresh_dynamic_conviction

        refresh_dynamic_conviction()
    except Exception:
        pass

    try:
        from intel.cramer_cnbc_top10 import _load_cnbc_sync, _save_cnbc_sync

        st = _load_cnbc_sync()
        if st.get("date") == date.today().isoformat():
            _save_cnbc_sync(
                {
                    **st,
                    "ai_pending": "ai" not in str(doc.get("parser", "")),
                    "ingested": "ai" in str(doc.get("parser", "")),
                    "parser": doc.get("parser"),
                    "ai_confidence": doc.get("ai_confidence"),
                    "tickers": len(doc.get("tickers") or {}),
                }
            )
    except Exception:
        pass

    out = {
        "ok": True,
        "parser": doc.get("parser"),
        "ai_confidence": doc.get("ai_confidence"),
        "top_buys": doc.get("top_buys"),
        "top_avoids": doc.get("top_avoids"),
        "tickers": len(doc.get("tickers") or {}),
        "day_trade_bias": doc.get("day_trade_bias"),
    }
    print(json.dumps(out, indent=2))
    return 0 if "ai" in str(doc.get("parser", "")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
