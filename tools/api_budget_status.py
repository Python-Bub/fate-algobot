#!/usr/bin/env python3
"""Print API budget + per-provider coverage strategies."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from intel.api_coverage import coverage_report


def main() -> int:
    print(json.dumps(coverage_report(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
