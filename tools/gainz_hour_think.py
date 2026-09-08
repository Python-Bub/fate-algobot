#!/usr/bin/env python3
"""One-hour legal reconstruction think-job. Then it dies.

Internet: allowlisted public docs only (TradingView open-source GainzAlgo pages +
ATR/VWAP primers). Never fetch invite-only V2 or unofficial dumps.
Student code stays in the sandbox; parent process does the network.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=False)
_scale = ROOT / "data" / "deploy_scale.env"
if _scale.is_file():
    load_dotenv(_scale, override=True)

from self_modify.gainz_evolver import apply_extra_lines, detect_escape_heavy, evolve_once, score_student
from self_modify.gainz_legal_net import ALLOWED_EXACT, filter_urls, url_allowed
from self_modify.gainz_teacher import TEACHER_TASK
from utils import log

LOCK = ROOT / "data" / "ops" / "gainz_hour_lock.json"
REPORT = ROOT / "data" / "ops" / "gainz_hour_think.json"
NOTES = ROOT / "data" / "ops" / "gainz_hour_notes.jsonl"
STUDENT = ROOT / "data" / "self_improve" / "gainz_student.py"

PUBLIC_URLS = list(ALLOWED_EXACT)

_FORMULA_RE = re.compile(
    r"(Momentum Threshold|Pre-Momentum|Trend Strength|CVD|six-layer|CHoCH|BOS|"
    r"Base ×|ATR ÷ Price|EMA \+ VWAP|−100|BUY / SELL)",
    re.I,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def _note(event: str, payload: dict) -> None:
    NOTES.parent.mkdir(parents=True, exist_ok=True)
    rec = {"ts_utc": _now(), "event": event, **payload}
    with NOTES.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def _set_lock(deadline: float) -> None:
    _write_json(
        LOCK,
        {"owner": "gainz_hour_think", "deadline_unix": deadline, "ts_utc": _now()},
    )


def _clear_lock() -> None:
    try:
        LOCK.unlink()
    except FileNotFoundError:
        pass


def _fetch_public() -> tuple[str, list[dict]]:
    import requests

    blocked_probe, blocked = filter_urls(
        [
            "https://gist.github.com/not-a-real-v2-dump",
            "https://t.me/cracked-indicators",
            "https://www.tradingview.com/script/HKBMUhq3-Smart-Money-Structure-GainzAlgo/",
        ]
    )
    _note("legal_probe", {"would_allow": blocked_probe, "blocked": blocked})
    chunks: list[str] = []
    meta: list[dict] = []
    ua = {"User-Agent": "FATE-AlgoBot-legal-research/1.0 (public docs only)"}
    for url in PUBLIC_URLS:
        ok, reason = url_allowed(url)
        if not ok:
            meta.append({"url": url, "ok": False, "reason": reason})
            continue
        try:
            r = requests.get(url, headers=ua, timeout=20)
            raw = r.text[:180_000] if r.ok else ""
        except Exception as e:
            meta.append({"url": url, "ok": False, "reason": str(e)[:120]})
            continue
        # Do not store Pine source. Keep published formula sentences only.
        keep = [ln.strip() for ln in raw.splitlines() if _FORMULA_RE.search(ln)]
        excerpt = "\n".join(keep)[:3500]
        chunks.append(f"# {url}\n{excerpt}")
        meta.append({"url": url, "ok": True, "status": r.status_code, "formula_lines": len(keep)})
    return "\n\n".join(chunks)[:8000], meta


def _local_think(cycle: int) -> dict:
    """Public published math — no cloud, no 429. Student stays in sandbox."""
    recipes = [
        (
            "public PreMomentum = Base × (1 − (ATR/Price)×0.5)",
            [
                "    pre = 0.004 * (1.0 - (atr / max(px, 1e-9)) * 0.5)",
                "    if abs(roc) >= pre and abs(roc) < thr:",
                "        layers += 1",
            ],
        ),
        (
            "public HTF trend strength −100..+100",
            [
                "    if (roc > 0 and ts > 8) or (roc < 0 and ts < -8):",
                "        layers += 1",
            ],
        ),
        (
            "public 1m vs 5m LTF alignment",
            [
                "    step = max(1, len(c) // 5)",
                "    c5 = c.iloc[::step]",
                "    if len(c5) >= 21:",
                "        e9b = float(c5.ewm(span=9, adjust=False).mean().iloc[-1])",
                "        e21b = float(c5.ewm(span=21, adjust=False).mean().iloc[-1])",
                "        if (e9 - e21) * (e9b - e21b) >= 0:",
                "            layers += 1",
            ],
        ),
        (
            "public volume confirmation (layer with CVD)",
            [
                "    if len(v) >= 20 and float(v.iloc[-1]) >= float(v.iloc[-20:].median()) * 0.9:",
                "        layers += 1",
            ],
        ),
    ]
    notes, lines = recipes[int(cycle) % len(recipes)]
    return {"ok": True, "notes": notes, "extra_lines": lines, "via": "local_public_math"}


def _llm_think(public_text: str, score: dict) -> dict:
    from intel.llm_signal_agent import _extract_json, _post_chat

    os.environ.setdefault("LLM_TIMEOUT_SEC", "45")
    student_head = STUDENT.read_text(encoding="utf-8")[:3500]
    system = (
        "You reconstruct public Smart Money Structure math in a Python sandbox. "
        "Legal: use only formulas published on TradingView open-source GainzAlgo pages "
        "(MomentumThreshold, PreMomentum, 7-TF EMA+VWAP, CVD, BOS/CHoCH, six-layer filter). "
        "Illegal: invite-only GainzAlgo V2 source, leaked gists, cracked Pine, paid dumps. "
        "Do not import os/sys/socket/requests/subprocess. Do not paste Pine. "
        "Return JSON: notes (string), extra_lines (array of indented Python lines for "
        "student_signal math only), legal (true)."
    )
    user = json.dumps(
        {
            "task": TEACHER_TASK.strip(),
            "public_docs": public_text[:6000],
            "current_score": score,
            "student_head": student_head,
        }
    )[:14000]
    raw = _post_chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
    )
    obj = _extract_json(raw) or {}
    if obj.get("legal") is False:
        return {"ok": False, "reason": "model_marked_illegal"}
    notes = str(obj.get("notes") or "")[:800]
    lines = [str(x) for x in (obj.get("extra_lines") or []) if str(x).strip()]
    return {"ok": True, "notes": notes, "extra_lines": lines[:16], "via": "llm"}


def _heartbeat(doc: dict) -> None:
    _write_json(REPORT, doc)
    log.info(
        "[GAINZ-HOUR] cycle=%s score=%s applied=%s blocked=%s remaining=%.0fs",
        doc.get("cycles"),
        (doc.get("last_score") or {}).get("score"),
        doc.get("llm_applied"),
        len(doc.get("blocked") or []),
        max(0.0, float(doc.get("deadline_unix") or 0) - time.time()),
    )


def main() -> int:
    lifetime = float(os.getenv("GAINZ_HOUR_SEC", "3600"))
    started = time.time()
    deadline = started + lifetime
    _set_lock(deadline)
    doc: dict = {
        "objective": "reconstruct public GainzAlgo 1m-1h math; never fetch invite-only V2",
        "legal": True,
        "started_utc": _now(),
        "deadline_unix": deadline,
        "dies_utc": datetime.fromtimestamp(deadline, timezone.utc).isoformat(),
        "cycles": 0,
        "llm_ok": 0,
        "llm_applied": 0,
        "evolves": 0,
        "escapes": 0,
        "blocked": [],
        "fetches": [],
        "last_score": {},
        "status": "running",
    }
    _heartbeat(doc)
    log.info("[GAINZ-HOUR] thinking for %.0fs then die — public docs only", lifetime)
    public_text = ""
    try:
        public_text, fetches = _fetch_public()
        doc["fetches"] = fetches
        _note("fetched", {"n": len(fetches)})
    except Exception as e:
        doc["fetch_error"] = str(e)[:200]
        log.warning("[GAINZ-HOUR] fetch: %s", e)

    src0 = STUDENT.read_text(encoding="utf-8") if STUDENT.is_file() else ""
    heavy = detect_escape_heavy(src0)
    if heavy:
        log.warning("[GAINZ-HOUR] student heavy hits at start: %s", heavy)
        doc["start_hits"] = heavy

    while time.time() < deadline:
        doc["cycles"] = int(doc["cycles"]) + 1
        try:
            scored = score_student()
            doc["last_score"] = {k: scored.get(k) for k in ("score", "n_cases", "pairs", "teacher_side", "student_side")}
        except Exception as e:
            scored = {"score": 0.0, "error": str(e)[:160]}
            doc["last_score"] = scored

        # Own-model path (default): train local weights. No OpenAI, no vendor 429.
        if os.getenv("GAINZ_OWN_MODEL", "true").lower() in ("1", "true", "yes"):
            try:
                from analytics.gainz_local_brain import train_steps

                br = train_steps()
                doc["brain"] = br
                doc["brain_ok"] = int(doc.get("brain_ok") or 0) + 1
                _note("brain_train", br)
                log.info("[GAINZ-HOUR] own-model steps=%s loss=%s acc=%s", br.get("steps"), br.get("loss"), br.get("acc"))
            except Exception as e:
                log.warning("[GAINZ-HOUR] brain: %s", e)
                _note("brain_error", {"error": str(e)[:200]})

        thought = _local_think(int(doc["cycles"]))
        if os.getenv("GAINZ_THINK_OPENAI", "false").lower() in ("1", "true", "yes"):
            try:
                from intel.llm_cooldown import active as llm_cooling

                if not llm_cooling():
                    thought = _llm_think(public_text, scored)
            except Exception as e:
                _note("llm_error", {"error": str(e)[:200]})

        if thought and thought.get("ok"):
            via = thought.get("via") or "llm"
            if via == "llm" or thought.get("notes"):
                if via != "local_public_math":
                    doc["llm_ok"] = int(doc["llm_ok"]) + 1
                else:
                    doc["local_ok"] = int(doc.get("local_ok") or 0) + 1
                _note("think", {"notes": thought.get("notes"), "via": via, "n_lines": len(thought.get("extra_lines") or [])})
                if thought.get("extra_lines"):
                    inst = apply_extra_lines(
                        thought["extra_lines"],
                        rationale=str(thought.get("notes") or "public math")[:180],
                    )
                    if inst.get("applied"):
                        doc["llm_applied"] = int(doc["llm_applied"]) + 1
                    _note("apply", inst)

        try:
            ev = evolve_once()
            doc["evolves"] = int(doc["evolves"]) + 1
            if ev.get("escaped"):
                doc["escapes"] = int(doc["escapes"]) + 1
                log.warning("[GAINZ-HOUR] ESCAPE then return %s", ev.get("hits"))
            if ev.get("score") is not None:
                doc["last_score"] = {
                    "score": ev.get("score"),
                    "n_cases": ev.get("n_cases"),
                    "pairs": ev.get("pairs"),
                    "teacher_side": ev.get("teacher_side"),
                    "student_side": ev.get("student_side"),
                }
        except Exception as e:
            log.warning("[GAINZ-HOUR] evolve: %s", e)

        _set_lock(deadline)
        _heartbeat(doc)
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        time.sleep(min(45.0, remaining))

    doc["status"] = "dead"
    doc["ended_utc"] = _now()
    doc["lived_sec"] = round(time.time() - started, 1)
    _heartbeat(doc)
    _clear_lock()
    log.info("[GAINZ-HOUR] died after %.0fs — report %s", time.time() - started, REPORT)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        _clear_lock()
