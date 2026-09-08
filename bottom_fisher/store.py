"""Persist bottom-fisher scan results for paper/fortress integration."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from utils import log

ROOT = Path(__file__).resolve().parents[1]


def store_path() -> Path:
    return Path(os.getenv("BOTTOM_FISHER_STORE", "data/bottom_fisher/latest_scan.json"))


def save_scan(payload: dict) -> Path:
    p = store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(payload)
    payload["saved_at"] = datetime.now(timezone.utc).isoformat()
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, p)
    log.info("[BOTTOM_FISHER] saved %d picks → %s", len(payload.get("picks", [])), p)
    return p


def load_scan() -> dict:
    p = store_path()
    if not p.is_file():
        return {"picks": [], "by_ticker": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"picks": [], "by_ticker": {}}
    picks = data.get("picks") or []
    by_ticker = {str(r.get("ticker", "")).upper(): r for r in picks if r.get("ticker")}
    data["by_ticker"] = by_ticker
    return data


def lookup_ticker(ticker: str) -> dict | None:
    return load_scan().get("by_ticker", {}).get(ticker.strip().upper())
