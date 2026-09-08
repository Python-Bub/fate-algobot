#!/usr/bin/env python3
"""Print centralized strategy family coverage and env knobs."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analytics.strategy_registry import STRATEGY_CATALOG, families_for_runtime


def _fmt_env(name: str) -> str:
    return name if name else "-"


def main() -> int:
    runtimes = ("paper", "fortress", "daily", "intraday", "subsecond", "day_trade")
    print("STRATEGY REGISTRY AUDIT")
    print(f"  total families: {len(STRATEGY_CATALOG)}")
    print("")
    for rt in runtimes:
        fams = families_for_runtime(rt)
        print(f"[{rt}] {len(fams)} families")
        for s in fams:
            print(
                f"  - {s.id:22s}  horizon={s.horizon:9s}  "
                f"enable={_fmt_env(s.env_enable):28s}  weight={_fmt_env(s.env_weight)}"
            )
        print("")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
