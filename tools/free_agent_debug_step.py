#!/usr/bin/env python3
"""Run one free_agent_step with a watchdog that dumps the stack if it hangs."""

from __future__ import annotations

import faulthandler
import os
import sys
import threading
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

    faulthandler.enable()
    # Dump all thread stacks after 35s if still running, every 15s after.
    faulthandler.dump_traceback_later(35, repeat=True)

    from self_modify.free_agent import free_agent_step

    t0 = time.time()
    print(f"[debug] starting free_agent_step force=True", flush=True)
    out = free_agent_step(force=True)
    print(f"[debug] completed in {time.time()-t0:.1f}s ok={out.get('ok')}", flush=True)
    print(out, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
