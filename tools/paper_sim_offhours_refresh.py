#!/usr/bin/env python3
"""Off-hours paper_sim refresh for family-forecast (no order placement)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

os.environ.setdefault("PAPER_SIM_ALLOW_OFFHOURS", "true")
os.environ.setdefault("HOLD_DAYS_DEFAULT", "1")
os.environ.setdefault("PAPER_SIM_WORKERS", "2")
os.environ.setdefault("PAPER_SIM_LITE_INTEL", "true")
os.environ.setdefault("FEATURE_BUILD_CACHE", "false")

from paper_sim_today import run_paper_simulation_today

# Need ≥ PAPER_REPORT_MIN_TRADEABLE (default 100) scored names for a usable report.
mx = int(os.getenv("PAPER_SIM_MAX_SYMBOLS", "160"))
doc = run_paper_simulation_today(max_symbols=mx)
print(
    "DONE scored",
    doc.get("symbols_scored"),
    "rows",
    len(doc.get("rows") or []),
    "err",
    doc.get("error"),
    "skip",
    doc.get("skip_reason"),
)
