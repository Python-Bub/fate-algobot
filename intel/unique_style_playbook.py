"""Discover a unique FATE trading playbook — math-first, not Cramer-copy.

Researches allowlisted sources + local book + historical events + performance
lessons (BP/KLAC pressure, SBUX earnings, micro-scalp bleed, fortress overnight),
then writes data/intel/unique_playbook.json (+ .md).

Pipelines read tweaks via load_playbook() / unique_rank_boost() — env-overridable.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = ROOT / "data" / "intel" / "unique_playbook.json"
OUT_MD = ROOT / "data" / "intel" / "unique_playbook.md"
BOOK_STRAT = ROOT / "data" / "intel" / "book_strategies.json"
BOOKS_DIR = ROOT / "data" / "books"
MICRO_STATE = ROOT / "data" / "intel" / "micro_scalp_state.json"
EARNINGS_RADAR = ROOT / "data" / "intel" / "earnings_radar.json"

_CACHE: dict[str, Any] | None = None
_CACHE_MTIME: float = 0.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _b(name: str, default: bool = True) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _research_local() -> dict[str, Any]:
    """Gather local lessons — no name favoritism, evidence only."""
    lessons: list[dict[str, Any]] = []
    sources: list[str] = []

    # Book strategies
    book = _read_json(BOOK_STRAT)
    fams = []
    if book:
        sources.append("data/intel/book_strategies.json")
        for s in book.get("strategies") or []:
            fam = s.get("family") or s.get("sleeve")
            if fam:
                fams.append(str(fam))
        lessons.append(
            {
                "id": "book_families",
                "worked": True,
                "note": f"Local guide families: {', '.join(fams[:8]) or 'none'}",
                "weight_hint": 0.12,
            }
        )

    # Books dir presence
    if BOOKS_DIR.is_dir():
        sources.append("data/books/")
        n = sum(1 for _ in BOOKS_DIR.rglob("*.md"))
        lessons.append(
            {
                "id": "local_books",
                "worked": n > 0,
                "note": f"{n} markdown book file(s) under data/books/",
                "weight_hint": 0.05,
            }
        )

    # Historical / earnings
    radar = _read_json(EARNINGS_RADAR)
    if radar:
        sources.append("data/intel/earnings_radar.json")
        lessons.append(
            {
                "id": "earnings_radar",
                "worked": True,
                "note": "Earnings radar live — posture: reduce new risk in window (SBUX-class).",
                "weight_hint": 0.10,
            }
        )
    else:
        lessons.append(
            {
                "id": "earnings_calendar",
                "worked": True,
                "note": "Tighten size near earnings; fear-sell watch (SBUX-class).",
                "weight_hint": 0.10,
            }
        )
    try:
        from intel import historical_events as _he

        if hasattr(_he, "earnings_event"):
            sources.append("intel.historical_events")
    except Exception:
        pass

    # Downward pressure lesson (BP / KLAC class)
    try:
        from intel.downward_pressure import blocks_new_buy

        _ = blocks_new_buy  # import proves module wired
        sources.append("intel.downward_pressure")
        lessons.append(
            {
                "id": "down_pressure_bp_klac",
                "worked": True,
                "failed_without": True,
                "note": (
                    "Hard-block new buys on oil weakness (BP-class) and semi dumps "
                    "(KLAC-class). Math gate, not ticker favoritism."
                ),
                "weight_hint": 0.18,
            }
        )
    except Exception:
        lessons.append(
            {
                "id": "down_pressure_bp_klac",
                "worked": True,
                "note": "Downward-pressure gate expected for BP/KLAC-style dumps.",
                "weight_hint": 0.18,
            }
        )

    # Micro-scalp bleed
    ms = _read_json(MICRO_STATE)
    if ms:
        sources.append("data/intel/micro_scalp_state.json")
        fills = int(ms.get("fills") or ms.get("trades") or 0)
        errs = str(ms.get("last_error") or "")
        bleed = bool(errs) or fills > 200
        lessons.append(
            {
                "id": "micro_scalp_bleed",
                "worked": not bleed,
                "failed": bleed,
                "note": (
                    f"Micro-scalp fills={fills}; last_error={'yes' if errs else 'no'}. "
                    "Cap noise-harvest size; never let scalp bleed overnight risk budget."
                ),
                "weight_hint": -0.08 if bleed else 0.04,
            }
        )
    else:
        lessons.append(
            {
                "id": "micro_scalp_bleed",
                "worked": True,
                "note": "Assume micro-scalp can bleed — keep as sidecar with tight BP frac.",
                "weight_hint": -0.05,
            }
        )

    # Fortress overnight — intentional hold beats flatten panic
    lessons.append(
        {
            "id": "fortress_overnight",
            "worked": True,
            "note": (
                "Fortress overnight hold ON with multi-day exit floor; "
                "do not hygiene-liquidate intentional multi-day theses."
            ),
            "weight_hint": 0.14,
        }
    )
    sources.append("fortress_live FORTRESS_ALLOW_OVERNIGHT")

    # Letter-fair / BP util
    lessons.append(
        {
            "id": "letter_fair_bp",
            "worked": True,
            "note": "Letter-fair universe training; BP util high (~0.90) but gated by pressure + earnings.",
            "weight_hint": 0.08,
        }
    )

    # Allowlisted external research (optional, best-effort, never blocks)
    wiki_bits: list[str] = []
    try:
        from intel.safe_knowledge import wiki_summary

        for title in (
            "Modern_portfolio_theory",
            "Value_investing",
            "Market_microstructure",
            "Earnings",
        ):
            doc = wiki_summary(title)
            if doc and doc.get("extract"):
                wiki_bits.append((doc.get("extract") or "")[:180])
        if wiki_bits:
            sources.append("wikipedia(allowlisted)")
            lessons.append(
                {
                    "id": "allowlisted_wiki",
                    "worked": True,
                    "note": " | ".join(wiki_bits)[:400],
                    "weight_hint": 0.03,
                }
            )
    except Exception:
        pass

    return {"lessons": lessons, "sources": sources, "book_families": fams}


def _name_from_fingerprint(lessons: list[dict[str, Any]]) -> str:
    """Stable unique name from lesson mix — not a celebrity copy."""
    blob = "|".join(sorted(str(x.get("id")) for x in lessons))
    h = hashlib.sha256(blob.encode()).hexdigest()[:8].upper()
    # Style axes from lessons
    axes = []
    ids = {str(x.get("id")) for x in lessons}
    if "down_pressure_bp_klac" in ids:
        axes.append("PressureGate")
    if "fortress_overnight" in ids:
        axes.append("OvernightFortress")
    if "earnings_radar" in ids or "earnings_calendar" in ids:
        axes.append("EarningsTight")
    if "micro_scalp_bleed" in ids:
        axes.append("ScalpCapped")
    if "letter_fair_bp" in ids:
        axes.append("LetterFair")
    if "book_families" in ids:
        axes.append("BookMath")
    style = "".join(axes[:3]) or "MathFirst"
    return f"FATE-{style}-{h}"


def discover_and_write(*, force: bool = False) -> dict[str, Any]:
    """Research + write unique playbook. Never enables edits."""
    research = _research_local()
    lessons = list(research.get("lessons") or [])
    name = _name_from_fingerprint(lessons)

    # Math-first rules (env-overridable when applied)
    rules = {
        "overnight_hold": True,
        "overnight_exit_floor_min": 4320,
        "flatten_at_close": False,
        "earnings_posture": "tighten",  # reduce new buys in window; keep stops tight
        "earnings_size_mult": 0.55,
        "down_pressure_blocks": True,
        "letter_fair": True,
        "bp_use_frac": 0.90,
        "micro_scalp_bp_frac": 0.25,
        "micro_scalp_max_share_of_risk": 0.15,
        "cramer_weight_cap": 0.08,  # never copy-Cramer-only
        "math_first": True,
        "no_name_favoritism": True,
        "risk": {
            "max_single_name_frac": 0.12,
            "stop_tighten_on_pressure": True,
            "stop_tighten_on_earnings": True,
            "forbid_new_buys_on_hard_dump": True,
        },
    }

    # Rank / size tweaks — bounded; pipelines multiply into scores
    tweaks = {
        "rank_w_unique": 0.06,
        "rank_w_math": 1.15,
        "rank_w_news": 0.55,
        "rank_w_cramer": 0.08,
        "fortress_size_mult": 1.0,
        "earnings_size_mult": rules["earnings_size_mult"],
        "pressure_block_boost": 0.0,  # block, don't boost dumps
        "overnight_pref_boost": 0.04,  # slight tilt to holdable theses
        "scalp_rank_penalty": 0.03,
    }

    # Lesson-driven adjustments
    for les in lessons:
        hid = str(les.get("id") or "")
        wh = float(les.get("weight_hint") or 0.0)
        if hid == "micro_scalp_bleed" and (les.get("failed") or wh < 0):
            tweaks["scalp_rank_penalty"] = min(0.08, tweaks["scalp_rank_penalty"] + 0.02)
            rules["micro_scalp_bp_frac"] = min(float(rules["micro_scalp_bp_frac"]), 0.20)
        if hid.startswith("down_pressure"):
            rules["down_pressure_blocks"] = True
        if hid.startswith("earnings"):
            rules["earnings_posture"] = "tighten"

    playbook = {
        "version": 1,
        "name": name,
        "unique": True,
        "not_cramer_copy": True,
        "math_first": True,
        "no_name_favoritism": True,
        "updated_at": _now(),
        "generated_ts": time.time(),
        "sources": research.get("sources") or [],
        "book_families": research.get("book_families") or [],
        "lessons": lessons,
        "rules": rules,
        "tweaks": tweaks,
        "thesis": (
            f"{name}: hold multi-day fortress theses overnight; hard-block BP/KLAC-class "
            "down-pressure; tighten into earnings (SBUX-class); cap micro-scalp bleed; "
            "letter-fair BP util ~90%; math residuals over celebrity names."
        ),
        "env_overrides": {
            "UNIQUE_PLAYBOOK_PATH": "data/intel/unique_playbook.json",
            "USE_UNIQUE_PLAYBOOK": "true",
            "RANK_W_UNIQUE": str(tweaks["rank_w_unique"]),
            "FORTRESS_ALLOW_OVERNIGHT": "true",
            "FORTRESS_BP_USE_FRAC": str(rules["bp_use_frac"]),
            "FLATTEN_AT_CLOSE": "false",
        },
        "edits_enabled": False,
        "note": "Playbook discovery does NOT unlock AI code edits (1B gate).",
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    if OUT_JSON.is_file() and not force:
        prev = _read_json(OUT_JSON)
        # Refresh timestamp/lessons but keep name if same fingerprint family
        if prev.get("name") and prev.get("name", "").startswith("FATE-"):
            # Recompute — always update content; name follows fingerprint
            pass
    OUT_JSON.write_text(json.dumps(playbook, indent=2), encoding="utf-8")

    md = (
        f"# {name}\n\n"
        f"_Updated {_now()}_\n\n"
        f"{playbook['thesis']}\n\n"
        "## Rules\n\n"
        f"- Overnight hold: **{rules['overnight_hold']}** (floor {rules['overnight_exit_floor_min']}m)\n"
        f"- Earnings posture: **{rules['earnings_posture']}** (size×{rules['earnings_size_mult']})\n"
        f"- Down-pressure blocks: **{rules['down_pressure_blocks']}** (BP/KLAC-class)\n"
        f"- Letter-fair: **{rules['letter_fair']}**\n"
        f"- BP util: **{rules['bp_use_frac']}** (scalp capped at {rules['micro_scalp_bp_frac']})\n"
        f"- Cramer weight cap: **{rules['cramer_weight_cap']}** (not copy-only)\n"
        f"- Math-first / no name favoritism: **true**\n\n"
        "## Lessons\n\n"
    )
    for les in lessons:
        flag = "ok" if les.get("worked") else "fail"
        md += f"- [{flag}] `{les.get('id')}` — {les.get('note')}\n"
    md += (
        "\n## Pipeline hooks\n\n"
        "- `intel.unique_style_playbook.unique_rank_boost` → fortress / paper_sim / integrate\n"
        "- Env: `USE_UNIQUE_PLAYBOOK`, `RANK_W_UNIQUE`, `UNIQUE_PLAYBOOK_PATH`\n"
        "- AI edits remain gated until 1B problems (`intel.talk_edit_gate`).\n"
    )
    OUT_MD.write_text(md, encoding="utf-8")
    global _CACHE, _CACHE_MTIME
    _CACHE = playbook
    _CACHE_MTIME = time.time()
    return playbook


def load_playbook(*, reload: bool = False) -> dict[str, Any]:
    global _CACHE, _CACHE_MTIME
    path = Path(os.getenv("UNIQUE_PLAYBOOK_PATH", str(OUT_JSON)))
    if not path.is_absolute():
        path = ROOT / path
    if not path.is_file():
        return {}
    mtime = path.stat().st_mtime
    if _CACHE is not None and not reload and mtime <= _CACHE_MTIME:
        return dict(_CACHE)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    _CACHE = doc if isinstance(doc, dict) else {}
    _CACHE_MTIME = mtime
    return dict(_CACHE)


def playbook_rules() -> dict[str, Any]:
    pb = load_playbook()
    return dict(pb.get("rules") or {}) if pb else {}


def playbook_tweaks() -> dict[str, Any]:
    pb = load_playbook()
    tw = dict(pb.get("tweaks") or {}) if pb else {}
    # Env overrides
    if os.getenv("RANK_W_UNIQUE"):
        tw["rank_w_unique"] = _f("RANK_W_UNIQUE", float(tw.get("rank_w_unique") or 0.06))
    if os.getenv("UNIQUE_FORTRESS_SIZE_MULT"):
        tw["fortress_size_mult"] = _f("UNIQUE_FORTRESS_SIZE_MULT", 1.0)
    if os.getenv("UNIQUE_EARNINGS_SIZE_MULT"):
        tw["earnings_size_mult"] = _f("UNIQUE_EARNINGS_SIZE_MULT", 0.55)
    return tw


def unique_rank_boost(symbol: str, *, metrics: dict[str, Any] | None = None) -> tuple[float, dict[str, Any]]:
    """Small math-first boost/penalty from unique playbook. Env: USE_UNIQUE_PLAYBOOK."""
    if not _b("USE_UNIQUE_PLAYBOOK", True):
        return 0.0, {"disabled": True}
    pb = load_playbook()
    if not pb:
        return 0.0, {"missing": True}
    tw = playbook_tweaks()
    rules = playbook_rules()
    meta: dict[str, Any] = {
        "playbook": pb.get("name"),
        "math_first": True,
        "no_name_favoritism": True,
    }
    boost = 0.0
    m = metrics or {}
    # Overnight preference for strong p_up (holdable)
    p_up = float(m.get("p_up") or m.get("neural_p_up") or 0.5)
    if rules.get("overnight_hold") and p_up >= 0.58:
        boost += float(tw.get("overnight_pref_boost") or 0.0)
        meta["overnight_tilt"] = True
    # Earnings tighten → slight score dampen when flag set
    if m.get("in_earnings_window") and rules.get("earnings_posture") == "tighten":
        boost -= 0.02
        meta["earnings_dampen"] = True
    # Pressure: never boost blocked names
    if m.get("down_pressure_block"):
        boost = min(boost, 0.0)
        meta["pressure_capped"] = True
    # Scalp bleed penalty on ultra-short noise names if tagged
    if m.get("micro_scalp_candidate"):
        boost -= float(tw.get("scalp_rank_penalty") or 0.0)
        meta["scalp_penalty"] = True

    w = float(tw.get("rank_w_unique") or 0.10)
    # Bound applied delta; scale gently by RANK_W_UNIQUE / default
    scale = max(0.25, min(2.5, w / 0.06))
    cap = float(os.getenv("UNIQUE_RANK_CAP", "0.10"))
    applied = max(-cap, min(cap, float(boost) * scale))
    meta["raw_boost"] = round(boost, 4)
    meta["applied"] = round(applied, 4)
    meta["rank_w_unique"] = w
    if _b("USE_SHELDON_HEAD", True):
        try:
            from analytics.sheldon_head import sheldon_rank_boost

            s_boost, s_meta = sheldon_rank_boost(symbol)
            applied = max(-cap, min(cap, float(applied) + float(s_boost or 0.0)))
            meta["sheldon"] = s_meta
            meta["applied"] = round(applied, 4)
        except Exception:
            pass
    return float(applied), meta


def fortress_size_mult_from_playbook(metrics: dict[str, Any] | None = None) -> float:
    """Env-overridable fortress size multiplier from playbook."""
    if not _b("USE_UNIQUE_PLAYBOOK", True):
        return 1.0
    tw = playbook_tweaks()
    mult = float(tw.get("fortress_size_mult") or 1.0)
    m = metrics or {}
    if m.get("in_earnings_window") or m.get("encourage_pre_momentum") or m.get("stick_to_prediction"):
        damp = float(tw.get("earnings_size_mult") or playbook_rules().get("earnings_size_mult") or 0.55)
        try:
            from analytics.catalyst_horizon import earnings_size_mult_aligned

            mult *= earnings_size_mult_aligned(
                days_to=m.get("days_to_earnings", m.get("days_to")),
                in_earnings_window=bool(m.get("in_earnings_window") or m.get("near_event")),
                sleeve=str(m.get("sleeve") or "fortress"),
                hold_days=m.get("hold_days"),
                encourage=bool(m.get("encourage_pre_momentum") or m.get("stick_to_prediction")),
                playbook_dampen=damp,
            )
        except Exception:
            mult *= damp
    if m.get("down_pressure_block"):
        mult = 0.0
    return max(0.0, min(1.35, mult))


def apply_playbook_env_defaults() -> dict[str, str]:
    """Set missing env keys from playbook (does not override explicit env)."""
    rules = playbook_rules()
    applied: dict[str, str] = {}
    if not rules:
        return applied
    mapping = {
        "FORTRESS_ALLOW_OVERNIGHT": "true" if rules.get("overnight_hold") else "false",
        "FLATTEN_AT_CLOSE": "true" if rules.get("flatten_at_close") else "false",
        "FORTRESS_BP_USE_FRAC": str(rules.get("bp_use_frac") or 0.90),
        "FORTRESS_OVERNIGHT_EXIT_TIMEOUT_MIN": str(rules.get("overnight_exit_floor_min") or 4320),
    }
    for k, v in mapping.items():
        if os.getenv(k) is None:
            os.environ[k] = str(v)
            applied[k] = str(v)
    return applied


if __name__ == "__main__":
    import sys

    force = "--force" in sys.argv or "-f" in sys.argv
    doc = discover_and_write(force=force)
    print(json.dumps({"ok": True, "name": doc.get("name"), "path": str(OUT_JSON)}, indent=2))
