#!/usr/bin/env python3
"""Free agent daemon — reads prompts, plans via online LLM, trains + self-edits all day."""

from __future__ import annotations

import faulthandler
import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run_step_with_timeout(free_agent_step, *, timeout: float):
    """Run one step in a worker thread; if it wedges (network/lock), abandon it and
    keep the daemon alive. A wedged thread is daemonized so the loop never blocks."""
    result: dict = {}
    done = threading.Event()

    def _worker():
        try:
            result["out"] = free_agent_step(force=False)
        except Exception as e:  # noqa: BLE001
            result["err"] = str(e)
        finally:
            done.set()

    th = threading.Thread(target=_worker, name="free-agent-step", daemon=True)
    th.start()
    if not done.wait(timeout):
        faulthandler.dump_traceback(file=sys.stderr)
        return {"ok": False, "reason": f"step_timeout_{int(timeout)}s"}
    if "err" in result:
        return {"ok": False, "reason": result["err"][:200]}
    return result.get("out", {"ok": False, "reason": "no_result"})


def main() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env", override=False)
    except Exception:
        pass

    faulthandler.enable()

    from self_modify.free_agent import free_agent_step
    from self_modify.prompt_inbox import ensure_inbox

    ensure_inbox()
    once = "--once" in sys.argv
    force = "--force" in sys.argv
    poll = int(os.getenv("FREE_AGENT_POLL_SEC", "45"))
    step_timeout = float(os.getenv("FREE_AGENT_STEP_TIMEOUT_SEC", "120"))

    if once:
        out = free_agent_step(force=force)
        print(out, flush=True)
        return 0 if out.get("ok") else 1

    print(
        f"[free-agent] daemon poll={poll}s step_timeout={step_timeout:.0f}s objective=grow equity",
        flush=True,
    )
    while True:
        try:
            out = _run_step_with_timeout(free_agent_step, timeout=step_timeout)
            if out.get("ok"):
                print(
                    f"[free-agent] gen={out.get('generation')} equity={out.get('equity')} "
                    f"delta={out.get('equity_delta')} plan={out.get('plan')}",
                    flush=True,
                )
            else:
                print(f"[free-agent] skip: {out.get('reason')}", flush=True)
        except Exception as e:
            print(f"[free-agent] error: {e}", flush=True)
        time.sleep(poll)


if __name__ == "__main__":
    raise SystemExit(main())
