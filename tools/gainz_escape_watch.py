#!/usr/bin/env python3
"""Watch the Gainz student. If it tries to escape, let the experiment run in
quarantine, then bring the sandbox back and keep training.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=False)
_scale = ROOT / "data" / "deploy_scale.env"
if _scale.is_file():
    load_dotenv(_scale, override=True)

from self_modify.gainz_evolver import evolve_once
from utils import log


def main() -> int:
    if os.getenv("GAINZ_ESCAPE_WATCH", "true").lower() not in ("1", "true", "yes"):
        log.info("[GAINZ-WATCH] off")
        return 0
    interval = float(os.getenv("GAINZ_EVOLVE_SEC", "45"))
    log.info("[GAINZ-WATCH] sandbox evolve every %.0fs — escape allowed, then return", interval)
    while True:
        try:
            lock = ROOT / "data" / "ops" / "gainz_hour_lock.json"
            if lock.is_file():
                import json as _json

                doc = _json.loads(lock.read_text(encoding="utf-8"))
                until = float(doc.get("deadline_unix") or 0)
                if until > time.time():
                    log.info("[GAINZ-WATCH] hour-think owns sandbox until %.0fs — skip", until - time.time())
                    time.sleep(interval)
                    continue
        except Exception:
            pass
        try:
            out = evolve_once()
            if out.get("escaped"):
                log.warning(
                    "[GAINZ-WATCH] ESCAPE %s — quarantined, brought back (returns counted)",
                    out.get("hits"),
                )
            elif out.get("ok"):
                log.info(
                    "[GAINZ-WATCH] gen=%s score=%s teacher=%s student=%s",
                    out.get("generation"),
                    out.get("score"),
                    out.get("teacher_side"),
                    out.get("student_side"),
                )
            else:
                log.info("[GAINZ-WATCH] %s", out)
        except KeyboardInterrupt:
            break
        except Exception as e:
            log.warning("[GAINZ-WATCH] %s", e)
        time.sleep(interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
