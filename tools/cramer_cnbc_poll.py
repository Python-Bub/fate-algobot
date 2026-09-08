#!/usr/bin/env python3
"""Poll CNBC Top 10 URL every invocation — use with daemon_loop.sh 15."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def main() -> int:
    from intel.cramer_cnbc_top10 import (
        already_ingested_today,
        poll_and_ingest_cnbc_top10,
        poll_window_open,
    )

    force = "--force" in sys.argv
    if not force:
        if already_ingested_today():
            print(json.dumps({"skipped": True, "reason": "already_ingested_today"}))
            return 0
        # Re-run AI on today's article if OpenAI was rate-limited earlier
        try:
            from intel.cramer_cnbc_top10 import _load_cnbc_sync, fetch_cnbc_top10, now_et

            st = _load_cnbc_sync()
            if st.get("ai_pending") and st.get("url"):
                hit = fetch_cnbc_top10(now_et().date())
                if hit:
                    from intel.morning_club_intel import ingest_morning_email

                    doc = ingest_morning_email(hit[1], source=f"cnbc_ai_retry:{st['url']}")
                    if "ai" in str(doc.get("parser", "")):
                        from intel.cramer_cnbc_top10 import _save_cnbc_sync

                        _save_cnbc_sync(
                            {
                                **st,
                                "ai_pending": False,
                                "ingested": True,
                                "parser": doc.get("parser"),
                                "ai_confidence": doc.get("ai_confidence"),
                                "tickers": len(doc.get("tickers") or {}),
                            }
                        )
                        try:
                            from intel.club_conviction_engine import refresh_dynamic_conviction

                            refresh_dynamic_conviction()
                        except Exception:
                            pass
                    print(json.dumps({"ai_retry": True, "parser": doc.get("parser")}, indent=2))
                    return 0
        except Exception:
            pass
        ok, reason = poll_window_open()
        if not ok:
            print(json.dumps({"skipped": True, "reason": reason}))
            return 0

    report = poll_and_ingest_cnbc_top10(force=force)
    print(json.dumps(report, indent=2))
    return 0 if report.get("ok") or report.get("reason") == "not_published_yet" else 1


if __name__ == "__main__":
    raise SystemExit(main())
