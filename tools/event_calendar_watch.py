#!/usr/bin/env python3
"""Refresh public event clocks (ClinicalTrials.gov + 8-K titles + guidance regex).

  ./venv/bin/python tools/event_calendar_watch.py --once
  ./venv/bin/python tools/event_calendar_watch.py --once --no-sec

Does not predict unpublished trial *results*. Writes data/intel/event_calendar.json
for rank_pipeline / historical_events.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="single refresh then exit")
    ap.add_argument("--no-sec", action="store_true", help="skip EDGAR 8-K titles")
    ap.add_argument("--page-size", type=int, default=int(os.getenv("EVENT_CALENDAR_PAGE_SIZE", "40")))
    ap.add_argument("--sponsors", nargs="*", help="override CT.gov query.spons list")
    args = ap.parse_args()

    from analytics.event_calendar import refresh_event_calendar

    pause = float(os.getenv("EVENT_CALENDAR_LOOP_SEC", "21600"))
    while True:
        extra: dict[str, str] = {}
        # Optional operator overlay: data/intel/event_guidance_text.json {"MRNA": "topline in 2H 2026"}
        overlay = ROOT / "data" / "intel" / "event_guidance_text.json"
        if overlay.is_file():
            try:
                raw = json.loads(overlay.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    extra = {str(k).upper(): str(v) for k, v in raw.items() if v}
            except Exception:
                extra = {}
        doc = refresh_event_calendar(
            sponsors=list(args.sponsors) if args.sponsors else None,
            extra_text=extra,
            fetch_sec=not args.no_sec,
            page_size=max(10, int(args.page_size)),
        )
        top = doc.get("top") or []
        print(
            json.dumps(
                {
                    "as_of": doc.get("as_of"),
                    "n_studies": doc.get("n_studies"),
                    "n_tickers": doc.get("n_tickers"),
                    "top": top[:8],
                    "disclaimer": doc.get("disclaimer"),
                },
                indent=2,
            ),
            flush=True,
        )
        if args.once:
            return 0
        import time

        time.sleep(max(600.0, pause))


if __name__ == "__main__":
    raise SystemExit(main())
