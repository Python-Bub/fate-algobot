#!/usr/bin/env python3
"""One-shot Jim Cramer post-market / Mad Money / Homestretch sync.

  ./venv/bin/python -u tools/cramer_post_market_once.py
  ./venv/bin/python -u tools/cramer_post_market_once.py --force
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
except Exception:
    pass


def main() -> int:
    from intel.cramer_post_market import sync_post_market_cramer

    force = "--force" in sys.argv
    report = sync_post_market_cramer(force=force)
    print(json.dumps(report, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
