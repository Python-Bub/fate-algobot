"""
User prompt inbox — the agent reads natural-language instructions from here.

Drop `.md` or `.txt` files into data/agi/inbox/ (or edit MASTER_PROMPT.md).
Processed files move to data/agi/inbox/processed/.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
INBOX = Path(os.getenv("AGI_PROMPT_INBOX", "data/agi/inbox"))
PROCESSED = INBOX / "processed"
OUTBOX = Path(os.getenv("AGI_PROMPT_OUTBOX", "data/agi/outbox"))
MASTER = INBOX / "MASTER_PROMPT.md"
STATE_PATH = Path(os.getenv("AGI_PROMPT_STATE", "data/agi/prompt_state.json"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_inbox() -> None:
    INBOX.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    OUTBOX.mkdir(parents=True, exist_ok=True)
    if not MASTER.is_file():
        MASTER.write_text(
            "# Master directive\n\n"
            "Primary objective: **Make portfolio account larger**.\n\n"
            "You have autonomy to evolve strategy code, train models (LSTM, neural ensemble, "
            "intraday), tune execution params, and redeploy the stack when equity stalls.\n"
            "Prefer aggressive deployment of buying power when edge is positive.\n",
            encoding="utf-8",
        )


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(st: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(st, indent=2), encoding="utf-8")


def read_pending_prompts(*, max_files: int = 5) -> list[dict[str, Any]]:
    """Return unread prompt documents (newest first)."""
    ensure_inbox()
    st = _load_state()
    seen = set(st.get("processed_files") or [])
    out: list[dict[str, Any]] = []

    # Master prompt always included (live reread).
    if MASTER.is_file():
        out.append(
            {
                "path": str(MASTER),
                "name": MASTER.name,
                "text": MASTER.read_text(encoding="utf-8")[:12000],
                "persistent": True,
            }
        )

    candidates: list[Path] = []
    for pat in ("*.md", "*.txt"):
        candidates.extend(INBOX.glob(pat))
    candidates = sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)

    for p in candidates:
        if p.name == MASTER.name:
            continue
        key = str(p.resolve())
        if key in seen:
            continue
        try:
            text = p.read_text(encoding="utf-8")[:12000]
        except Exception:
            continue
        out.append({"path": key, "name": p.name, "text": text, "persistent": False})
        if len([x for x in out if not x.get("persistent")]) >= max_files:
            break
    return out


def mark_processed(paths: list[str]) -> None:
    st = _load_state()
    done = list(st.get("processed_files") or [])
    for raw in paths:
        p = Path(raw)
        if not p.is_file() or p.name == MASTER.name:
            continue
        key = str(p.resolve())
        if key not in done:
            done.append(key)
        try:
            dest = PROCESSED / f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{p.name}"
            shutil.move(str(p), str(dest))
        except Exception:
            pass
    st["processed_files"] = done[-500:]
    st["updated_utc"] = _now()
    _save_state(st)


def write_outbox_response(text: str, *, tag: str = "agent") -> Path:
    ensure_inbox()
    path = OUTBOX / f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{tag}.md"
    path.write_text(text.strip() + "\n", encoding="utf-8")
    return path


def combined_prompt_text(prompts: list[dict[str, Any]] | None = None) -> str:
    docs = prompts if prompts is not None else read_pending_prompts()
    parts: list[str] = []
    for d in docs:
        parts.append(f"### {d.get('name', 'prompt')}\n{d.get('text', '').strip()}")
    return "\n\n".join(parts)[:20000]
