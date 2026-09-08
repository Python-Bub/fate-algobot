#!/usr/bin/env python3
"""Daily autonomous Cramer / Investing Club intel sync + dynamic conviction refresh."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def main() -> int:
    from intel.club_conviction_engine import refresh_dynamic_conviction
    from intel.cramer_email_fetcher import sync_daily_cramer_intel

    force = "--force" in sys.argv
    cramer = sync_daily_cramer_intel(force=force)
    conviction = refresh_dynamic_conviction()
    out = {"cramer": cramer, "conviction": conviction}
    print(json.dumps(out, indent=2))
    return 0 if cramer.get("ok") or cramer.get("skipped") else 1


if __name__ == "__main__":
    raise SystemExit(main())
