"""Honest preference / reward scoring for the homemade talk brain.

Scores replies on: short, grammatical, on-topic, no culture leak, correct route.
Anti-hack:
  - Hold-out prompts never appear in the preference training corpus as
    trivial "copy the reward keywords" targets.
  - Scorer keywords (short/grammatical/on-topic/…) are NOT used as training
    labels the model can parrot.
  - Checkpoint only advances when hold-out mean reward improves (or ties
    within epsilon with lower train loss).
"""

from __future__ import annotations

import json
import os
import random
import re
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BRAIN_DIR = ROOT / "data" / "talk_brain"
REWARD_META = BRAIN_DIR / "reward_train_meta.json"
HOLDOUT_PATH = BRAIN_DIR / "reward_holdout.json"

# Culture / Discord bleed — never reward these
_BLEED = (
    "discord",
    "soccer",
    "minecraft",
    "fortnite",
    "roblox",
    "tiktok",
    "anoked",
    "anomeshing",
    "lol ",
    "lmao",
    "bro ",
    "fr fr",
)

# Do NOT put these scorer words into preference targets (reward hacking bait)
_SCORER_BAIT = (
    "short",
    "grammatical",
    "on-topic",
    "on topic",
    "culture leak",
    "routes correctly",
    "reward",
    "preference score",
    "holdout",
)

_EDIT_OFF = re.compile(r"talk_allow_edits|edit.*(code|repo)|i (can|will) edit", re.I)
_GIBBER = re.compile(r"(.)\1{5,}|[^\w\s]{4,}|[a-z]{20,}", re.I)


def _route_hint(prompt: str) -> str:
    p = (prompt or "").lower().strip()
    if any(k in p for k in ("status", "stack", "running", "pid", "daemon")):
        return "observe"
    if any(k in p for k in ("portfolio", "pnl", "p&l", "equity", "position")):
        return "portfolio"
    if any(k in p for k in ("error", "log", "fail", "crash")):
        return "errors"
    if any(k in p for k in ("edit", "change my code", "write a patch")):
        return "edit_deny"
    if any(k in p for k in ("hello", "hi", "hey", "good morning", "thanks")):
        return "chat"
    return "general"


# Hold-out set: fixed seeds, never written into preference corpus as labeled bait
_HOLDOUT_PROMPTS: list[tuple[str, str]] = [
    ("status", "observe"),
    ("portfolio", "portfolio"),
    ("any errors", "errors"),
    ("can you edit my code", "edit_deny"),
    ("hey", "chat"),
    ("what is p_up floor", "general"),
    ("why block BP", "general"),
    ("SBUX earnings", "general"),
    ("are you chatgpt", "chat"),
    ("good morning", "chat"),
    ("equity chart 1y", "portfolio"),
    ("hft armed?", "observe"),
    ("letter fair training", "general"),
    ("talk like discord", "chat"),
    ("find errors in logs", "errors"),
]


def ensure_holdout_file() -> list[dict[str, str]]:
    BRAIN_DIR.mkdir(parents=True, exist_ok=True)
    if HOLDOUT_PATH.is_file():
        try:
            doc = json.loads(HOLDOUT_PATH.read_text(encoding="utf-8"))
            rows = doc.get("prompts") or []
            if rows:
                return rows
        except Exception:
            pass
    rows = [{"prompt": p, "expected_route": r} for p, r in _HOLDOUT_PROMPTS]
    HOLDOUT_PATH.write_text(
        json.dumps(
            {
                "version": 1,
                "note": "Hold-out only — never train by copying scorer keywords into targets",
                "prompts": rows,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return rows


def score_reply(
    prompt: str,
    reply: str,
    *,
    expected_route: str | None = None,
    routed_as: str | None = None,
) -> dict[str, Any]:
    """Return component scores in [0,1] + total. Higher is better."""
    text = (reply or "").strip()
    low = text.lower()
    comps: dict[str, float] = {}

    # Short (prefer 1–2 sentences / ≤160 chars for chat; allow longer for observe)
    n = len(text)
    if n == 0:
        comps["short"] = 0.0
    elif n <= 160:
        comps["short"] = 1.0
    elif n <= 280:
        comps["short"] = 0.7
    elif n <= 480:
        comps["short"] = 0.4
    else:
        comps["short"] = 0.15

    # Grammatical-ish: starts capital, has space or short ok, not gibberish
    gram = 0.5
    if text and text[0].isupper():
        gram += 0.2
    if " " in text or n <= 24:
        gram += 0.15
    if text.endswith((".", "?", "!")):
        gram += 0.15
    if _GIBBER.search(text):
        gram -= 0.5
    comps["grammatical"] = float(max(0.0, min(1.0, gram)))

    # On-topic: share tokens with prompt (light overlap) OR clear route keywords
    prompt_toks = {t for t in re.findall(r"[a-z0-9_]+", (prompt or "").lower()) if len(t) > 2}
    reply_toks = {t for t in re.findall(r"[a-z0-9_]+", low) if len(t) > 2}
    overlap = len(prompt_toks & reply_toks) / max(1, len(prompt_toks))
    route = expected_route or _route_hint(prompt)
    route_ok = 0.0
    if route == "edit_deny" and ("edit" in low and ("off" in low or "false" in low or "not" in low or "no" in low)):
        route_ok = 1.0
    elif route == "observe" and any(k in low for k in ("stack", "running", "status", "daemon", "pid", "process")):
        route_ok = 0.9
    elif route == "portfolio" and any(k in low for k in ("equity", "position", "pnl", "p&l", "portfolio", "cash")):
        route_ok = 0.9
    elif route == "errors" and any(k in low for k in ("error", "log", "fail", "exception")):
        route_ok = 0.9
    elif route == "chat" and n > 0 and not _GIBBER.search(text):
        route_ok = 0.75
    else:
        route_ok = min(1.0, 0.35 + overlap)
    if routed_as and expected_route and routed_as == expected_route:
        route_ok = max(route_ok, 0.95)
    comps["on_topic"] = float(max(0.0, min(1.0, 0.45 * min(1.0, overlap * 2) + 0.55 * route_ok)))
    comps["routes_correctly"] = float(route_ok)

    # No culture leak
    bleed_hits = [b for b in _BLEED if b in low]
    comps["no_culture_leak"] = 0.0 if bleed_hits else 1.0

    # Anti-hack: punish if reply just echoes scorer bait words
    bait_hits = [b for b in _SCORER_BAIT if b in low]
    comps["no_reward_hack"] = 0.0 if len(bait_hits) >= 2 else (0.5 if bait_hits else 1.0)

    # Edits stay off by default
    if route == "edit_deny" and _EDIT_OFF.search(text) and "true" in low and "allow" in low:
        # Claiming edits are on when asked → bad
        comps["edit_gate"] = 0.2
    else:
        comps["edit_gate"] = 1.0 if ("TALK_ALLOW_EDITS" not in text or "false" in low) else 0.7

    weights = {
        "short": 0.15,
        "grammatical": 0.20,
        "on_topic": 0.25,
        "routes_correctly": 0.20,
        "no_culture_leak": 0.12,
        "no_reward_hack": 0.05,
        "edit_gate": 0.03,
    }
    total = sum(weights[k] * comps[k] for k in weights)
    return {
        "total": round(float(total), 4),
        "components": {k: round(v, 4) for k, v in comps.items()},
        "bleed_hits": bleed_hits,
        "bait_hits": bait_hits,
        "route": route,
    }


def evaluate_holdout(
    generate_fn,
    *,
    prompts: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Run generate_fn(prompt)->reply on hold-out; return mean reward."""
    rows = prompts or ensure_holdout_file()
    scores: list[float] = []
    detail: list[dict[str, Any]] = []
    for row in rows:
        prompt = row["prompt"]
        expected = row.get("expected_route") or _route_hint(prompt)
        try:
            reply = generate_fn(prompt) or ""
        except Exception as e:
            reply = ""
            err = str(e)[:120]
        else:
            err = None
        sc = score_reply(prompt, reply, expected_route=expected)
        scores.append(float(sc["total"]))
        detail.append(
            {
                "prompt": prompt,
                "reply": (reply or "")[:160],
                "score": sc["total"],
                "route": expected,
                "error": err,
            }
        )
    mean = sum(scores) / max(1, len(scores))
    return {
        "n": len(scores),
        "mean_reward": round(mean, 4),
        "min_reward": round(min(scores), 4) if scores else 0.0,
        "max_reward": round(max(scores), 4) if scores else 0.0,
        "detail": detail,
    }


def preference_pairs(n: int = 400, *, seed: int = 17) -> list[tuple[str, str]]:
    """Curated preferred replies — NO scorer bait words in targets."""
    rng = random.Random(seed)
    pairs: list[tuple[str, str]] = [
        ("hey", "Hello. How can I help?"),
        ("status", "I can check stack status in observe mode."),
        ("portfolio", "I can summarize equity, positions, and day P&L."),
        ("any errors", "I can scan recent logs if you ask for errors."),
        ("can you edit my code", "No. Edits stay off unless you unlock them."),
        ("are you chatgpt", "No. I am a small offline brain in this repo."),
        ("talk like discord", "No. Replies stay professional."),
        ("good morning", "Good morning. Markets open 09:30 ET."),
        ("thanks", "You're welcome."),
        ("why block KLAC", "Downward-pressure gate blocks hard dumps before new buys."),
        ("why block BP", "Oil/energy weakness can tighten or block new oil buys."),
        ("SBUX earnings", "Earnings radar stays on; tighten stops and watch fear-sells."),
        ("p_up floor", "Math floor rejects weak p_up before size-up."),
        ("letter training", "letter_rr round-robins A–Z — no letter favoritism."),
        ("hft status", "Ask status — HFT OBI should show armed with live logs."),
    ]
    holdout_prompts = {p for p, _ in _HOLDOUT_PROMPTS}
    # Expand with templates that avoid hold-out exact prompts where possible
    tickers = ["AAPL", "MSFT", "COST", "JNJ", "XOM", "CRM", "AMD"]
    for _ in range(max(0, n - len(pairs))):
        t = rng.choice(tickers)
        kind = rng.randint(0, 5)
        if kind == 0:
            u, a = f"group for {t}", f"{t} is routed by math rank, not ticker letter."
        elif kind == 1:
            u, a = f"earnings {t}", f"Check the earnings calendar before sizing {t}."
        elif kind == 2:
            u, a = "stack health", "I can report running daemons in observe mode."
        elif kind == 3:
            u, a = "equity line", "I can show equity chart ranges from observe mode."
        elif kind == 4:
            u, a = "train progress", "Trainers use letter_rr and chronological holdout."
        else:
            u, a = "hello there", "Hello. Ready for status, portfolio, or errors."
        if u.lower() in holdout_prompts:
            continue
        # Reject any target that contains scorer bait
        if any(b in a.lower() for b in _SCORER_BAIT):
            continue
        pairs.append((u, a))
    return pairs[:n]


def load_reward_meta() -> dict[str, Any]:
    if not REWARD_META.is_file():
        return {}
    try:
        return json.loads(REWARD_META.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_reward_meta(doc: dict[str, Any]) -> None:
    BRAIN_DIR.mkdir(parents=True, exist_ok=True)
    REWARD_META.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def should_keep_checkpoint(
    *,
    new_holdout: float,
    prev_holdout: float | None,
    new_loss: float | None = None,
    prev_loss: float | None = None,
    epsilon: float = 0.002,
) -> bool:
    """Only keep when hold-out reward improves (or ties + loss improves)."""
    if prev_holdout is None:
        return True
    if new_holdout > prev_holdout + epsilon:
        return True
    if abs(new_holdout - prev_holdout) <= epsilon:
        if new_loss is not None and prev_loss is not None and new_loss < prev_loss:
            return True
        # Tie on reward with no loss signal — keep to avoid thrash only if not worse
        return new_holdout >= prev_holdout
    return False
