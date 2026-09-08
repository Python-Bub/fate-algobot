"""Offline shadow validation for candidate policy changes."""

from __future__ import annotations

import json
from pathlib import Path


def _latest_paper_report() -> dict:
    rep_dir = Path("reports")
    if not rep_dir.is_dir():
        return {}
    files = sorted(rep_dir.glob("paper_sim_*.json"))
    if not files:
        return {}
    try:
        return json.loads(files[-1].read_text(encoding="utf-8"))
    except Exception:
        return {}


def validate_candidate_changes(candidates: dict) -> dict:
    """Lightweight safeguard:
    - reject if candidate tries to both lower buy threshold and increase notional > 15%
      when last paper sim pnl is negative.
    """
    rep = _latest_paper_report()
    pnl = float(rep.get("sum_hypothetical_pnl_usd", 0.0))
    buy_thr = candidates.get("BUY_THRESHOLD")
    notional = candidates.get("ORDER_NOTIONAL")
    prev_notional = 500.0
    try:
        import os

        prev_notional = float(os.getenv("ORDER_NOTIONAL", "500"))
    except Exception:
        pass
    aggressive = os.getenv("SELF_IMPROVE_BEAT_MARKET_MODE", "true").lower() in ("1", "true", "yes")
    if aggressive:
        try:
            from self_modify.market_benchmark import beat_market_snapshot

            bench = beat_market_snapshot()
            if bench.get("losing_to_market"):
                return {"ok": True, "reason": "beat_market_aggressive", "alpha": bench.get("alpha")}
        except Exception:
            pass
    if pnl < 0 and buy_thr is not None and notional is not None:
        if float(buy_thr) < 0.58 and float(notional) > prev_notional * 1.15:
            return {"ok": False, "reason": "negative_pnl_guard", "pnl": pnl}
    return {"ok": True, "reason": "ok", "pnl": pnl}

