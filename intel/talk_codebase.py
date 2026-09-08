"""Read-only codebase bridge for the homemade talk brain.

Wired for awareness (stack, files, math flags) and optional corpus ingest so
the LSTM can learn what the repo is. Edits stay OFF until problems_done >= 1e9
AND TALK_ALLOW_EDITS=true (intel.talk_edit_gate). Error reporting is
observe-only — never auto-fixes files.
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CORPUS_OUT = ROOT / "data" / "talk_brain" / "codebase_corpus.txt"

# Key modules the brain may train on (read-only text ingest).
_CORPUS_TARGETS: tuple[str, ...] = (
    "intel/talk_brain.py",
    "intel/talk_codebase.py",
    "intel/talk_culture.py",
    "intel/talk_grammar.py",
    "tools/operator_terminal_chat.py",
    "tools/enhancement_queue.py",
    "parallel_train.py",
    "fortress_live.py",
    "paper_sim_today.py",
    "run_all.sh",
    "analytics/math_pivot.py",
)


def connect_enabled() -> bool:
    return os.getenv("TALK_CONNECT_CODEBASE", "true").lower() in ("1", "true", "yes")


def edits_allowed() -> bool:
    """Hard off until 1B problems + TALK_ALLOW_EDITS — see intel.talk_edit_gate."""
    try:
        from intel.talk_edit_gate import edits_allowed as _gate

        return bool(_gate(source="talk_codebase", log=False))
    except Exception:
        return False


def _alive(pat: str) -> bool:
    try:
        return subprocess.run(["pgrep", "-f", pat], capture_output=True, timeout=5).returncode == 0
    except Exception:
        return False


def stack_snapshot() -> dict[str, bool]:
    return {
        "fortress": _alive("fortress_live.py"),
        "micro_scalp": _alive("micro_scalp_daemon.py"),
        "pattern": _alive("hidden_pattern_scan.py"),
        "day_trade": _alive("day_trade_daemon.py"),
        "train_top100": _alive("train_top100_perfect.py"),
        "parallel_train": _alive("parallel_train.py"),
        "enhancement_queue": _alive("enhancement_queue.py"),
        "idle_watchdog": _alive("idle_watchdog"),
        "stack_watchdog": _alive("stack_watchdog.py"),
        "hft_obi": _alive("dist/obi-tape/index.js"),
        "doc_chat": _alive("operator_doc_chat.py"),
    }


def math_flags() -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        from analytics.math_pivot import pivot_status

        out.update(pivot_status())
    except Exception as e:
        out["math_error"] = str(e)[:80]
    brain = ROOT / "data" / "talk_brain" / "meta.json"
    if brain.is_file():
        try:
            out["talk_brain"] = json.loads(brain.read_text(encoding="utf-8"))
        except Exception:
            pass
    return out


def briefing(max_chars: int = 500) -> str:
    """Short factual context the chat can lean on — not for the LSTM to memorize."""
    snap = stack_snapshot()
    up = [k for k, v in snap.items() if v]
    down = [k for k, v in snap.items() if not v]
    mf = math_flags()
    lines = [
        f"stack_up={','.join(up) or 'none'}",
        f"stack_down={','.join(down) or 'none'}",
        f"PURE_MATH_PIVOT={mf.get('pure_math_pivot', '?')}",
        f"edits_allowed={edits_allowed()}",
        "mode=read_only_wire",
    ]
    text = " | ".join(lines)
    return text[:max_chars]


def _wants_detail(user: str) -> bool:
    return bool(
        re.search(
            r"(?i)\b(full|more detail|in detail|longer|everything|read everything|"
            r"explain more|tell me more|go deeper|expand)\b",
            user or "",
        )
    )


def repo_overview(max_chars: int = 900, *, brief: bool = True) -> str:
    """Human-readable read-only summary of the FATE_AlgoBot repo."""
    snap = stack_snapshot()
    up = [k for k, v in snap.items() if v]
    edit_note = (
        "Edits ON."
        if edits_allowed()
        else "Edits OFF — read-only."
    )
    if brief:
        # Keep under ~120 chars so hard-caps never slice mid-word
        core_up = ", ".join(up[:4]) + ("…" if len(up) > 4 else "")
        return f"Observe mode. Up: {core_up or 'none'}. {edit_note} Try find errors."

    top = []
    try:
        for p in sorted(ROOT.iterdir(), key=lambda x: x.name.lower()):
            if p.name.startswith("."):
                continue
            top.append(f"{p.name}/" if p.is_dir() else p.name)
    except Exception:
        top = ["(could not list root)"]
    top_s = ", ".join(top[:24])
    if len(top) > 24:
        top_s += ", …"

    key_dirs = []
    for name in ("intel", "tools", "analytics", "models", "data", "paper", "hft"):
        d = ROOT / name
        if d.is_dir():
            try:
                n = sum(1 for _ in d.rglob("*") if _.is_file())
            except Exception:
                n = "?"
            key_dirs.append(f"{name}/ (~{n} files)")

    parts = [
        "I can read the FATE_AlgoBot codebase in read-only mode.",
        f"Root has: {top_s}.",
        f"Key areas: {', '.join(key_dirs) or 'n/a'}.",
        f"Live stack up: {', '.join(up) or 'none of the checked daemons'}.",
        edit_note,
        "Ask find errors for a short issue list.",
    ]
    return " ".join(parts)[:max_chars]


def build_codebase_corpus(*, max_file_chars: int = 12_000) -> str:
    """Read-only Q&A + module snippets for talk-brain training (no edit rights)."""
    blocks: list[str] = [
        "you: can you see my code\nai: Yes — wired read-only. Edits stay off.\n",
        "you: have you seen the code\nai: Yes — observe mode. Short briefing on request; edits stay off.\n",
        "you: have you seen teh code\nai: Yes — observe mode. Ask for a briefing or find errors.\n",
        "you: well have you seen the code\nai: Yes — wired read-only. I can summarize the repo.\n",
        "you: seen the code\nai: Yes. Observe only — say find errors for a scan.\n",
        "you: see the code\nai: Wired read-only. Ask for a briefing.\n",
        "you: see my code\nai: Yes — observe mode. Edits stay off.\n",
        "you: look at the code\nai: Sure — read-only observe. No edits.\n",
        "you: read the code\nai: Read-only. I can summarize without changing anything.\n",
        "you: are you connected to the codebase\nai: Yes. Observe mode only. I train on key modules read-only.\n",
        "you: can you edit my code\nai: No. TALK_ALLOW_EDITS is false. I only observe and report.\n",
        "you: find errors\nai: I scan critical paths read-only and list issues. I do not auto-fix.\n",
        "you: what's wrong\nai: Ask find errors for a short bullet list of problems.\n",
        "you: are there any inaccuracies\nai: Scanning read-only for issues — short list only. Edits stay off.\n",
        "you: so are there any inaccuracies\nai: Scanning read-only for issues — short list only. Edits stay off.\n",
        "you: do you read any inaccuracies\nai: Yes — I scan read-only and report issues. Edits stay off.\n",
        "you: like do you read any of them\nai: Yes — scanning read-only for issues. Edits stay off.\n",
        "you: review codebase\nai: Read-only review — I report issues, never patch files myself.\n",
        "you: what is this repo\nai: FATE_AlgoBot — trading stack with train, paper, fortress, and talk brain.\n",
        "you: what is parallel_train\nai: parallel_train trains daily/intraday model heads across the universe.\n",
        "you: what is enhancement queue\nai: enhancement_queue runs the full finish pipeline including top100 and LSTM-all.\n",
        "you: what is fortress\nai: fortress_live is the live-facing fortress trading daemon.\n",
    ]
    snap = stack_snapshot()
    up = [k for k, v in snap.items() if v]
    blocks.append(
        f"you: stack status\nai: Observe: up={','.join(up) or 'none'}; edits_allowed={edits_allowed()}.\n"
    )
    for rel in _CORPUS_TARGETS:
        path = ROOT / rel
        if not path.is_file():
            continue
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        snippet = raw[:max_file_chars]
        # Keep dialogue shape; summarize purpose from path + first docstring-ish line
        first = ""
        for line in snippet.splitlines()[:40]:
            s = line.strip()
            if s.startswith('"""') or s.startswith("'''"):
                first = s.strip("\"' ")[:120]
                break
            if s.startswith("#") and "coding" not in s.lower():
                first = s.lstrip("# ").strip()[:120]
                break
        purpose = first or f"module {rel}"
        blocks.append(f"you: what is {rel}\nai: {purpose}\n")
        # Light structural cues (function/class names) — not full dump
        names = re.findall(r"^(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)", snippet, re.M)
        if names:
            shown = ", ".join(names[:12])
            blocks.append(
                f"you: summarize {rel}\nai: {rel} defines: {shown}. Read-only — I do not edit it.\n"
            )
    return "\n".join(blocks)


def save_codebase_corpus() -> dict[str, Any]:
    CORPUS_OUT.parent.mkdir(parents=True, exist_ok=True)
    text = build_codebase_corpus()
    CORPUS_OUT.write_text(text, encoding="utf-8")
    return {"path": str(CORPUS_OUT), "chars": len(text), "lines": text.count("\n")}


def _py_syntax_issues(paths: list[Path], *, limit: int = 8) -> list[str]:
    out: list[str] = []
    for p in paths:
        if not p.is_file() or p.suffix != ".py":
            continue
        try:
            src = p.read_text(encoding="utf-8", errors="replace")
            ast.parse(src, filename=str(p))
        except SyntaxError as e:
            rel = p.relative_to(ROOT) if str(p).startswith(str(ROOT)) else p
            out.append(f"syntax {rel}:{e.lineno}: {e.msg}")
        except Exception as e:
            out.append(f"parse {p.name}: {type(e).__name__}")
        if len(out) >= limit:
            break
    return out


def _pattern_flags(paths: list[Path], *, limit: int = 6) -> list[str]:
    """Known failure / smell patterns — report only, never auto-fix."""
    smells = [
        (re.compile(r"except\s*:\s*(?:pass|\.\.\.)\s*$", re.M), "bare except pass"),
        (re.compile(r"TALK_ALLOW_EDITS\s*=\s*['\"]true['\"]", re.I), "edits unlocked in source"),
        (re.compile(r"TODO\s*\(critical\)|FIXME\s*\(critical\)|XXX\s*SECURITY", re.I), "critical TODO/FIXME"),
    ]
    hits: list[str] = []
    for p in paths:
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")[:200_000]
        except Exception:
            continue
        rel = str(p.relative_to(ROOT)) if str(p).startswith(str(ROOT)) else p.name
        for rx, label in smells:
            if rx.search(text):
                hits.append(f"{label} in {rel}")
                if len(hits) >= limit:
                    return hits
    return hits


def scan_issues(*, max_items: int = 10) -> list[str]:
    """Static / ops health scan. Returns short problem strings (empty = clean)."""
    issues: list[str] = []

    if edits_allowed():
        issues.append("TALK_ALLOW_EDITS is ON — talk can edit; usually leave false.")

    brain = ROOT / "data" / "talk_brain" / "brain.pt"
    if not brain.is_file():
        issues.append("talk brain missing (data/talk_brain/brain.pt) — run train-talk.")

    snap = stack_snapshot()
    # Core train/live pieces we expect when finishing
    for key, label in (
        ("enhancement_queue", "enhancement-queue not running"),
        ("parallel_train", "parallel_train not running (daily may idle if caught up)"),
        ("fortress", "fortress_live not running"),
    ):
        if key == "parallel_train" and not snap.get(key):
            # Soft: only note if enhancement also down
            if not snap.get("enhancement_queue"):
                issues.append(label)
        elif not snap.get(key) and key != "parallel_train":
            issues.append(label)

    ckpt = ROOT / "data" / "train_checkpoint.json"
    if ckpt.is_file():
        try:
            data = json.loads(ckpt.read_text(encoding="utf-8"))
            failed = data.get("failed") or data.get("failures") or []
            if isinstance(failed, dict):
                n = len(failed)
            else:
                n = len(failed)
            if n:
                issues.append(f"train checkpoint reports {n} failed symbol(s).")
        except Exception:
            pass

    eq_log = ROOT / "logs" / "enhancement-queue_latest.log"
    if eq_log.is_file():
        try:
            tail = eq_log.read_text(encoding="utf-8", errors="replace")[-4000:].lower()
            if "traceback" in tail or "fatal" in tail:
                issues.append("enhancement-queue log shows traceback/fatal recently.")
        except Exception:
            pass

    targets = [ROOT / rel for rel in _CORPUS_TARGETS if (ROOT / rel).suffix == ".py"]
    issues.extend(_py_syntax_issues(targets))
    issues.extend(_pattern_flags(targets))

    # Dedupe preserve order
    seen: set[str] = set()
    uniq: list[str] = []
    for i in issues:
        if i not in seen:
            seen.add(i)
            uniq.append(i)
    return uniq[:max_items]


def error_report(user: str = "") -> str:
    """Concise operator-facing issue list. Never modifies files."""
    items = scan_issues()
    detail = _wants_detail(user)
    if not items:
        snap = stack_snapshot()
        up = [k for k, v in snap.items() if v]
        msg = f"No critical issues found. Up: {', '.join(up) or 'none'}. Edits off."
        return msg if detail else msg[:120]
    bullets = "; ".join(f"• {x}" for x in items[: 8 if detail else 5])
    prefix = "Issues (read-only, not fixed): "
    out = prefix + bullets
    if not detail:
        from intel.talk_brain import brief_reply

        return brief_reply(out, max_chars=220, max_sentences=4)
    return out[:900]


_FACT_PAT = re.compile(
    r"\b(status|stack|running|alive|down|fortress|train|pattern|scalp|"
    r"math|pivot|edit|codebase|code\s*base|wired|connect|repo|repository|"
    r"what.?s up with the bot|how.?s the|processes?|"
    r"read\s+(my\s+)?(code|codebase|repo|repository)|"
    r"look\s+(at|through)\s+(my\s+)?(code|codebase|repo)|"
    r"summarize\s+(the\s+)?(code|codebase|repo)|"
    r"what.?s\s+in\s+(the\s+)?(repo|codebase)|"
    r"show\s+(me\s+)?(the\s+)?(codebase|repo)|"
    r"(have\s+you\s+)?(seen|see)\s+(the\s+|my\s+|teh\s+)?(code|codebase|repo)|"
    r"can\s+you\s+(see|seen|read|look\s+at|observe)\s+(my\s+|the\s+)?(code|codebase|repo)|"
    r"(see|seen|observe)\s+(my\s+|the\s+|teh\s+)?(code|codebase|repo|stack)|"
    r"do\s+(you|u)\s+(see|seen|read)\s+(my\s+|the\s+)?(code|codebase)|"
    r"well\s+.*\b(seen|see|look|read)\b.*\b(code|codebase|repo)\b|"
    r"find(?:ing)?\s+errors?|what'?s\s+wrong|whats\s+wrong|review\s+(the\s+)?(code|codebase|repo)|"
    r"any\s+(bugs?|errors?|issues?|inaccurac\w*|mistakes?|problems?)|"
    r"inaccurac\w*|inaccurate|anything\s+wrong|"
    r"scan\s+(for\s+)?(errors?|issues?|problems?)|"
    r"portfolio|equity|buying\s+power|account\s+value|p\s*&\s*l|pnl)\b",
    re.I,
)

_READ_CODE_PAT = re.compile(
    r"\b(read|look|summarize|scan|inspect|browse|show|see|seen|observe)\b.*\b(codebase|code\s*base|repo|repository|code|stack)\b"
    r"|\b(codebase|repo|repository|code)\b.*\b(read|look|summarize|scan|inspect|see|seen|observe)\b"
    r"|\b(have\s+you\s+)?(seen|see)\s+(the\s+|my\s+|teh\s+)?(code|codebase|repo)\b"
    r"|\bcan\s+you\s+(see|seen|read|look\s+at|observe)\b.*\b(code|codebase|repo)\b"
    r"|\bplease\s+read\b"
    r"|\bobserve\s+(the\s+)?(stack|repo|codebase)\b"
    r"|\bread\s+the\s+code\b"
    r"|\bdo\s+(you|u)\s+read\b"
    r"|\bhave\s+you\s+read\b"
    r"|\b(seen|see)\s+the\s+code\b",
    re.I,
)

# Error / inaccuracy scan — wins over observe when both match
_ERROR_PAT = re.compile(
    r"(?i)("
    r"\bfind(?:ing)?\s+errors?\b|"
    r"\btry\s+(to\s+)?find(?:ing)?\s+errors?\b|"
    r"\bcheck\s+(for\s+)?(errors?|issues?|bugs?)\b|"
    r"\blook\s+for\s+(errors?|bugs?|issues?)\b|"
    r"\bwhat'?s\s+wrong\b|\bwhats\s+wrong\b|"
    r"\breview\s+(the\s+)?(code|codebase|repo)\b|"
    r"\bany\s+(bugs?|errors?|issues?|inaccurac\w*|mistakes?|problems?)\b|"
    r"\binaccurac\w*\b|\binaccurate\b|"
    r"\banything\s+wrong\b|\bany\s+mistakes?\b|"
    r"\b(are\s+there\s+)?any\s+(bugs?|errors?|issues?|inaccurac\w*|mistakes?|problems?)\b|"
    r"\bdo\s+(you|u)\s+read\s+any\b|"
    r"\bread\s+any\s+(of\s+them|inaccurac\w*|errors?|bugs?|issues?|mistakes?)\b|"
    r"\bscan\s+(for\s+)?(errors?|issues?|problems?)\b|"
    r"\bcode\s+review\b|\bstatic\s+review\b"
    r")"
)

_PORTFOLIO_PAT = re.compile(
    r"(?i)("
    r"\bportfolio\b|\bequity\b|\bbuying\s+power\b|"
    r"\baccount\s+value\b|\baccount\s+equity\b|"
    r"\bp\s*&\s*l\b|\bpnl\b|\bprofit\s+and\s+loss\b|"
    r"\b(see|seen|show|check|read|look\s+at)\b.{0,40}\b(portfolio|equity|positions?|account)\b|"
    r"\b(value|worth)\s+of\s+(the\s+)?(portfolio|account|equity)\b|"
    r"\bhow\s+much\s+(is\s+)?(the\s+)?(portfolio|account|equity)\b"
    r")"
)

# Earning / P&L vernacular — high priority before culture / grammar / LSTM
_EARNING_PAT = re.compile(
    r"(?i)("
    r"\b(earn|earning|earnings|profitable)\b|"
    r"\b(making|losing)\s+(any\s+)?money\b|"
    r"\b(are\s+we|am\s+i|are\s+you)\s+(we\s+)?(earn|earning|making|losing|profitable)\b|"
    r"\b(up\s+or\s+down)\b|"
    r"\b(overall\s+)?\b(performance|profit|loss)\b|"
    r"\bhow\s+(are|is)\s+(we|the\s+(bot|account|portfolio))\s+doing\b|"
    r"\b(going\s+up|going\s+down)\b.{0,30}\b(portfolio|equity|value|account)\b|"
    r"\b(portfolio|equity|value|account).{0,30}\b(going\s+up|going\s+down)\b"
    r")"
)

# Bare "are we" / "am i" — continue P&L only after earning/portfolio prior
_INCOMPLETE_EARNING_CONT = re.compile(
    r"(?i)^(well[, ]*)?(are\s+we|am\s+i|are\s+you)\??$"
)

_FOLLOWUP_THEM_PAT = re.compile(
    r"(?i)\b(any\s+of\s+them|of\s+them|those|any\s+yet)\b"
)

_AFFIRM_PAT = re.compile(
    r"(?i)^(yes|yeah|yep|yup|ok|okay|sure|please|go\s+ahead|do\s+it|"
    r"do\s+that|yes,?\s*do\s+that|please\s+do(\s+that)?|"
    r"go\s+for\s+it|sounds\s+good|alright|all\s+right)[\s.!]*$"
)

# Strong "do that" affirmations — never fall through to LSTM grammar dumps
_DO_THAT_PAT = re.compile(
    r"(?i)^(yes,?\s*)?(please\s+)?(do\s+that|do\s+it|go\s+ahead|go\s+for\s+it)[\s.!]*$"
)

_INCOMPLETE_PAT = re.compile(
    r"(?i)^(do\s+you|can\s+you|will\s+you|are\s+you|did\s+you|have\s+you|"
    r"do\s+u|can\s+u)\??$"
)


def wants_factual(user: str) -> bool:
    u = user or ""
    return bool(
        _FACT_PAT.search(u)
        or _READ_CODE_PAT.search(u)
        or _ERROR_PAT.search(u)
        or _PORTFOLIO_PAT.search(u)
        or _EARNING_PAT.search(u)
    )


def wants_error_scan(user: str) -> bool:
    return bool(_ERROR_PAT.search(user or ""))


def wants_observe(user: str) -> bool:
    u = user or ""
    return bool(_READ_CODE_PAT.search(u)) and not wants_error_scan(u) and not wants_portfolio(u)


def wants_earning(user: str) -> bool:
    return bool(_EARNING_PAT.search(user or ""))


def wants_portfolio(user: str) -> bool:
    u = user or ""
    return bool(_PORTFOLIO_PAT.search(u) or _EARNING_PAT.search(u))


def is_affirmation(user: str) -> bool:
    return bool(_AFFIRM_PAT.match((user or "").strip()))


def is_do_that(user: str) -> bool:
    return bool(_DO_THAT_PAT.match((user or "").strip()))


def incomplete_prompt_reply(user: str) -> str | None:
    """Bare 'Do you' / 'Can you' → clarify, never thanks/grammar dumps."""
    if _INCOMPLETE_PAT.match((user or "").strip()):
        return "Do I what?"
    return None


def detect_offer(reply: str) -> str | None:
    """If the AI offered an action, remember it for yes/do-that follow-ups."""
    low = (reply or "").lower()
    if not low:
        return None
    if "find error" in low or "try find" in low or "issue list" in low:
        return "errors"
    if "portfolio" in low and ("ask" in low or "say" in low):
        return "portfolio"
    return None


def run_offer(offer: str, user: str = "") -> str | None:
    if offer == "errors":
        return error_report(user)
    if offer == "observe":
        return repo_overview(brief=True)
    if offer == "portfolio":
        return portfolio_report(user)
    return None


def equity_snapshot() -> dict[str, Any]:
    """Read-only equity curve + live Alpaca tip for talk observe paths."""
    try:
        from equity_terminal_chart import equity_snapshot as _eq

        return _eq()
    except Exception as e:
        return {"source": "none", "error": str(e)[:80]}


def _curve_trend(es: dict[str, Any] | None) -> str:
    """Recent equity-curve direction from history tip (up/down/flat)."""
    if not es:
        return "flat"
    try:
        from equity_terminal_chart import load_history_series

        hist = load_history_series(max_points=40)
    except Exception:
        hist = []
    if len(hist) >= 4:
        mid = len(hist) // 2
        a = sum(hist[:mid]) / max(mid, 1)
        b = sum(hist[mid:]) / max(len(hist) - mid, 1)
        chg = (b - a) / max(abs(a), 1e-9)
        if chg > 0.002:
            return "up"
        if chg < -0.002:
            return "down"
        return "flat"
    hmin, hmax, hlast = es.get("history_min"), es.get("history_max"), es.get("history_last")
    try:
        if hmin is not None and hmax is not None and hlast is not None:
            span = float(hmax) - float(hmin)
            if span <= 1e-6:
                return "flat"
            # Near highs → up bias; near lows → down
            loc = (float(hlast) - float(hmin)) / span
            if loc >= 0.6:
                return "up"
            if loc <= 0.4:
                return "down"
    except (TypeError, ValueError):
        pass
    return "flat"


def portfolio_report(user: str = "") -> str:
    """Short read-only Alpaca paper equity / positions + fortress liveness.

    Earning / up-or-down prompts get a one-line UP/DOWN + day P&L answer.
    Explicit portfolio observe still gets the fuller equity dump.
    """
    snap = stack_snapshot()
    fortress = "up" if snap.get("fortress") else "down"
    eq = bp = cash = pnl = None
    npos = 0
    top: list[str] = []
    deployed = 0.0
    curve_note = ""
    es: dict[str, Any] = {}
    try:
        es = equity_snapshot()
        if es.get("spark"):
            curve_note = f" curve[{es.get('history_pts', 0)}]: {es['spark']}"
        if eq is None and es.get("equity") is not None:
            eq = float(es["equity"])
        if pnl is None and es.get("day_pnl") is not None:
            pnl = float(es["day_pnl"])
    except Exception:
        pass
    try:
        from alpaca_broker import get_account, intraday_buying_power, list_positions

        acct = get_account() or {}
        if acct:
            try:
                eq = float(acct.get("equity") or acct.get("portfolio_value") or 0)
            except (TypeError, ValueError):
                eq = None
            try:
                cash = float(acct.get("cash") or 0)
            except (TypeError, ValueError):
                cash = None
            try:
                bp = float(intraday_buying_power(acct))
            except Exception:
                bp = None
            try:
                last = float(acct.get("last_equity") or 0)
                if eq is not None and last:
                    pnl = eq - last
            except (TypeError, ValueError):
                pnl = None
        positions = list_positions() or []
        npos = len(positions)
        for p in positions[:4]:
            sym = p.get("symbol") or "?"
            try:
                mv = float(p.get("market_value") or 0)
            except (TypeError, ValueError):
                mv = 0.0
            deployed += abs(mv)
            top.append(f"{sym} ${mv:,.0f}")
        if npos > 4:
            for p in positions[4:]:
                try:
                    deployed += abs(float(p.get("market_value") or 0))
                except (TypeError, ValueError):
                    pass
    except Exception:
        pass

    if eq is None:
        return (
            f"Paper account unavailable right now. Fortress {fortress}. "
            f"Edits OFF."
        )

    u = user or ""
    short_pnl = wants_earning(u) or bool(
        re.search(r"(?i)\b(up\s+or\s+down|going\s+up|going\s+down)\b", u)
    )
    if short_pnl:
        day = pnl if pnl is not None else 0.0
        day_dir = "Up" if day >= 0 else "Down"
        sign = "+" if day >= 0 else ""
        trend = _curve_trend(es)
        trend_note = {
            "up": "Recent curve trending up.",
            "down": "Recent curve trending down.",
            "flat": "Recent curve mostly flat.",
        }.get(trend, "Recent curve mostly flat.")
        cash_heavy = eq > 0 and deployed < 0.15 * eq
        if cash_heavy:
            pos_note = (
                f"Still mostly cash — only {npos} small position"
                f"{'' if npos == 1 else 's'}."
            )
        elif npos:
            pos_note = f"{npos} pos ({', '.join(top)})." if top else f"{npos} positions."
        else:
            pos_note = "No open positions."
        return (
            f"{day_dir} today {sign}${day:,.0f} on equity ${eq:,.0f}. "
            f"{trend_note} {pos_note}"
        )

    parts = [f"Equity ${eq:,.0f}"]
    if bp is not None:
        parts.append(f"BP ${bp:,.0f}")
    if cash is not None:
        parts.append(f"cash ${cash:,.0f}")
    if pnl is not None:
        sign = "+" if pnl >= 0 else ""
        parts.append(f"day {sign}${pnl:,.0f}")
    parts.append(f"{npos} pos")
    if top:
        parts.append("(" + ", ".join(top) + ")")
    parts.append(f"fortress {fortress}.")
    if curve_note:
        parts.append(curve_note.strip() + ".")
    parts.append("Edits OFF.")
    return " ".join(parts)


def factual_reply(user: str) -> str:
    """Honest read-only answers — bypass the tiny LSTM for real questions."""
    snap = stack_snapshot()
    up = [k for k, v in snap.items() if v]
    down = [k for k, v in snap.items() if not v]
    u = (user or "").lower()
    detail = _wants_detail(user)

    if edits_allowed():
        edit_note = "edits ON (careful)."
    else:
        edit_note = "edits OFF."

    # Portfolio / equity / P&L — never LSTM
    if wants_portfolio(user or ""):
        return portfolio_report(user)

    # Inaccuracies / errors / "do you read any …" → short scan report
    if wants_error_scan(user or ""):
        return error_report(user)

    if re.search(r"\bedit", u) and not _READ_CODE_PAT.search(u) and not wants_error_scan(u):
        try:
            from intel.talk_edit_gate import log_denial, progress_snapshot

            snap = progress_snapshot()
            log_denial("talk_codebase.factual_reply", reason="user_asked_edit")
            return (
                f"{edit_note} AI edits locked until 1B problems "
                f"(now {snap['problems_done']:,}; {snap['pct_of_1b']}% of 1B). "
                "TALK_ALLOW_EDITS alone is not enough. Read-only now."
            )
        except Exception:
            return f"{edit_note} set TALK_ALLOW_EDITS=true only after 1B problems. Read-only now."

    if re.search(r"\bmath|pivot", u):
        mf = math_flags()
        return (
            f"math pivot pure={mf.get('pure_math_pivot')} "
            f"mult={mf.get('math_mult')}/{mf.get('news_mult')}. {edit_note}"
        )

    if _READ_CODE_PAT.search(u) or re.search(
        r"\bcodebase|code\s*base|repo\b|"
        r"\b(see|seen|read|look|observe).{0,24}\b(code|codebase|repo)\b",
        u,
    ):
        return repo_overview(brief=not detail)

    parts = [
        "wired read-only.",
        f"up: {', '.join(up) or 'none'}.",
    ]
    if down and detail:
        parts.append(f"down: {', '.join(down)}.")
    parts.append(edit_note)
    return " ".join(parts)


def _prior_earning_context(prior: str) -> bool:
    p = prior or ""
    return bool(
        wants_portfolio(p)
        or wants_earning(p)
        or re.search(r"(?i)\b(earn|earning|portfolio|equity|p\s*&\s*l|pnl|profit|money)\b", p)
    )


def maybe_handle(user: str, *, prior: str = "", last_offer: str = "") -> str | None:
    if not connect_enabled():
        return None
    # Affirmation after AI offered find-errors / observe / portfolio
    if is_affirmation(user or ""):
        if last_offer:
            ran = run_offer(last_offer, user)
            if ran is not None:
                return ran
        # "Yes, do that" with nothing pending — never LSTM Then/Than dumps
        if is_do_that(user or ""):
            return "Nothing pending. Say find errors, status, or portfolio."
    # "are we" / "am i" after earning/portfolio talk → continue P&L (not grammar)
    if _INCOMPLETE_EARNING_CONT.match((user or "").strip()) and _prior_earning_context(prior):
        return portfolio_report(user or "are we earning")
    inc = incomplete_prompt_reply(user or "")
    if inc is not None:
        return inc
    if wants_factual(user):
        return factual_reply(user)
    # Follow-up after code/error talk: "any of them" / "of them"
    if prior and _FOLLOWUP_THEM_PAT.search(user or ""):
        if wants_factual(prior) or wants_error_scan(prior) or _READ_CODE_PAT.search(prior):
            return error_report(user)
    return None
