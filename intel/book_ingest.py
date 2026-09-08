"""Ingest pasted investing-book text → structured knowledge for rank/talk/math.

Usage:
  ./venv/bin/python tools/ingest_investing_book.py data/books/investing_guide_part1.md
  ./venv/bin/python -c "from intel.book_ingest import ingest_markdown_file; ingest_markdown_file('data/books/…')"

Leaves hook for follow-up pastes: append parts under data/books/ and re-run.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BOOKS_DIR = ROOT / "data" / "books"
INDEX_PATH = ROOT / "data" / "intel" / "book_ingest_index.json"
STRUCTURED_PATH = ROOT / "data" / "intel" / "book_strategies.json"

# Map chapter keywords → existing investing.catalog / knowledge families
_FAMILY_MAP: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"\b(graham|net[- ]?net|deep value|buffett|moat|contrarian|sotp|turnaround|special situation|asset[- ]based|intrinsic)\b", re.I), "value", "value_investing"),
    (re.compile(r"\b(garp|growth|compounder|secular|hypergrowth|momentum|disruptor|innovation|early[- ]stage|quality growth)\b", re.I), "growth", "growth_investing"),
    (re.compile(r"\b(dividend|income|reit|preferred|covered call|high[- ]yield|bond)\b", re.I), "income", "income_investing"),
    (re.compile(r"\b(quant|factor|stat(?:istical)?\s*arb|risk parity|enhanced index|ai/?ml|hft|algo)\b", re.I), "quant", "quant_investing"),
    (re.compile(r"\b(day trad|swing|position trad|scalp|trend follow|mean reversion|range trad|breakout|news trad|event[- ]driven)\b", re.I), "trading", "trading_styles"),
    (re.compile(r"\b(option|derivative|spread|iron condor|credit spread|debit)\b", re.I), "derivatives", "derivatives"),
    (re.compile(r"\b(short sell|shorting)\b", re.I), "trading", "short_selling"),
    (re.compile(r"\b(macro|fed|rates|geopolit)\b", re.I), "macro", "macro"),
    (re.compile(r"\b(venture|angel|alternative|private equity|vc)\b", re.I), "alt", "alternative"),
]


def books_dir() -> Path:
    BOOKS_DIR.mkdir(parents=True, exist_ok=True)
    return BOOKS_DIR


def next_part_path(stem: str = "investing_guide") -> Path:
    d = books_dir()
    n = 1
    while True:
        p = d / f"{stem}_part{n}.md"
        if not p.exists():
            return p
        n += 1


def save_book_text(text: str, *, path: Path | None = None, stem: str = "investing_guide") -> Path:
    """Save raw paste; returns path. Hook for follow-up messages."""
    p = path or next_part_path(stem=stem)
    p.parent.mkdir(parents=True, exist_ok=True)
    header = (
        f"<!-- ingested_at={time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} "
        f"source=user_paste -->\n\n"
    )
    body = text if text.lstrip().startswith("#") or text.lstrip().startswith("Introduction") else text
    p.write_text(header + body.strip() + "\n", encoding="utf-8")
    return p


def _extract_strategies(text: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for pat, family, sleeve in _FAMILY_MAP:
        hits = sorted({m.group(0).lower() for m in pat.finditer(text)})
        if not hits:
            continue
        key = f"{family}:{sleeve}"
        if key in seen:
            continue
        seen.add(key)
        found.append(
            {
                "family": family,
                "sleeve": sleeve,
                "keywords_hit": hits[:12],
                "fate_hooks": _hooks_for(family, sleeve),
            }
        )
    return found


def _hooks_for(family: str, sleeve: str) -> list[str]:
    hooks = {
        "value": [
            "analytics.value_investing.analyze_value",
            "investing.integrate.book_rank_boost (BOOK_W_VALUE)",
            "investing.knowledge.value",
        ],
        "growth": [
            "investing.formulas.growth",
            "investing.integrate.book_rank_boost (BOOK_W_GROWTH)",
            "investing.knowledge.growth",
        ],
        "income": [
            "investing.formulas.income",
            "investing.integrate.book_rank_boost (BOOK_W_INCOME)",
            "investing.knowledge.income",
        ],
        "quant": [
            "analytics.math_pivot.apply_pivot_to_components",
            "analytics.hedge_fund_stack",
            "investing.knowledge.quant",
            "hft/src/earnings (HFT sleeve)",
        ],
        "trading": [
            "fortress_live (swing/position)",
            "tools/day_trade_daemon.py",
            "tools/micro_scalp_daemon.py",
            "investing.knowledge.trading",
        ],
        "derivatives": ["investing.knowledge.derivatives", "investing.formulas.derivatives"],
        "macro": ["analytics.market_regime_score", "analytics.industries.macro_playbooks"],
        "alt": ["investing.knowledge.alt_passive"],
    }
    return hooks.get(family, [f"investing.knowledge / sleeve={sleeve}"])


def structure_book(text: str, *, source_path: str = "") -> dict[str, Any]:
    strategies = _extract_strategies(text)
    doc = {
        "version": 1,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_path": source_path,
        "n_chars": len(text),
        "strategies": strategies,
        "families": sorted({s["family"] for s in strategies}),
        "use": {
            "rank": "investing.integrate.book_rank_boost + PURE_MATH_PIVOT",
            "fortress": "USE_INVESTING_BOOK=true (default)",
            "talk": "intel.talk_codebase can summarize via book index",
            "more_pastes": "save next part under data/books/ and call ingest_markdown_file",
        },
    }
    return doc


def ingest_markdown_file(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(p)
    text = p.read_text(encoding="utf-8", errors="replace")
    structured = structure_book(text, source_path=str(p.relative_to(ROOT) if p.is_relative_to(ROOT) else p))
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    index = {}
    if INDEX_PATH.is_file():
        try:
            index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        except Exception:
            index = {}
    parts = list(index.get("parts") or [])
    rel = str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)
    parts = [x for x in parts if x.get("path") != rel]
    parts.append(
        {
            "path": rel,
            "ingested_at": structured["updated_at"],
            "n_chars": structured["n_chars"],
            "families": structured["families"],
        }
    )
    index = {
        "version": 1,
        "updated_at": structured["updated_at"],
        "parts": parts,
        "hook": "Paste next chapter → save as data/books/investing_guide_partN.md → tools/ingest_investing_book.py",
    }
    INDEX_PATH.write_text(json.dumps(index, indent=2), encoding="utf-8")

    # Merge strategies across parts
    merged_strats: dict[str, dict[str, Any]] = {}
    if STRUCTURED_PATH.is_file():
        try:
            prev = json.loads(STRUCTURED_PATH.read_text(encoding="utf-8"))
            for s in prev.get("strategies") or []:
                merged_strats[f"{s.get('family')}:{s.get('sleeve')}"] = s
        except Exception:
            pass
    for s in structured["strategies"]:
        merged_strats[f"{s['family']}:{s['sleeve']}"] = s
    out = {
        **structured,
        "strategies": list(merged_strats.values()),
        "families": sorted({s["family"] for s in merged_strats.values()}),
        "parts_indexed": len(parts),
    }
    STRUCTURED_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


def book_strategy_boost_hint(symbol: str) -> dict[str, Any]:
    """Tiny hint for talk / debug — does not replace book_rank_boost."""
    if not STRUCTURED_PATH.is_file():
        return {"loaded": False}
    try:
        doc = json.loads(STRUCTURED_PATH.read_text(encoding="utf-8"))
        return {
            "loaded": True,
            "families": doc.get("families") or [],
            "n_strategies": len(doc.get("strategies") or []),
            "symbol": symbol.strip().upper(),
            "note": "Live boosts via investing.integrate.book_rank_boost",
        }
    except Exception as e:
        return {"loaded": False, "error": str(e)[:80]}
