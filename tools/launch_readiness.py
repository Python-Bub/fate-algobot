#!/usr/bin/env python3
"""Launch readiness — insider, defensive, liquidity, industry, family-forecast speed."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / "venv/bin/python"


def _check(name: str, ok: bool, detail: str = "", *, warn: bool = False) -> bool:
    tag = "WARN" if warn and ok else ("OK" if ok else "FAIL")
    print(f"  [{tag}] {name}" + (f" — {detail}" if detail else ""))
    return ok or warn


def main() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    rc = 0

    print("=== launch readiness ===\n")

    # Module imports
    try:
        from intel.insider_signals import assess_insider_flow
        from intel.earnings_defensive_signals import assess_pre_earnings_defensive
        from analytics.liquidity_impact import assess_order_liquidity

        _check("intel modules", True, "insider + defensive + liquidity")
        ed = assess_pre_earnings_defensive(
            "DEMO",
            documents=["didn't work don't worry earnings might not be that high"],
            days_to_earnings=3,
        )
        _check("earnings defensive scan", ed.get("active"), f"intensity={ed.get('intensity')}")
        liq = assess_order_liquidity("DEMO", 1_000_000, 50.0)
        _check("liquidity model", liq.get("adv_usd", 0) > 0, f"adv=${liq.get('adv_usd', 0):,.0f}")
    except Exception as e:
        _check("intel modules", False, str(e))
        rc = 1

    # Industry neural model
    mlp = ROOT / "models/industry_neural/blend_mlp.pkl"
    _check("industry neural model", mlp.is_file(), str(mlp), warn=not mlp.is_file())

    # Family forecast speed (should finish < 120s on cached report)
    print("\n-- family-forecast speed --")
    t0 = time.perf_counter()
    try:
        r = subprocess.run(
            [str(PY), "-u", "tools/family_forecast.py", "--json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=180,
            env={**os.environ, "FAMILY_LIGHT_INDUSTRY": "true"},
        )
        elapsed = time.perf_counter() - t0
        ok = r.returncode == 0 and elapsed < 120
        if not _check("family-forecast", ok, f"{elapsed:.1f}s rc={r.returncode}"):
            rc = 1
            if r.stderr:
                print(r.stderr[-800:])
    except subprocess.TimeoutExpired:
        _check("family-forecast", False, "timeout >180s")
        rc = 1

    # Targeted pytest
    print("\n-- pytest (launch signals) --")
    t = subprocess.run(
        [
            str(PY),
            "-m",
            "pytest",
            "tests/test_insider_earnings_liquidity.py",
            "tests/test_category_decision.py",
            "tests/test_industry_similarity.py",
            "-q",
            "--tb=line",
        ],
        cwd=ROOT,
    )
    if t.returncode != 0:
        rc = 1

    print(f"\n=== launch readiness done rc={rc} ===")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
