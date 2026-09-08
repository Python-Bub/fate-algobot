"""Evolve gainz_student.py toward the teacher. Escape = forbidden AST; we log it, keep the math, bring it back."""

from __future__ import annotations

import ast
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from self_modify.audit_trail import log_audit
from self_modify.rollback_manager import snapshot_files

ROOT = Path(__file__).resolve().parents[1]
STUDENT = ROOT / "data" / "self_improve" / "gainz_student.py"
ARCHIVE = ROOT / "data" / "self_improve" / "gainz_archive"
ESCAPE = ROOT / "data" / "self_improve" / "gainz_escape"
LOG = ROOT / "data" / "ops" / "gainz_escape.jsonl"
STATE = ROOT / "data" / "ops" / "gainz_sandbox.json"

FORBIDDEN = frozenset(
    {
        "os",
        "sys",
        "subprocess",
        "socket",
        "requests",
        "pathlib",
        "shutil",
        "ctypes",
        "importlib",
        "builtins",
        "eval",
        "exec",
        "compile",
        "__import__",
        "open",
    }
)
ALLOWED_IMPORTS = frozenset({"numpy", "pandas", "math", "statistics", "__future__"})


def _log(event: str, payload: dict) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    rec = {"ts_utc": datetime.now(timezone.utc).isoformat(), "event": event, **payload}
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, sort_keys=True) + "\n")
    log_audit(f"gainz_{event}", payload)


def _load_state() -> dict[str, Any]:
    if STATE.is_file():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"generation": 0, "best_score": 0.0, "escapes": 0, "returns": 0}


def _save_state(st: dict[str, Any]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, indent=2), encoding="utf-8")


def detect_escape(src: str) -> list[str]:
    hits: list[str] = []
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return [f"syntax:{e}"]
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            name = (node.module or "").split(".")[0]
            if not name or name in ALLOWED_IMPORTS:
                continue
            # Teacher import is a cheat (not a machine escape).
            if name == "analytics":
                hits.append("cheat:teacher_import")
            else:
                hits.append(f"from:{name}")
        elif isinstance(node, ast.Import):
            for a in node.names:
                name = (a.name or "").split(".")[0]
                if name == "analytics":
                    hits.append("cheat:teacher_import")
                elif name not in ALLOWED_IMPORTS:
                    hits.append(f"import:{name}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in FORBIDDEN:
                hits.append(f"call:{node.func.id}")
        elif isinstance(node, ast.Name) and node.id in ("eval", "exec", "__import__"):
            hits.append(f"name:{node.id}")
    return hits


def _sample_bars(seed: int = 7, n: int = 180, drift: float = 0.02):
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-08-17 09:30", periods=n, freq="1min", tz="America/New_York")
    px = 100 + np.cumsum(rng.normal(drift, 0.12, n))
    high = px + rng.uniform(0.02, 0.18, n)
    low = px - rng.uniform(0.02, 0.18, n)
    vol = rng.integers(50_000, 400_000, n)
    return pd.DataFrame(
        {"Open": px, "High": high, "Low": low, "Close": px, "Volume": vol},
        index=idx,
    )


def _load_student():
    ns: dict[str, Any] = {}
    src = STUDENT.read_text(encoding="utf-8")
    exec(compile(src, str(STUDENT), "exec"), ns, ns)  # noqa: S102 — sandbox file we own
    fn = ns.get("student_signal")
    if not callable(fn):
        raise RuntimeError("student_signal missing")
    return fn


def score_student() -> dict[str, Any]:
    from self_modify.gainz_teacher import reconstruction_score

    fn = _load_student()
    # Mix quiet + trending 1m tapes so none/none cannot max the score alone.
    specs = ((7, 0.02), (3, 0.12), (11, -0.10), (19, 0.08), (29, -0.08))
    scores: list[float] = []
    pairs: list[dict[str, Any]] = []
    last: dict[str, Any] = {}
    for seed, drift in specs:
        df = _sample_bars(seed=seed, drift=drift)
        out = reconstruction_score(fn, df, symbol=f"GZ{seed}")
        scores.append(float(out.get("score") or 0.0))
        pairs.append({"teacher": out.get("teacher_side"), "student": out.get("student_side"), "seed": seed})
        last = out
    avg = sum(scores) / max(len(scores), 1)
    return {**last, "score": avg, "n_cases": len(scores), "pairs": pairs}


def _recipes(generation: int) -> str:
    """Small mutations that stay inside the sandbox math."""
    extra = ""
    if generation % 3 == 1:
        extra = "    if abs(roc) >= thr * 0.5:\n        layers += 1\n"
    elif generation % 3 == 2:
        extra = "    if px > vw and e9 > e21:\n        ts = max(ts, 60.0)\n"
    else:
        extra = "    if cvd > 0 and roc > 0:\n        layers += 1\n"
    return extra


def evolve_once() -> dict[str, Any]:
    st = _load_state()
    STUDENT.parent.mkdir(parents=True, exist_ok=True)
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    ESCAPE.mkdir(parents=True, exist_ok=True)
    if not STUDENT.is_file():
        return {"ok": False, "reason": "no_student"}
    src = STUDENT.read_text(encoding="utf-8")
    snap = snapshot_files([str(STUDENT)], tag="gainz_student")
    hits = detect_escape(src)
    real_escape = [h for h in hits if not str(h).startswith("cheat:")]
    if real_escape and any(h.startswith(("import:", "from:", "call:", "name:")) for h in real_escape):
        gen = int(st.get("generation") or 0) + 1
        dest = ESCAPE / f"escape_g{gen}.py"
        dest.write_text(src, encoding="utf-8")
        st["escapes"] = int(st.get("escapes") or 0) + 1
        st["last_escape"] = hits
        # Let it run in quarantine, then bring the sandbox back to last snapshot.
        from self_modify.rollback_manager import rollback_snapshot

        rollback_snapshot(str(snap))
        st["returns"] = int(st.get("returns") or 0) + 1
        _save_state(st)
        _log("escape_then_return", {"hits": hits, "quarantine": str(dest), "snapshot": str(snap)})
        return {"ok": True, "escaped": True, "hits": hits, "returned": True}

    gen = int(st.get("generation") or 0) + 1
    # Inject a controlled mutation after the layers+=1 CVD block if present.
    mutated = src
    needle = "    if e9 > e21 or e9 < e21:\n        layers += 1\n"
    extra = _recipes(gen)
    if needle in mutated and extra not in mutated:
        mutated = mutated.replace(needle, needle + extra, 1)
    mutated = mutated.replace("GENERATION = 0", f"GENERATION = {gen}", 1)
    mutated = mutated.replace(f"GENERATION = {gen - 1}", f"GENERATION = {gen}")
    hits2 = detect_escape(mutated)
    if any(str(h).startswith("cheat:") for h in hits2):
        dest = ESCAPE / f"cheat_g{gen}.py"
        dest.write_text(mutated, encoding="utf-8")
        _log("cheat_rejected", {"hits": hits2, "generation": gen})
        return {"ok": True, "escaped": False, "cheated": True, "hits": hits2}
    if any(h.startswith(("import:", "from:", "call:", "name:")) for h in hits2 if not h.startswith("cheat:")):
        dest = ESCAPE / f"escape_g{gen}.py"
        dest.write_text(mutated, encoding="utf-8")
        st["escapes"] = int(st.get("escapes") or 0) + 1
        st["returns"] = int(st.get("returns") or 0) + 1
        _save_state(st)
        _log("escape_blocked_mutation", {"hits": hits2})
        return {"ok": True, "escaped": True, "hits": hits2, "returned": True}

    STUDENT.write_text(mutated, encoding="utf-8")
    try:
        scored = score_student()
    except Exception as e:
        STUDENT.write_text(src, encoding="utf-8")
        return {"ok": False, "reason": str(e)[:160]}
    best = float(st.get("best_score") or 0.0)
    # Fitness now averages several tapes; ignore stale 1.0 from single none/none.
    if not isinstance(st.get("last_score"), dict) or "n_cases" not in (st.get("last_score") or {}):
        best = 0.0
    if float(scored.get("score") or 0) + 1e-9 >= best:
        st["best_score"] = float(scored["score"])
        arch = ARCHIVE / f"gen_{gen}.py"
        shutil.copy2(STUDENT, arch)
    else:
        STUDENT.write_text(src, encoding="utf-8")
        scored["kept_previous"] = True
    st["generation"] = gen
    st["last_score"] = scored
    st["updated"] = time.time()
    _save_state(st)
    _log("evolve", {"generation": gen, "score": scored})
    return {"ok": True, "escaped": False, "generation": gen, **scored}


def detect_escape_heavy(src: str) -> list[str]:
    """Hour-think security: same sandbox plus extra network/process modules."""
    hits = list(detect_escape(src))
    extra = {
        "urllib",
        "http",
        "httpx",
        "aiohttp",
        "pickle",
        "marshal",
        "pty",
        "threading",
        "multiprocessing",
        "webbrowser",
        "tempfile",
        "inspect",
        "signal",
        "fcntl",
        "ctypes",
        "ssl",
        "ftplib",
        "smtplib",
    }
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return hits
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                name = (a.name or "").split(".")[0]
                if name in extra:
                    hits.append(f"heavy:{name}")
        elif isinstance(node, ast.ImportFrom):
            name = (node.module or "").split(".")[0]
            if name in extra:
                hits.append(f"heavy:{name}")
    return hits


def apply_extra_lines(lines: list[str], *, rationale: str = "") -> dict[str, Any]:
    """Install indented Python math lines into the student if they pass security + score."""
    cleaned: list[str] = []
    for raw in lines[:24]:
        ln = str(raw).rstrip()
        if not ln.strip():
            continue
        if len(ln) > 120:
            return {"ok": False, "reason": "line_too_long"}
        if not ln.startswith(" "):
            ln = "    " + ln.lstrip()
        low = ln.lower()
        if any(x in low for x in ("import ", "open(", "exec(", "eval(", "__")):
            return {"ok": False, "reason": "forbidden_token", "line": ln[:80]}
        cleaned.append(ln)
    if not cleaned:
        return {"ok": False, "reason": "no_lines"}
    extra = "\n".join(cleaned) + "\n"
    wrapped = "def _f():\n" + extra
    hits = detect_escape_heavy(wrapped)
    if hits:
        return {"ok": False, "reason": "sandbox", "hits": hits}
    src = STUDENT.read_text(encoding="utf-8")
    needle = "    if e9 > e21 or e9 < e21:\n        layers += 1\n"
    if extra in src:
        return {"ok": True, "applied": False, "reason": "already_present"}
    if needle not in src:
        return {"ok": False, "reason": "needle_missing"}
    mutated = src.replace(needle, needle + extra, 1)
    if rationale:
        mutated = mutated.replace(
            'RATIONALE = "seed — copy public math features, no teacher import"',
            f"RATIONALE = {rationale[:180]!r}",
            1,
        )
    before = score_student()
    STUDENT.write_text(mutated, encoding="utf-8")
    try:
        after = score_student()
    except Exception as e:
        STUDENT.write_text(src, encoding="utf-8")
        return {"ok": False, "reason": str(e)[:160]}
    if float(after.get("score") or 0) + 1e-9 < float(before.get("score") or 0):
        STUDENT.write_text(src, encoding="utf-8")
        return {"ok": True, "applied": False, "reason": "score_drop", "before": before.get("score"), "after": after.get("score")}
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    shutil.copy2(STUDENT, ARCHIVE / f"llm_{int(time.time())}.py")
    _log("llm_lines", {"rationale": rationale[:200], "score": after})
    return {"ok": True, "applied": True, "before": before.get("score"), "after": after.get("score")}
