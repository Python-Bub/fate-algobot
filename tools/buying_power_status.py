#!/usr/bin/env python3
"""Print the live buying-power plan (overnight 1.0× cash vs same-day DTBP)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analytics.buying_power import refresh_and_persist


def main() -> int:
    quiet = "--quiet" in sys.argv or "-q" in sys.argv
    plan = refresh_and_persist()
    d = plan.to_dict()
    if quiet:
        print(
            f"  GET /v2/account  equity=${d['equity']:.0f}  cash=${d['cash']:.0f}  "
            f"buying_power=${d['buying_power']:.0f}  long=${d['long_mv']:.0f}  "
            f"gap=${d['overnight_gap']:.0f}  overnight_clip=${d['overnight_clip']:.0f}  "
            f"hft_clip=${d['hft_clip']:.0f}  pnl=${d.get('daily_pnl', 0):+.0f}  "
            f"{'FULL' if d['overnight_full'] else 'IDLE CASH'}"
        )
        return 0
    print(json.dumps(d, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
