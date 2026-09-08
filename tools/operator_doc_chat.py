#!/usr/bin/env python3
"""Operator Doc chat daemon — read Google Doc (or local mirror), reply honestly, edit when warranted.

Usage:
  ./run_all.sh doc-chat          # daemon
  PYTHONPATH=. python -u tools/operator_doc_chat.py --once

Doc: https://docs.google.com/document/d/1fEuErs8mTMzSoJm4WMesxmhsfqvnlhzzFINycbRCIeU/
Fallback: data/intel/operator_chat.md
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stack_snapshot() -> dict[str, Any]:
    import subprocess

    patterns = {
        "fortress": "fortress_live.py",
        "micro_scalp": "micro_scalp_daemon.py",
        "train_top100": "train_top100_perfect.py",
        "pattern": "hidden_pattern_scan.py",
        "day_trade": "day_trade_daemon.py",
        "intraday_train": "parallel_train.py",
    }
    alive: dict[str, bool] = {}
    for name, pat in patterns.items():
        try:
            r = subprocess.run(
                ["pgrep", "-f", pat], capture_output=True, text=True, timeout=5
            )
            alive[name] = r.returncode == 0
        except Exception:
            alive[name] = False
    return alive


def _math_status() -> str:
    try:
        from analytics.math_catalog import catalog_summary
        from analytics.math_pivot import pivot_status

        ps = pivot_status()
        return (
            f"PURE_MATH_PIVOT={ps.get('pure_math_pivot')} "
            f"math_mult={ps.get('math_mult')} news_mult={ps.get('news_mult')}\n"
            f"{catalog_summary(8)}"
        )
    except Exception as e:
        return f"math status error: {e}"


def _paper_hurting() -> tuple[bool, float | None]:
    """Best-effort equity delta from common state files — honest if unknown."""
    candidates = [
        ROOT / "data" / "agi" / "free_agent_state.json",
        ROOT / "data" / "intel" / "micro_scalp_state.json",
        ROOT / "data" / "paper" / "equity_snapshot.json",
    ]
    for p in candidates:
        if not p.is_file():
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            for k in ("equity_delta", "pnl_day", "day_pnl", "realized_pnl"):
                if k in d and d[k] is not None:
                    v = float(d[k])
                    return v < 0, v
        except Exception:
            continue
    return False, None


def _handle_commands(cmds: list[str], user_text: str) -> tuple[str, dict[str, Any]]:
    from intel.operator_code_edit import apply_honest_fix, trigger_evolve

    bits: list[str] = []
    meta: dict[str, Any] = {"edits": []}
    for c in cmds:
        if c == "help":
            bits.append(
                "Commands: [[status]] [[train]] [[explain last loss]] [[evolve]] "
                "[[fix]] [[math]] [[mood]] [[help]]. Write `USER: …` then wait for `AI:`."
            )
        elif c == "status":
            snap = _stack_snapshot()
            dead = [k for k, v in snap.items() if not v]
            bits.append(
                "Stack: "
                + ", ".join(f"{k}={'up' if v else 'DOWN'}" for k, v in snap.items())
            )
            if dead:
                bits.append(
                    f"Honest: these look down right now: {', '.join(dead)}. "
                    "I will not claim the stack is healthy."
                )
            else:
                bits.append("Core processes I check are up.")
            bits.append(_math_status())
        elif c == "math":
            bits.append(_math_status())
            bits.append("Catalog: analytics/math_manifest.md · analytics/math_catalog.py")
        elif c == "mood":
            from intel.operator_persona import update_mood

            hurt, delta = _paper_hurting()
            st = update_mood(delta, paper_hurting=hurt)
            bits.append(
                f"mood={st.mood} concern={st.concern:.2f} confidence={st.confidence:.2f}\n"
                f"{st.last_thought}"
            )
        elif c == "explain last loss":
            hurt, delta = _paper_hurting()
            bits.append(
                "I do not have a perfect single-trade postmortem wired to this chat yet. "
                f"Best equity/pnl signal I see: delta={delta}. "
                "Working hypothesis under math pivot: narrative/news still competing with "
                "factor + residual + cointegration signals; check operator_math_overrides "
                "and rank components. Prefer fixing weights over deleting capability."
            )
            if hurt or (user_text and any(w in user_text.lower() for w in ("loss", "losing", "red"))):
                meta["edits"].append(apply_honest_fix("loss", user_text=user_text))
        elif c == "train":
            bits.append(
                "I will not tear down running trainers. Enqueue ensure_training via free-agent "
                "if gaps exist; stack keepalive stays."
            )
            meta["edits"].append(
                apply_honest_fix("train", user_text="ensure training continues; do not stop live trains")
            )
        elif c == "evolve":
            bits.append("Triggering guarded evolve / free-agent step (allowlisted surfaces only).")
            meta["edits"].append(trigger_evolve(force=True))
        elif c == "fix":
            bits.append(
                "Assessing from your message — if something is actually wrong I will change "
                "math overrides and/or enqueue self-improve. No model deletes, no universe shrink."
            )
            meta["edits"].append(apply_honest_fix(user_text or "fix", user_text=user_text))
    return "\n\n".join(bits) if bits else "", meta


def build_reply(user_text: str, *, backend: str) -> str:
    from intel.operator_code_edit import apply_honest_fix, parse_command_tags
    from intel.operator_doc import auth_setup_instructions, google_docs_available
    from intel.operator_persona import (
        format_reply,
        honest_critique_for_topic,
        update_mood,
    )

    hurt, delta = _paper_hurting()
    st = update_mood(delta, paper_hurting=hurt)
    cmds = parse_command_tags(user_text)
    cmd_body, meta = _handle_commands(cmds, user_text)
    critique = honest_critique_for_topic(user_text)

    # Auto-edit when user describes real pain / quality issues (even without [[fix]])
    edits_note = ""
    if critique and not cmds:
        edit_out = apply_honest_fix(user_text, user_text=user_text)
        meta.setdefault("edits", []).append(edit_out)
    if meta.get("edits"):
        n = len(meta["edits"])
        edits_note = f"\n\n_code actions this turn:_ {n} (logged in data/intel/operator_edits.jsonl)"

    ok_g, reason = google_docs_available()
    transport = (
        f"Transport: **{backend}**"
        + ("" if ok_g else f" (Google not live: {reason})")
    )
    if backend == "local":
        transport += "\n" + auth_setup_instructions().split("\n")[0]

    body_parts = [
        transport,
        cmd_body or (
            f"Got it. You said: «{user_text[:400]}». "
            "Math-first pivot is on (news→z, factors/residuals/cointegration preferred). "
            "I will not invent a rosy PnL story."
        ),
        edits_note,
        f"_ts {_now()}_",
    ]
    body = "\n\n".join(p for p in body_parts if p)
    return format_reply(body, st=st, include_inner=True, critique=critique)


def operator_step(*, force: bool = False) -> dict[str, Any]:
    from intel.operator_doc import (
        append_doc,
        extract_latest_user_message,
        read_doc,
        _load_state,
        _save_state,
    )

    text, backend = read_doc()
    user = extract_latest_user_message(text)
    st = _load_state()
    if not user and not force:
        return {"ok": True, "skipped": True, "reason": "no_new_user_message", "backend": backend}

    uh = hashlib.sha256((user or force and "force" or "").encode()).hexdigest()[:16]
    if user and uh == st.get("last_user_hash") and not force:
        return {"ok": True, "skipped": True, "reason": "already_replied_hash", "backend": backend}

    reply_body = build_reply(user or "(forced status ping)", backend=backend)
    ai_block = f"AI: {reply_body}\n"
    used = append_doc(ai_block, backend=backend)
    st["last_user_hash"] = uh
    st["last_reply_ts"] = _now()
    st["backend"] = used
    _save_state(st)
    return {"ok": True, "backend": used, "user": (user or "")[:200], "replied": True}


def main() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env", override=False)
    except Exception:
        pass

    once = "--once" in sys.argv
    force = "--force" in sys.argv
    poll = int(os.getenv("OPERATOR_DOC_POLL_SEC", "45"))

    if once:
        out = operator_step(force=force)
        print(out, flush=True)
        return 0 if out.get("ok") else 1

    print(
        f"[operator-doc] poll={poll}s doc={os.getenv('OPERATOR_DOC_ID', 'default')} "
        f"persona=honest math_pivot={os.getenv('PURE_MATH_PIVOT', 'true')}",
        flush=True,
    )
    # Startup: introduce ourselves once if chat empty-ish
    try:
        from intel.operator_doc import ensure_local_chat, google_docs_available

        ensure_local_chat()
        ok, reason = google_docs_available()
        print(f"[operator-doc] google={'live' if ok else 'needs_auth:' + reason}", flush=True)
    except Exception as e:
        print(f"[operator-doc] init warn: {e}", flush=True)

    while True:
        try:
            out = operator_step(force=False)
            if out.get("replied"):
                print(
                    f"[operator-doc] replied via {out.get('backend')} user={out.get('user')!r}",
                    flush=True,
                )
            else:
                print(f"[operator-doc] idle: {out.get('reason')} backend={out.get('backend')}", flush=True)
        except Exception as e:
            print(f"[operator-doc] error: {e}", flush=True)
        time.sleep(poll)


if __name__ == "__main__":
    raise SystemExit(main())
