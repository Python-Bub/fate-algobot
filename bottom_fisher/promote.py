"""Promote bottom-fisher winners into the strong top50-quality training stack.

Does NOT fake market-cap membership. Writes an overlay list and runs
``run_top50_protocol`` (daily + intraday + strong + LSTM) so recovering names
get real multi-horizon heads — never blacklist, never delete models.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from utils import log

ROOT = Path(__file__).resolve().parents[1]
PROMOTED_PATH = ROOT / "data" / "bottom_fisher_promoted.json"


def _load() -> dict:
    if not PROMOTED_PATH.is_file():
        return {"symbols": [], "history": []}
    try:
        return json.loads(PROMOTED_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"symbols": [], "history": []}


def _save(doc: dict) -> None:
    PROMOTED_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROMOTED_PATH.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def record_and_train(symbols: list[str], *, train: bool | None = None) -> dict:
    """Persist promoted tickers and optionally run the top50 training protocol."""
    syms = list(dict.fromkeys(s.strip().upper() for s in symbols if s and s.strip()))
    if not syms:
        return {"promoted": [], "trained": False}
    doc = _load()
    cur = {str(s).upper() for s in doc.get("symbols", [])}
    added = [s for s in syms if s not in cur]
    cur.update(syms)
    hist = list(doc.get("history") or [])
    hist.append({"at": datetime.now(timezone.utc).isoformat(), "added": added, "batch": syms})
    doc["symbols"] = sorted(cur)
    doc["history"] = hist[-40:]
    doc["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save(doc)
    log.info("[BOTTOM_PROMOTE] recorded %d (%d new) → %s", len(syms), len(added), PROMOTED_PATH)

    do_train = (
        train
        if train is not None
        else os.getenv("BOTTOM_FISHER_PROMOTE_TOP50", "true").lower() in ("1", "true", "yes")
    )
    out: dict = {"promoted": syms, "added": added, "trained": False, "protocol": None}
    if not do_train:
        return out
    try:
        from universe_lifecycle.protocol import run_top50_protocol

        cap = int(os.getenv("BOTTOM_FISHER_PROMOTE_TRAIN_CAP", "25"))
        out["protocol"] = run_top50_protocol(syms[:cap])
        out["trained"] = True
    except Exception as e:
        log.warning("[BOTTOM_PROMOTE] protocol failed: %s", e)
        out["error"] = str(e)
    return out
