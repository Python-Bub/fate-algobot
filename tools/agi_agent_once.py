#!/usr/bin/env python3
"""Run one AGI agent step (objective: grow portfolio equity)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env", override=False)
    except Exception:
        pass
    from self_modify.agi_agent import agi_step

    force = "--force" in sys.argv
    out = agi_step(force=force)
    print(out, flush=True)
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
