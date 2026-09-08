#!/usr/bin/env python3
"""Run one neural-ensemble online training pass as a standalone (detached) process.

Kept out of the free-agent daemon process so heavy PyTorch work cannot OOM-kill
the agent loop. Launched by self_modify/online_trainer.train_neural_online().
"""

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

    max_tickers = None
    for arg in sys.argv[1:]:
        if arg.startswith("--tickers="):
            try:
                max_tickers = int(arg.split("=", 1)[1])
            except Exception:
                max_tickers = None

    from self_modify.online_trainer import _train_neural_online_inproc

    out = _train_neural_online_inproc(max_tickers=max_tickers)
    print(out, flush=True)
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
