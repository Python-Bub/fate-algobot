#!/usr/bin/env python3
"""Fail loud if critical env values are empty on regular runs.

Usage:
  ./venv/bin/python -u tools/validate_env.py
  ./run_all.sh validate-env
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")
load_dotenv(ROOT / "data" / "deploy_scale.env", override=True)

# Keys that must be non-empty for a normal paper/live stack run.
# (Secrets themselves are not printed — only names.)
CRITICAL = [
    "APCA_API_KEY_ID",
    "APCA_API_SECRET_KEY",
]

# Prefer either naming style
CRITICAL_ALT = {
    "APCA_API_KEY_ID": ["ALPACA_API_KEY", "APCA_API_KEY_ID"],
    "APCA_API_SECRET_KEY": ["ALPACA_SECRET_KEY", "APCA_API_SECRET_KEY", "ALPACA_API_SECRET_KEY"],
}

# Soft-critical: warn but exit non-zero if STRICT_ENV=true
IMPORTANT = [
    "ORDER_NOTIONAL",
    "FORTRESS_MAX_POSITIONS",
    "FORTRESS_TARGET_DEPLOY_FRAC",
    "TRAIN_PRIORITIZE",
]


def _present(keys: list[str]) -> bool:
    for k in keys:
        v = os.getenv(k)
        if v is not None and str(v).strip() != "":
            return True
    return False


def validate(*, strict: bool | None = None) -> int:
    if strict is None:
        strict = os.getenv("STRICT_ENV", "true").lower() in ("1", "true", "yes")

    missing: list[str] = []
    empty_important: list[str] = []

    for canon, alts in CRITICAL_ALT.items():
        if not _present(alts):
            missing.append(canon)

    for k in IMPORTANT:
        v = os.getenv(k)
        if v is None or str(v).strip() == "":
            empty_important.append(k)

    # Default TRAIN_PRIORITIZE if unset — repair in-process for this process only
    repairs: list[str] = []
    if not os.getenv("TRAIN_PRIORITIZE"):
        os.environ["TRAIN_PRIORITIZE"] = "letter_rr"
        repairs.append("TRAIN_PRIORITIZE=letter_rr")
    if not os.getenv("USE_CRAMER_HOT_PICKS"):
        os.environ["USE_CRAMER_HOT_PICKS"] = "true"
        repairs.append("USE_CRAMER_HOT_PICKS=true")
    if not os.getenv("USE_INVESTOR_SUCCESSION"):
        os.environ["USE_INVESTOR_SUCCESSION"] = "true"
        repairs.append("USE_INVESTOR_SUCCESSION=true")

    if missing:
        print("[validate-env] FAIL — empty/missing critical keys:", ", ".join(missing))
        print("[validate-env] repair: set them in .env (never commit secrets)")
        return 2

    if empty_important:
        msg = "[validate-env] empty important keys: " + ", ".join(empty_important)
        if strict:
            print(msg + " (STRICT_ENV=true → fail)")
            print("[validate-env] repair: fill data/deploy_scale.env or .env")
            return 1
        print(msg + " (warn)")

    if repairs:
        print("[validate-env] applied process repairs:", "; ".join(repairs))
    print("[validate-env] OK — critical keys present; TRAIN_PRIORITIZE=%s" % os.getenv("TRAIN_PRIORITIZE"))
    return 0


def main() -> int:
    return validate()


if __name__ == "__main__":
    raise SystemExit(main())
