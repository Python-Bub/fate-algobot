#!/usr/bin/env python3
"""Generate a high-quality dialogue teacher corpus for the homemade talk brain.

Prefers local Ollama chat models if they respond quickly. Skips hung coder-only
models. Always expands a large curated + templated professional operator pack
(portfolio, stack, typos, P&L, errors, greetings). CharLSTM will not match a
frontier LLM — this only improves the training distribution.
"""

from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

OUT = ROOT / "data" / "talk_brain" / "teacher_corpus.txt"
META = ROOT / "data" / "talk_brain" / "teacher_fetch.json"

# Strong curated pairs always included (offline, professional).
CURATED = [
    ("hey", "Hello. How can I help?"),
    ("hi", "Hi. What do you need?"),
    ("hello", "Hello. Ready when you are."),
    ("you too", "You as well."),
    ("thanks", "You're welcome."),
    ("thank you", "You're welcome."),
    ("excuse me", "Yes — go ahead."),
    ("what do you mean", "Which part should I clarify?"),
    ("can you see my code", "Yes — read-only observe mode. I can summarize the repo without editing."),
    ("are you chatgpt", "No. I am a small offline brain trained in this repo."),
    ("be honest", "Always. I will not overstate what I can do."),
    ("status", "I can check stack status in observe mode if you ask."),
    ("do you edit code", "Not unless TALK_ALLOW_EDITS is on. Edits are off by default."),
    ("how smart are you", "I am a compact local model. Useful for ops chat; not a frontier LLM."),
    ("portfolio", "I can summarize equity, positions, and day P&L from observe mode."),
    ("pnl", "Ask for portfolio or equity and I will report what the stack sees."),
    ("are we making money", "I can read the latest equity snapshot and report day P&L."),
    ("any errors", "I can scan recent logs for errors if you ask for stack status."),
    ("find errors", "Say 'status' or 'errors' and I will summarize what I can observe."),
    ("good morning", "Good morning. Markets open 09:30 ET; extended hours 04:00–20:00 ET."),
    ("good night", "Good night. Daemons stay armed if the stack is online."),
    ("bye", "Goodbye. I will be here when you return."),
    ("ok", "Understood."),
    ("okay", "Understood. What next?"),
]


def _operator_templates(rng: random.Random, n: int) -> list[tuple[str, str]]:
    """Thousands of short professional operator dialogue pairs via templates."""
    tickers = [
        "SPY", "QQQ", "IWM", "AAPL", "MSFT", "NVDA", "AMD", "TSLA", "META", "AMZN",
        "GOOGL", "AVGO", "JPM", "XOM", "LLY", "UNH", "COST", "NFLX", "CRM", "ORCL",
    ]
    procs = [
        "fortress", "HFT OBI", "day-trade", "micro-scalp", "stack-watchdog",
        "parallel_train", "pattern scan", "paper sim",
    ]
    issues = [
        "stale websocket",
        "rest poll timeout",
        "monthly drawdown halt",
        "daily loss halt",
        "buying power tight",
        "fractional exit reject",
        "missing env after deploy_scale change",
        "duplicate train worker",
    ]
    greetings = [
        ("hey", "Hello. How can I help?"),
        ("hi there", "Hi. What do you need?"),
        ("yo", "Hello. What should we check?"),
        ("sup", "Hello. Ready for status or portfolio."),
        ("how are you", "Operational. Ask for status, portfolio, or errors."),
        ("how's it going", "Steady. I can report stack health or P&L."),
    ]
    typos = [
        ("stauts", "Did you mean status? I can check the stack."),
        ("porfolio", "Did you mean portfolio? I can summarize equity and positions."),
        ("equty", "Did you mean equity? I can show the line chart range."),
        ("erors", "Did you mean errors? I can scan recent logs."),
        ("traing", "Did you mean training? I can report trainer progress."),
        ("hft?", "HFT OBI is the sub-second tape/OBI engine. Ask status for the pid."),
        ("fortres", "Did you mean fortress? That is the intraday paper deployer."),
    ]
    pairs: list[tuple[str, str]] = []
    pairs.extend(greetings)
    pairs.extend(typos)

    for _ in range(max(50, n // 8)):
        t = rng.choice(tickers)
        p = rng.choice(procs)
        issue = rng.choice(issues)
        eq = rng.randint(70_000, 95_000)
        pnl = rng.uniform(-1200, 900)
        pnl_s = f"{pnl:+.0f}"
        util = rng.randint(35, 95)
        pairs.extend(
            [
                (f"how is {t}", f"{t}: I can pull the live quote and position if held."),
                (f"did we trade {t}", f"I can check recent fills for {t} in observe mode."),
                (f"sell {t}", "I will not place orders from chat. Use the trading daemons."),
                (f"buy {t}", "Chat cannot submit orders. Fortress/HFT handle entries."),
                (f"is {p} running", f"Ask status — I will report whether {p} is alive."),
                (f"restart {p}", "I cannot restart processes from chat while edits are off."),
                (f"why no trades", f"Common causes: {issue}. Check status and latest logs."),
                ("equity", f"Latest observe snapshot often looks like equity near ${eq:,}."),
                ("day pnl", f"Day P&L is last_equity to equity; recently around {pnl_s}."),
                ("are we up", f"I can confirm from the equity snapshot. Recent day move ~{pnl_s}."),
                ("are we down", f"If day P&L is negative I will say so plainly. Recent sample {pnl_s}."),
                ("bp", f"Buying power utilization is tracked by fortress; typical util ~{util}%."),
                ("deployed", f"Gross deployment is reported in fortress logs; often near {util}% of target."),
                ("kill switch", "Risk kills stay on. Only clear false-positive halts after verifying."),
                ("monthly dd", "Monthly drawdown halt remains armed. Peak baseline is in data/risk."),
                ("market closed", "Outside 04:00–20:00 ET, daemons stay alive and armed for the next open."),
                ("when do we trade", "Orders allowed 04:00–20:00 ET Mon–Fri; RTH is 09:30–16:00 ET."),
                ("help", "Try: status, portfolio, equity, errors, or a ticker name."),
                ("what can you do", "Observe-mode ops chat: status, portfolio, clarify errors. No code edits."),
                ("who are you", "Local talk brain for this trading stack — short professional replies."),
            ]
        )
    # Dedup while preserving order-ish shuffle later
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []
    for u, a in pairs:
        key = (u.lower().strip(), a)
        if key in seen:
            continue
        seen.add(key)
        out.append((u, a))
    rng.shuffle(out)
    return out[:n]


def _ollama_available() -> str | None:
    try:
        r = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=8,
        )
        if r.returncode != 0:
            return None
        lines = [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()]
        names = []
        for ln in lines[1:]:
            name = ln.split()[0]
            names.append(name)
        # Prefer chat models; skip large coder-only that often hang.
        prefer = [
            n
            for n in names
            if any(x in n.lower() for x in ("llama3", "llama3.1", "llama3.2", "qwen2.5:", "mistral", "phi", "gemma"))
            and "coder" not in n.lower()
            and "14b" not in n.lower()
            and "32b" not in n.lower()
        ]
        if prefer:
            return prefer[0]
        # Secondary: small non-coder
        small = [n for n in names if "coder" not in n.lower() and "14b" not in n.lower()]
        return small[0] if small else None
    except Exception:
        return None


def _ollama_chat(model: str, prompt: str) -> str | None:
    body = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.5, "num_predict": 60},
        }
    ).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            doc = json.loads(resp.read().decode("utf-8", errors="replace"))
            text = (doc.get("response") or "").strip()
            text = text.split("\n")[0].strip().strip("\"'")
            if len(text) < 2 or len(text) > 180:
                return None
            # Reject slang dumps / discord-ish tone
            low = text.lower()
            if any(x in low for x in ("lololol", "discord", "broooo", "skibidi")):
                return None
            return text
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None


_PROMPTS = [
    "Reply in one short professional sentence to: hey",
    "Reply in one short professional sentence to: status please",
    "Reply in one short professional sentence to: are we making money",
    "Reply in one short professional sentence to: any errors in the stack",
    "Reply in one short honest sentence as a tiny local AI (not ChatGPT) to: are you smart",
    "Reply in one short sentence offering read-only help to: can you see my code",
    "Reply in one short sentence to: how is the portfolio",
    "Reply in one short sentence to: is HFT running",
    "Reply in one short sentence to: what does fortress do",
    "Reply in one short sentence to: find errors",
]


def generate_teacher_corpus(*, n_ollama: int = 40, n_templates: int = 4000) -> dict:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    rng = random.Random(7)
    pairs = list(CURATED)
    pairs.extend(_operator_templates(rng, n_templates))

    # Hot Cramer picks + no-name-favoritism lines
    try:
        from intel.cramer_hot_picks import distill_hot_talk_pairs

        pairs.extend(distill_hot_talk_pairs())
    except Exception:
        pass

    # Fold in investing-guide 292-topic Q&A (durable encyclopedia)
    try:
        from intel.talk_investing_guide import build_investing_guide_pairs, save_investing_guide_corpus

        guide_pairs = build_investing_guide_pairs()
        if not guide_pairs:
            save_investing_guide_corpus()
            guide_pairs = build_investing_guide_pairs()
        pairs.extend(guide_pairs)
    except Exception as e:
        print(f"[teacher] investing guide distill skip: {e}", flush=True)

    # Fold in wiki/arxiv knowledge corpus if present
    know = ROOT / "data" / "talk_brain" / "knowledge_teacher.txt"
    if know.is_file():
        pairs.append(("knowledge corpus loaded", "Allowlisted Wikipedia and arXiv summaries are in the teacher pack."))

    model = _ollama_available()
    ollama_ok = 0
    # Default OFF — live talk is local CharLSTM; teacher must not disguise as Qwen.
    use_ollama = os.getenv("TALK_USE_OLLAMA_TEACHER", "false").lower() in ("1", "true", "yes")
    if model and use_ollama:
        print(f"[teacher] ollama model={model} (opt-in only; not used for live chat)", flush=True)
        prompts = list(_PROMPTS)
        # Distill today's Cramer buys via teacher if chat model works
        prompts.extend(
            [
                "Reply in one short professional sentence listing Cramer buys COST WMT NOW CRM JNJ as signal boosts.",
                "Reply in one short sentence: ranking never prefers tickers by letter or name.",
            ]
        )
        while len(prompts) < n_ollama:
            prompts.append(rng.choice(_PROMPTS))
        for p in prompts[:n_ollama]:
            ans = _ollama_chat(model, p + "\nOnly output the reply text. Professional, short.")
            if not ans:
                continue
            user = p.split("to:", 1)[-1].strip() if "to:" in p else "hey"
            pairs.append((user, ans))
            ollama_ok += 1
        if ollama_ok == 0:
            print("[teacher] ollama present but no usable replies — curated+templates only", flush=True)
    else:
        print(
            "[teacher] ollama DISABLED for teacher (TALK_USE_OLLAMA_TEACHER=false) — "
            "local curated+template distillation only",
            flush=True,
        )
        model = None

    # Reinforce curated professionalism
    pairs = pairs + CURATED * 40
    rng.shuffle(pairs)
    text = "\n".join(f"you: {u}\nai: {a}\n" for u, a in pairs)
    # Append knowledge corpus body
    if know.is_file():
        text = text + "\n" + know.read_text(encoding="utf-8")
    OUT.write_text(text, encoding="utf-8")
    meta = {
        "path": str(OUT),
        "chars": len(text),
        "pairs": text.count("you:"),
        "ollama_model": model,
        "ollama_pairs": ollama_ok,
        "mode": "teacher_distillation",
        "templates": n_templates,
    }
    META.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"[teacher] wrote {meta}", flush=True)
    return meta


def main() -> int:
    # Support trillion-scale config; session uses templates + ollama within reason
    problems = int(os.getenv("TALK_TEACHER_PROBLEMS", os.getenv("TALK_TEACHER_TEMPLATES", "4000")))
    # Map problems → templates (capped per process; harness handles resume)
    n_templates = min(problems, int(os.getenv("TALK_TEACHER_TEMPLATES", str(min(problems, 250_000)))))
    generate_teacher_corpus(
        n_ollama=int(os.getenv("TALK_TEACHER_N", "40")),
        n_templates=max(4000, n_templates) if problems >= 4000 else max(500, n_templates),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
