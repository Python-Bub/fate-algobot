"""Hard gate: talk / operator / big_brain edits OFF until 1B problems.

Optimize never remove — training continues; only mutation authority is locked.
TALK_ALLOW_EDITS env alone is NOT enough; problems_done must reach BILLION_THRESHOLD.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PROGRESS_JSONL = ROOT / "data" / "talk_brain" / "trillion_progress.jsonl"
CKPT_PATH = ROOT / "data" / "talk_brain" / "massive_harness_checkpoint.json"
RESULTS_PATH = ROOT / "data" / "talk_brain" / "massive_harness_results.json"
STATUS_PATH = ROOT / "data" / "talk_brain" / "edit_gate_status.json"
DENY_LOG = ROOT / "data" / "talk_brain" / "edit_denials.jsonl"

# Hard threshold: one billion problems before any AI repo edits.
BILLION_THRESHOLD = 1_000_000_000


def _env_wants_edits() -> bool:
    return os.getenv("TALK_ALLOW_EDITS", "false").lower() in ("1", "true", "yes")


def problems_done() -> int:
    """Honest cumulative teacher problems from checkpoint + progress jsonl."""
    best = 0
    if CKPT_PATH.is_file():
        try:
            doc = json.loads(CKPT_PATH.read_text(encoding="utf-8"))
            best = max(best, int(doc.get("teacher_done") or 0))
            best = max(best, int(doc.get("problems_done") or 0))
            meta = doc.get("meta") or {}
            if isinstance(meta, dict):
                best = max(best, int(meta.get("teacher_done") or 0))
                best = max(best, int(meta.get("problems_done") or 0))
        except Exception:
            pass
    if RESULTS_PATH.is_file():
        try:
            doc = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
            teacher = doc.get("teacher") or {}
            if isinstance(teacher, dict):
                best = max(best, int(teacher.get("teacher_done") or 0))
                best = max(best, int(teacher.get("problems_done") or 0))
        except Exception:
            pass
    if PROGRESS_JSONL.is_file():
        try:
            # Tail scan — last ~200 lines enough for max teacher done
            lines = PROGRESS_JSONL.read_text(encoding="utf-8").splitlines()[-200:]
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                phase = str(row.get("phase") or "")
                if phase and phase not in ("teacher", "generate", "problems"):
                    continue
                for key in ("problems_done", "done", "teacher_done"):
                    if key in row:
                        try:
                            best = max(best, int(row[key]))
                        except (TypeError, ValueError):
                            pass
        except Exception:
            pass
    return int(best)


def billion_unlocked() -> bool:
    return problems_done() >= BILLION_THRESHOLD


def progress_snapshot() -> dict[str, Any]:
    done = problems_done()
    snap = {
        "ts": time.time(),
        "problems_done": done,
        "billion_threshold": BILLION_THRESHOLD,
        "billion_unlocked": done >= BILLION_THRESHOLD,
        "pct_of_1b": round(100.0 * done / max(BILLION_THRESHOLD, 1), 6),
        "remaining_to_1b": max(0, BILLION_THRESHOLD - done),
        "env_TALK_ALLOW_EDITS": _env_wants_edits(),
        "edits_allowed": False,  # filled below
        "note": (
            "Edits stay locked until problems_done >= 1e9 AND TALK_ALLOW_EDITS=true. "
            "Closing the Mac stops local caffeinate/daemons; resume with "
            "./tools/resume_massive_training.sh --continue"
        ),
        "sources": {
            "checkpoint": str(CKPT_PATH.relative_to(ROOT)) if CKPT_PATH.is_file() else None,
            "progress_jsonl": str(PROGRESS_JSONL.relative_to(ROOT)) if PROGRESS_JSONL.is_file() else None,
        },
    }
    snap["edits_allowed"] = bool(snap["billion_unlocked"] and snap["env_TALK_ALLOW_EDITS"])
    return snap


def persist_status() -> dict[str, Any]:
    snap = progress_snapshot()
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps(snap, indent=2), encoding="utf-8")
    return snap


def log_denial(source: str, *, reason: str = "", detail: dict[str, Any] | None = None) -> None:
    DENY_LOG.parent.mkdir(parents=True, exist_ok=True)
    snap = progress_snapshot()
    rec = {
        "ts": time.time(),
        "event": "edit_denied",
        "source": source,
        "reason": reason or "billion_gate",
        "problems_done": snap["problems_done"],
        "billion_threshold": BILLION_THRESHOLD,
        "env_TALK_ALLOW_EDITS": snap["env_TALK_ALLOW_EDITS"],
        "detail": detail or {},
    }
    with DENY_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    try:
        persist_status()
    except Exception:
        pass


def edits_allowed(*, source: str = "unknown", log: bool = True) -> bool:
    """Single source of truth for talk / operator / big_brain mutation authority."""
    done = problems_done()
    env_ok = _env_wants_edits()
    unlocked = done >= BILLION_THRESHOLD
    allowed = bool(unlocked and env_ok)
    if not allowed and log:
        why = []
        if not unlocked:
            why.append(f"problems_done={done}<{BILLION_THRESHOLD}")
        if not env_ok:
            why.append("TALK_ALLOW_EDITS=false")
        log_denial(source, reason=";".join(why) or "gated")
    return allowed


def require_edits(*, source: str, action: str = "edit") -> dict[str, Any]:
    """Return {ok:False,...} if gated; {ok:True} if allowed. Always logs denials."""
    if edits_allowed(source=source, log=True):
        return {"ok": True, "problems_done": problems_done()}
    snap = progress_snapshot()
    return {
        "ok": False,
        "reason": "edit_gate_locked",
        "action": action,
        "source": source,
        "problems_done": snap["problems_done"],
        "billion_threshold": BILLION_THRESHOLD,
        "remaining_to_1b": snap["remaining_to_1b"],
        "env_TALK_ALLOW_EDITS": snap["env_TALK_ALLOW_EDITS"],
        "message": (
            f"AI edits locked until {BILLION_THRESHOLD:,} problems "
            f"(now {snap['problems_done']:,}; {snap['pct_of_1b']}% of 1B)."
        ),
    }
