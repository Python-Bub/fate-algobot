#!/usr/bin/env python3
"""Refresh shared earnings calendar (Finnhub hours + IR overrides) and write coverage stats."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)


def main() -> int:
    from intel.earnings_calendar import build_shared_earnings_calendar, earnings_snapshot
    from intel.historical_events import refresh_earnings_radar

    force = "--force" in sys.argv
    doc = build_shared_earnings_calendar(force_refresh=force)
    radar = refresh_earnings_radar(
        ["SBUX", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "NVDA", "AMD", "CRM", "WMT", "JNJ"]
    )
    sbux = doc.get("sbux") or earnings_snapshot("SBUX")
    samples = {}
    for s in ("SBUX", "AAPL", "MSFT", "META", "AMZN"):
        samples[s] = earnings_snapshot(s)

    try:
        from tools.export_all_earnings_dates import main as export_main

        export_main()
    except Exception as e:
        # Fallback: run as script path import may fail depending on package layout
        import runpy

        try:
            runpy.run_path(str(Path(__file__).resolve().parent / "export_all_earnings_dates.py"), run_name="__main__")
        except Exception as e2:
            print(f"export_all_earnings_dates failed: {e} / {e2}", file=sys.stderr)

    out = {
        "coverage": {
            "universe_n": doc.get("universe_n"),
            "with_next_date": doc.get("with_next_date"),
            "with_session_hour": doc.get("with_session_hour"),
            "with_call_clock": doc.get("with_call_clock"),
            "pct_hour_given_date": doc.get("pct_hour_given_date"),
        },
        "sbux": sbux,
        "samples": {
            k: {
                "next_earnings_date": v.get("next_earnings_date"),
                "hour": v.get("hour"),
                "prev_earnings_date": v.get("prev_earnings_date"),
                "last_earnings_date": v.get("last_earnings_date"),
                "days_since_earnings": v.get("days_since_earnings"),
                "next_datetime_et": v.get("next_datetime_et"),
                "next_datetime_pt": v.get("next_datetime_pt"),
                "call_time_pt": v.get("call_time_pt"),
                "call_time_et": v.get("call_time_et"),
            }
            for k, v in samples.items()
        },
        "radar_sbux": next(
            (h for h in (radar.get("holdings") or []) if h.get("symbol") == "SBUX"),
            None,
        ),
        "radar_msft": next(
            (h for h in (radar.get("holdings") or []) if h.get("symbol") == "MSFT"),
            None,
        ),
        "path": "data/intel/earnings_calendar.json",
        "export_md": "data/ops/ALL_EARNINGS_DATES.md",
        "export_json": "data/ops/ALL_EARNINGS_DATES.json",
    }
    Path("data/ops").mkdir(parents=True, exist_ok=True)
    Path("data/ops/earnings_calendar_refresh.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
