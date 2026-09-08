#!/usr/bin/env python3
"""Recursive singularity daemon — plastic neurons + optional code evolution."""

from __future__ import annotations

import os
import sys
import time
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

    from cortex.singularity import singularity_step

    once = "--once" in sys.argv or os.getenv("CORTEX_ONCE", "").lower() in ("1", "true", "yes")
    force = "--force" in sys.argv
    poll = int(os.getenv("CORTEX_POLL_SEC", "120"))

    if once:
        out = singularity_step(force_evolve=force)
        print(f"[singularity] {out}", flush=True)
        return 0 if out.get("ok") else 1

    print(f"[singularity] daemon poll={poll}s", flush=True)
    while True:
        try:
            out = singularity_step(force_evolve=False)
            if out.get("ok"):
                print(
                    f"[singularity] gen={out.get('generation')} "
                    f"awareness={out.get('awareness')} reward={out.get('reward'):+.4f} "
                    f"action={out.get('rl_action')} equity={out.get('equity')} "
                    f"delta={out.get('equity_delta')} agi={out.get('agi_agent')}",
                    flush=True,
                )
            else:
                print(f"[singularity] skip: {out.get('reason')}", flush=True)
        except Exception as e:
            print(f"[singularity] error: {e}", flush=True)
        time.sleep(poll)


if __name__ == "__main__":
    raise SystemExit(main())
