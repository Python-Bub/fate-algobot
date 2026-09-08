#!/usr/bin/env python3
"""Background self-improvement loop — evolves strategy overlay + policy params."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    from self_modify.code_evolver import evolve_once

    once = "--once" in sys.argv or os.getenv("SELF_IMPROVE_ONCE", "").lower() in ("1", "true", "yes")
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env", override=False)
    except Exception:
        pass
    poll = int(os.getenv("SELF_IMPROVE_POLL_SEC", "180"))
    if once:
        out = evolve_once(force="--force" in sys.argv)
        print(f"[self-improve] {out}", flush=True)
        return 0 if out.get("ok") else 1
    print(f"[self-improve] daemon poll={poll}s", flush=True)
    while True:
        try:
            out = evolve_once()
            if out.get("ok"):
                print(f"[self-improve] evolved gen={out.get('generation')} — {out.get('rationale')}", flush=True)
            else:
                print(f"[self-improve] skip: {out.get('reason')}", flush=True)
        except Exception as e:
            print(f"[self-improve] error: {e}", flush=True)
        time.sleep(poll)


if __name__ == "__main__":
    raise SystemExit(main())
