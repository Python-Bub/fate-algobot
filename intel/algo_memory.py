"""Append-only algorithm memory + compact per-issuer summaries.

Corporate actions, power-people hits, and operator notes land in
`data/intel/algo_memory.jsonl`. A rolling summary per canonical ticker lives in
`data/intel/algo_memory_summaries.json` so rankers can read a few bullets instead
of the full log.

Memory never replaces model heads. Dead-money names (cash takeouts) get a hard
negative so we do not keep buying a listing that no longer exists.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from utils import log

ROOT = Path(__file__).resolve().parents[1]
EVENTS_PATH = ROOT / "data" / "intel" / "algo_memory.jsonl"
SUMMARY_PATH = ROOT / "data" / "intel" / "algo_memory_summaries.json"
MAX_BULLETS = 8
MAX_EVENTS_KEEP = 8000


def _enabled() -> bool:
    return os.getenv("USE_ALGO_MEMORY", "true").lower() in ("1", "true", "yes")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canon(ticker: str) -> str:
    t = str(ticker or "").strip().upper()
    if not t:
        return ""
    try:
        from universe_lifecycle.corporate_actions import canonical_symbol

        return canonical_symbol(t)
    except Exception:
        return t


def _events_path() -> Path:
    raw = os.getenv("ALGO_MEMORY_FILE", "")
    return Path(raw) if raw.strip() else EVENTS_PATH


def _summary_path() -> Path:
    raw = os.getenv("ALGO_MEMORY_SUMMARY_FILE", "")
    return Path(raw) if raw.strip() else SUMMARY_PATH


def remember(
    kind: str,
    ticker: str,
    text: str,
    *,
    related: list[str] | None = None,
    source: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append one memory event and refresh the issuer summary."""
    sym = _canon(ticker)
    if not sym:
        return {}
    ev: dict[str, Any] = {
        "ts": _now(),
        "kind": str(kind or "note"),
        "ticker": sym,
        "input": str(ticker or "").strip().upper(),
        "text": str(text or "").strip()[:500],
        "related": [str(x).upper() for x in (related or []) if str(x).strip()][:8],
        "source": str(source or "")[:80],
        "extra": extra or {},
    }
    if not _enabled():
        return ev
    path = _events_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(ev, default=str) + "\n")
    _refresh_summary(sym)
    return ev


def remember_corporate_event(ev: dict[str, Any]) -> None:
    kind = str(ev.get("kind") or "")
    old = str(ev.get("old") or "").upper()
    new = str(ev.get("new") or "").upper()
    note = str(ev.get("note") or "").strip()
    src = str(ev.get("source") or "corporate")
    if kind == "rename" and old and new:
        remember("rename", new, f"{old} renamed to {new}. {note}".strip(), related=[old], source=src)
        remember("rename", old, f"Now listed as {new}. {note}".strip(), related=[new], source=src)
    elif kind == "spinoff" and old and new:
        remember("spinoff", old, f"Spun off {new}. {note}".strip(), related=[new], source=src)
        remember("spinoff", new, f"Spun off from {old}. {note}".strip(), related=[old], source=src)
    elif kind == "merge" and old:
        if new:
            remember(
                "merger",
                old,
                f"Acquired into {new}. {note}".strip(),
                related=[new],
                source=src,
                extra={"dead_money": True},
            )
            remember("merger", new, f"Acquired {old}. {note}".strip(), related=[old], source=src)
        else:
            remember(
                "acquisition_cash",
                old,
                f"Cash takeout / listing ended. {note}".strip(),
                source=src,
                extra={"dead_money": True},
            )
    elif kind == "delist" and old:
        remember(
            "delist",
            old,
            f"Delisted. {note}".strip(),
            source=src,
            extra={"dead_money": True},
        )
    elif kind == "split" and old:
        remember("split", old, f"Split {note}".strip() or "Split", source=src)
    elif kind == "share_class" and old and new:
        remember("share_class", old, f"Dual class with {new}. {note}".strip(), related=[new], source=src)
        remember("share_class", new, f"Dual class with {old}. {note}".strip(), related=[old], source=src)


def _load_events_for(ticker: str, *, limit: int = 80) -> list[dict[str, Any]]:
    path = _events_path()
    if not path.is_file():
        return []
    want = {ticker.upper()}
    try:
        from universe_lifecycle.corporate_actions import related_symbols

        want.update(related_symbols(ticker))
    except Exception:
        pass
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-MAX_EVENTS_KEEP:]
    except Exception:
        return []
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            obj = json.loads(ln)
        except Exception:
            continue
        t = str(obj.get("ticker") or "").upper()
        inp = str(obj.get("input") or "").upper()
        rel = {str(x).upper() for x in (obj.get("related") or [])}
        if t in want or inp in want or (rel & want):
            rows.append(obj)
    return rows[-limit:]


def _refresh_summary(ticker: str) -> dict[str, Any]:
    canon = _canon(ticker)
    events = _load_events_for(canon, limit=60)
    bullets: list[str] = []
    dead = False
    try:
        from universe_lifecycle.corporate_actions import is_dead_money, lineage

        ident = lineage(canon)
        dead = bool(ident.get("dead_money")) or is_dead_money(canon)
        if ident.get("summary"):
            bullets.append(str(ident["summary"]))
        for ft in ident.get("former_tickers") or []:
            bullets.append(f"Former ticker: {ft}")
        if ident.get("spinoff_parent"):
            bullets.append(f"Spun off from {ident['spinoff_parent']}")
        for ch in ident.get("spinoff_children") or []:
            bullets.append(f"Spun off {ch}")
        if ident.get("acquired_into"):
            bullets.append(f"Acquired into {ident['acquired_into']}")
    except Exception as e:
        log.debug("[MEMORY] lineage %s: %s", canon, e)
        ident = {}
    signed = 0.0
    n_signed = 0
    for ev in reversed(events):
        extra = ev.get("extra") or {}
        if extra.get("dead_money"):
            dead = True
        txt = str(ev.get("text") or "").strip()
        if txt and txt not in bullets:
            bullets.append(txt)
        try:
            signed += float(extra.get("direction") or 0.0)
            if extra.get("direction") not in (None, 0, 0.0):
                n_signed += 1
        except (TypeError, ValueError):
            pass
        if len(bullets) >= MAX_BULLETS:
            break
    # unique preserve
    seen: set[str] = set()
    uniq: list[str] = []
    for b in bullets:
        b = b.strip()
        if b and b not in seen:
            seen.add(b)
            uniq.append(b)
        if len(uniq) >= MAX_BULLETS:
            break
    doc = {
        "ticker": canon,
        "dead_money": dead,
        "former_tickers": list(ident.get("former_tickers") or []),
        "related_symbols": list(ident.get("related_symbols") or [canon]),
        "bullets": uniq,
        "n_events": len(events),
        "signed_mean": (signed / n_signed) if n_signed else 0.0,
        "updated_at_utc": _now(),
    }
    path = _summary_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    all_docs: dict[str, Any] = {}
    if path.is_file():
        try:
            all_docs = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(all_docs, dict):
                all_docs = {}
        except Exception:
            all_docs = {}
    all_docs[canon] = doc
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(all_docs, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return doc


def summary_for(ticker: str) -> dict[str, Any]:
    if not _enabled():
        return {"ticker": str(ticker or "").upper(), "disabled": True, "bullets": []}
    canon = _canon(ticker)
    path = _summary_path()
    if path.is_file():
        try:
            all_docs = json.loads(path.read_text(encoding="utf-8"))
            hit = (all_docs or {}).get(canon)
            if isinstance(hit, dict) and hit.get("bullets"):
                return hit
        except Exception:
            pass
    return _refresh_summary(canon)


def bootstrap_corporate_memory() -> int:
    """Once: copy registry events into memory so FB/META summaries exist before the next rename."""
    if not _enabled():
        return 0
    try:
        from universe_lifecycle.corporate_actions import load_registry
    except Exception:
        return 0
    existing: dict = {}
    path = _summary_path()
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8")) or {}
        except Exception:
            existing = {}
    n = 0
    for ev in load_registry().get("events") or []:
        kind = str(ev.get("kind") or "")
        old = str(ev.get("old") or "").upper()
        new = str(ev.get("new") or "").upper()
        keys = [x for x in (new, old) if x]
        if keys and any((existing.get(k) or {}).get("bullets") for k in keys):
            continue
        try:
            remember_corporate_event(ev)
            n += 1
        except Exception:
            continue
    return n


def memory_boost_for(ticker: str) -> float:
    """Bounded [-1, 1]. Dead money is -1. Otherwise a small recency-weighted tilt."""
    if not _enabled():
        return 0.0
    t = str(ticker or "").strip().upper()
    if not t:
        return 0.0
    try:
        from universe_lifecycle.corporate_actions import is_dead_money

        if is_dead_money(t):
            return -1.0
    except Exception:
        pass
    doc = summary_for(t)
    if doc.get("dead_money"):
        return -1.0
    raw = float(doc.get("signed_mean") or 0.0)
    cap = float(os.getenv("ALGO_MEMORY_BOOST_CAP", "0.25"))
    return max(-cap, min(cap, raw))
