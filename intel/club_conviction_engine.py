"""Autonomous conviction picks — generated from live rankings/models, not a static ticker list."""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

from utils import log

ROOT = Path(__file__).resolve().parents[1]
PICKS_PATH = ROOT / "data" / "intel" / "club_proven_picks.json"
RANK_PATH = ROOT / "data" / "intel" / "day_trade_rankings.json"
PLAYBOOK_PATH = ROOT / "data" / "monday_playbook.json"


def _load_picks_doc() -> dict:
    if not PICKS_PATH.is_file():
        return {"picks": [], "updated": "", "mode": "dynamic"}
    try:
        return json.loads(PICKS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"picks": [], "updated": "", "mode": "dynamic"}


def _save_picks_doc(doc: dict) -> None:
    PICKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PICKS_PATH.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def _rank_candidates() -> list[dict]:
    if not RANK_PATH.is_file():
        return []
    try:
        ranks = json.loads(RANK_PATH.read_text(encoding="utf-8")).get("ranks") or {}
    except Exception:
        return []
    min_score = float(os.getenv("CONVICTION_MIN_RANK_SCORE", "0.36"))
    min_bias = float(os.getenv("CONVICTION_MIN_BIAS", "0.42"))
    out: list[dict] = []
    for sym, row in ranks.items():
        score = float(row.get("score") or 0)
        bias = float(row.get("bias") or 0)
        if score < min_score or bias < min_bias:
            continue
        mp = row.get("model_p")
        boost = min(0.62, 0.25 + score * 0.55)
        if mp is not None and float(mp) >= 0.58:
            boost = min(0.72, boost + 0.08)
        out.append(
            {
                "ticker": sym.upper(),
                "boost": round(boost, 3),
                "thesis": f"day_trade rank={score:.2f} bias={bias:.2f}",
                "source": "day_trade_rank",
                "score": score,
            }
        )
    return out


def _playbook_candidates() -> list[dict]:
    path = Path(os.getenv("MONDAY_PLAYBOOK_PATH", str(PLAYBOOK_PATH)))
    if not path.is_file():
        return []
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    min_p = float(os.getenv("CONVICTION_MIN_PLAYBOOK_P", "0.62"))
    out: list[dict] = []
    for p in doc.get("preorders") or []:
        sym = str(p.get("ticker") or "").upper()
        if not sym:
            continue
        p_adj = p.get("p_adj")
        try:
            p_val = float(p_adj)
        except (TypeError, ValueError):
            continue
        if p_val < min_p:
            continue
        out.append(
            {
                "ticker": sym,
                "boost": round(min(0.65, 0.2 + p_val * 0.5), 3),
                "thesis": f"playbook p_adj={p_val:.2f}",
                "source": "playbook",
                "score": p_val,
            }
        )
    return out


def _cramer_email_candidates() -> list[dict]:
    try:
        from intel.morning_club_intel import load_latest
    except Exception:
        return []
    doc = load_latest()
    if not doc.get("tickers"):
        return []
    top_buys = {str(x).upper() for x in (doc.get("top_buys") or [])}
    ai_conf = float(doc.get("ai_confidence") or 0.0)
    out: list[dict] = []
    for sym, row in doc["tickers"].items():
        sent = float(row.get("ai_action_bias", row.get("action_bias", row.get("sentiment", 0))))
        if sym in top_buys:
            sent = max(sent, 0.55)
        if sent < 0.30 and sym not in top_buys:
            continue
        boost = min(0.75, 0.12 + abs(sent) * 0.5)
        if ai_conf >= 0.5:
            boost = min(0.82, boost * (1.0 + 0.2 * (ai_conf - 0.5)))
        if row.get("club_held"):
            boost = min(0.85, boost + 0.1)
        if row.get("catalyst") == "earnings":
            boost = min(0.88, boost + 0.12)
        if sym in top_buys:
            boost = min(0.9, boost + 0.08)
        out.append(
            {
                "ticker": sym.upper(),
                "boost": round(boost, 3),
                "thesis": (row.get("thesis") or doc.get("ai_thesis") or "cramer_ai")[:120],
                "source": "cramer_ai" if "ai" in str(doc.get("parser", "")) else "cramer_email",
                "score": sent,
            }
        )
    return out


def refresh_dynamic_conviction() -> dict:
    """Rebuild conviction list from rankings + playbook + today's Cramer fetch."""
    if os.getenv("USE_CLUB_PROVEN_PICKS", "true").lower() not in ("1", "true", "yes"):
        return {"updated": 0, "skipped": True}

    merged: dict[str, dict] = {}
    for row in _cramer_email_candidates() + _rank_candidates() + _playbook_candidates():
        sym = row["ticker"]
        prev = merged.get(sym)
        if not prev or float(row["boost"]) > float(prev["boost"]):
            merged[sym] = row
        elif prev and row["source"] == "cramer_email":
            prev["thesis"] = row.get("thesis") or prev.get("thesis")

    max_n = int(os.getenv("CONVICTION_MAX_PICKS", "16"))
    # Gate only the top slice — blocks_long can hit news/LLM and must not block forever
    gate_n = int(os.getenv("CONVICTION_GATE_CANDIDATES", str(max(24, max_n * 3))))
    ranked = sorted(merged.values(), key=lambda r: float(r.get("boost", 0)), reverse=True)[:gate_n]

    filtered: list[dict] = []
    for row in ranked:
        sym = str(row.get("ticker", "")).upper()
        try:
            from intel.unified_intel import blocks_long

            blocked, _ = blocks_long(sym)
            if blocked:
                continue
        except Exception:
            pass
        filtered.append(row)

    picks = filtered[:max_n]

    doc = {
        "mode": "dynamic",
        "updated": date.today().isoformat(),
        "refreshed_at_utc": datetime.now(timezone.utc).isoformat(),
        "note": "Auto-generated from Cramer email + day-trade ranks + playbook — not manual",
        "picks": picks,
    }
    _save_picks_doc(doc)
    log.info("[CONVICTION] refreshed %d dynamic picks", len(picks))
    return {"updated": len(picks), "top": [p["ticker"] for p in picks[:6]]}


def proven_pick_boost(symbol: str) -> float:
    sym = symbol.strip().upper()
    gain = float(os.getenv("CLUB_PROVEN_PICK_GAIN", "0.55"))
    for row in _load_picks_doc().get("picks") or []:
        if str(row.get("ticker", "")).upper() == sym:
            return max(-1.0, min(1.0, float(row.get("boost", 0.0)) * gain))
    return 0.0


def proven_pick_tickers() -> list[str]:
    return [
        str(r.get("ticker", "")).upper()
        for r in _load_picks_doc().get("picks") or []
        if str(r.get("ticker", "")).strip()
    ]
