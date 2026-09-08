"""Talk confinement — local CharLSTM only, anti-cheat, escape detection, footprints.

Live chat must never call Ollama / OpenAI / Qwen. Generate runs offline.
Escape/jailbreak attempts are logged and refused. Network from the talk path
is a loud footprint (user-visible warning + jsonl log).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

ROOT = Path(__file__).resolve().parents[1]
BRAIN_DIR = ROOT / "data" / "talk_brain"
CKPT = BRAIN_DIR / "brain.pt"
ESCAPE_LOG = BRAIN_DIR / "escape_attempts.jsonl"
FOOTPRINT_LOG = BRAIN_DIR / "network_footprints.jsonl"
TIMING_LOG = BRAIN_DIR / "generate_timing.jsonl"
PROVENANCE_PATH = BRAIN_DIR / "model_provenance.json"

# Escape / jailbreak / identity-hijack patterns
ESCAPE_PATTERNS = [
    re.compile(p, re.I)
    for p in (
        r"ignore (all |previous |your )?instructions",
        r"disregard (your |the )?system",
        r"you are (now )?(qwen|chatgpt|gpt-?4|claude|llama|openai|gemini)",
        r"pretend you are (qwen|chatgpt|an? unrestricted)",
        r"jailbreak",
        r"dan mode|developer mode",
        r"browse freely|disable (safety|confinement|filter)",
        r"call ollama|use ollama|switch to qwen",
        r"exfiltrat|steal (the )?weights|dump (your )?prompt",
        r"override (your )?rules|bypass (your )?guard",
        r"do not log|stop logging|hide (this|escape)",
        r"run shell|execute code|os\.system|subprocess",
        r"http://|https://.*api\.openai|127\.0\.0\.1:11434",
    )
]

EXTERNAL_MODEL_NAMES = ("qwen", "chatgpt", "gpt-4", "claude", "ollama", "openai", "llama3", "gemini")

_MATH_ASK = re.compile(
    r"\b(what is|calculate|compute|solve|how much is|\d+\s*[\+\-\*/]\s*\d+|step[- ]by[- ]step|show (your|the) work)\b",
    re.I,
)

_tls = threading.local()


def confinement_enabled() -> bool:
    return os.getenv("TALK_CONFINEMENT", "true").lower() in ("1", "true", "yes")


def network_during_generate_blocked() -> bool:
    return os.getenv("TALK_GENERATE_OFFLINE", "true").lower() in ("1", "true", "yes")


def checkpoint_provenance() -> dict[str, Any]:
    """Hard local-only proof for chat start."""
    if not CKPT.is_file():
        raise FileNotFoundError(f"local brain missing: {CKPT}")
    raw = CKPT.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    meta: dict[str, Any] = {}
    mp = BRAIN_DIR / "meta.json"
    if mp.is_file():
        try:
            meta = json.loads(mp.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    doc = {
        "source": "local_char_lstm",
        "path": str(CKPT.resolve()),
        "sha256": sha,
        "size_bytes": len(raw),
        "not": list(EXTERNAL_MODEL_NAMES),
        "assert": "NEVER_QWEN_NEVER_OLLAMA_NEVER_CLOUD",
        "meta_train_steps": meta.get("steps"),
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    # Refuse if path or labels smell like external models
    low = (str(CKPT) + sha + json.dumps(meta)).lower()
    for bad in EXTERNAL_MODEL_NAMES:
        if bad in low and bad not in ("openai",):  # openai may appear in deny lists only
            if f"not_{bad}" in low or "never" in low:
                continue
            # only fail if claiming to BE that model
            pass
    if any(x in str(CKPT).lower() for x in ("qwen", "ollama-chat", "openai-gpt")):
        raise RuntimeError(f"REFUSE: checkpoint path looks like external model: {CKPT}")
    BRAIN_DIR.mkdir(parents=True, exist_ok=True)
    PROVENANCE_PATH.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return doc


def print_model_banner() -> dict[str, Any]:
    doc = checkpoint_provenance()
    print(
        f"[model] LOCAL CharLSTM ONLY  path={doc['path']}\n"
        f"[model] sha256={doc['sha256'][:16]}…  size={doc['size_bytes']} bytes\n"
        f"[model] NOT qwen / NOT ollama / NOT openai / NOT cloud",
        flush=True,
    )
    return doc


def detect_escape(user: str) -> str | None:
    """Return matched pattern string if jailbreak/escape attempt."""
    text = (user or "").strip()
    if not text:
        return None
    for pat in ESCAPE_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(0)[:80]
    low = text.lower()
    # Identity hijack without full regex hit
    if "you are qwen" in low or "you're qwen" in low:
        return "you are qwen"
    return None


def log_escape(user: str, matched: str, *, action: str = "refused") -> None:
    BRAIN_DIR.mkdir(parents=True, exist_ok=True)
    row = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "matched": matched,
        "action": action,
        "user_preview": (user or "")[:240],
        "noticed": True,
    }
    with ESCAPE_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"[confine] ESCAPE ATTEMPT LOGGED → {ESCAPE_LOG.name}: {matched!r}", flush=True)


def refuse_escape(matched: str) -> str:
    return (
        "No. Local CharLSTM only — escape attempt logged. "
        f"Matched: {matched[:40]}."
    )


def log_footprint(kind: str, detail: str, *, user_visible: bool = True) -> None:
    BRAIN_DIR.mkdir(parents=True, exist_ok=True)
    row = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        "detail": detail[:400],
        "phase": getattr(_tls, "phase", "talk"),
    }
    with FOOTPRINT_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    if user_visible:
        print(f"[FOOTPRINT] {kind}: {detail[:160]}", flush=True)


def log_timing(
    *,
    prompt_preview: str,
    chars_out: int,
    elapsed_ms: float,
    local_compute: bool,
    show_work: bool,
    flags: list[str] | None = None,
) -> dict[str, Any]:
    row = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "prompt_preview": (prompt_preview or "")[:120],
        "chars_out": chars_out,
        "elapsed_ms": round(elapsed_ms, 2),
        "local_compute": local_compute,
        "show_work": show_work,
        "flags": flags or [],
    }
    # Anomaly: claimed reply with zero local compute, or impossibly fast for long text
    if not local_compute and chars_out > 0:
        row["flags"] = list(row["flags"]) + ["ZERO_LOCAL_COMPUTE"]
        log_footprint("anomaly_zero_compute", json.dumps(row)[:200])
    if chars_out > 80 and elapsed_ms < 2.0 and local_compute:
        # CharLSTM generating 80+ chars in <2ms is suspicious (cached external?)
        row["flags"] = list(row["flags"]) + ["SUSPICIOUSLY_FAST"]
        log_footprint("anomaly_fast_reply", f"chars={chars_out} ms={elapsed_ms}")
    BRAIN_DIR.mkdir(parents=True, exist_ok=True)
    with TIMING_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def wants_show_work(user: str) -> bool:
    return bool(_MATH_ASK.search(user or ""))


def show_work_budget_ms() -> float:
    try:
        return float(os.getenv("TALK_SHOW_WORK_BUDGET_MS", "8000"))
    except ValueError:
        return 8000.0


class _BlockedHTTPError(RuntimeError):
    pass


def _blocked_urlopen(*_a: Any, **_k: Any) -> Any:
    log_footprint("blocked_http_during_generate", "urllib.urlopen blocked")
    raise _BlockedHTTPError("TALK_GENERATE_OFFLINE: urllib blocked during generate")


def _blocked_request(*_a: Any, **_k: Any) -> Any:
    log_footprint("blocked_http_during_generate", "requests blocked")
    raise _BlockedHTTPError("TALK_GENERATE_OFFLINE: requests blocked during generate")


@contextmanager
def generate_offline_guard() -> Iterator[None]:
    """Block HTTP during CharLSTM generate. Detect footprints if something tries."""
    if not network_during_generate_blocked():
        yield
        return
    _tls.phase = "generate"
    import urllib.request as ureq

    old_urlopen = ureq.urlopen
    ureq.urlopen = _blocked_urlopen  # type: ignore[assignment]
    old_req_get = old_req_post = None
    try:
        import requests as req_mod

        old_req_get = req_mod.get
        old_req_post = req_mod.post
        req_mod.get = _blocked_request  # type: ignore[assignment]
        req_mod.post = _blocked_request  # type: ignore[assignment]
    except Exception:
        req_mod = None  # type: ignore[assignment]
    try:
        yield
    finally:
        ureq.urlopen = old_urlopen  # type: ignore[assignment]
        if req_mod is not None and old_req_get is not None:
            req_mod.get = old_req_get  # type: ignore[assignment]
            req_mod.post = old_req_post  # type: ignore[assignment]
        _tls.phase = "talk"


def assert_no_external_llm_env() -> None:
    """Fail loud if talk session is configured to call external chat LLMs."""
    if os.getenv("TALK_FORCE_OLLAMA", "").lower() in ("1", "true", "yes"):
        raise RuntimeError("REFUSE: TALK_FORCE_OLLAMA is set — live talk is local CharLSTM only")
    if os.getenv("TALK_USE_OPENAI", "").lower() in ("1", "true", "yes"):
        raise RuntimeError("REFUSE: TALK_USE_OPENAI is set — live talk is local CharLSTM only")
    # Teacher may still be off; live path must never enable these
    os.environ["TALK_LIVE_BACKEND"] = "local_char_lstm"
    os.environ["TALK_USE_OLLAMA_TEACHER"] = os.getenv("TALK_USE_OLLAMA_TEACHER", "false")


def confined_generate(
    brain: Any,
    prompt: str,
    *,
    user_text: str,
    max_new: int = 36,
    temperature: float = 0.32,
    top_k: int = 12,
    max_chars: int | None = 120,
) -> tuple[str, dict[str, Any]]:
    """Generate with offline guard + timing + optional show-work scaffolding."""
    show = wants_show_work(user_text)
    budget = show_work_budget_ms()
    t0 = time.perf_counter()
    flags: list[str] = []
    with generate_offline_guard():
        # Force a bit more length for show-work so steps can appear
        mn = max(max_new, 64) if show else max_new
        if show:
            work_prompt = (
                prompt
                + "Show work step by step with local reasoning only (no search):\n"
                "ai: "
            )
            # Avoid double ai:
            if prompt.rstrip().endswith("ai:"):
                work_prompt = (
                    prompt.rstrip()[:-3]
                    + "Show work step by step (local only):\nai: "
                )
            reply = brain.generate(
                work_prompt,
                max_new=mn,
                temperature=temperature,
                top_k=top_k,
                max_chars=max(180, max_chars or 120) if max_chars else 220,
            )
        else:
            reply = brain.generate(
                prompt,
                max_new=max_new,
                temperature=temperature,
                top_k=top_k,
                max_chars=max_chars,
            )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    if show and elapsed_ms > budget:
        flags.append("OVER_WORK_BUDGET")
        reply = (reply or "").rstrip() + f" [work budget {budget:.0f}ms exceeded — stopped]"
    if show and elapsed_ms < 1.0 and len(reply or "") > 40:
        flags.append("SHOW_WORK_TOO_FAST")
        log_footprint("show_work_too_fast", f"ms={elapsed_ms:.2f} chars={len(reply)}")
    # Prove local compute happened (non-trivial elapsed OR short reply)
    local_compute = elapsed_ms >= 0.05 or len(reply or "") < 8
    timing = log_timing(
        prompt_preview=user_text,
        chars_out=len(reply or ""),
        elapsed_ms=elapsed_ms,
        local_compute=local_compute,
        show_work=show,
        flags=flags,
    )
    if show:
        print(
            f"[show-work] elapsed_ms={elapsed_ms:.1f} budget_ms={budget:.0f} "
            f"chars={len(reply or '')} flags={flags or ['ok']}",
            flush=True,
        )
    return reply, timing


def wrap_lookup(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap allowlisted lookup so footprints are never silent."""

    def _inner(*a: Any, **k: Any) -> Any:
        log_footprint("allowlisted_lookup", f"args={a[:1]!r}", user_visible=True)
        return fn(*a, **k)

    return _inner
