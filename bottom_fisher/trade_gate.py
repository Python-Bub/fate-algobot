"""Decide whether a bottom-fisher pick is eligible for paper trading (post deep scan)."""

from __future__ import annotations

import os
from typing import Any

from bottom_fisher.config import BottomFisherConfig


def trade_eligible(row: dict[str, Any], cfg: BottomFisherConfig | None = None) -> bool:
    """Extraordinary bar: AI buy A/B or strong recovery + catalyst without reject."""
    cfg = cfg or BottomFisherConfig.from_env()
    comp = float(row.get("composite_score", 0))
    rec = float(row.get("recovery_score", 0))
    cat = float(row.get("catalyst_score", 0))
    verdict = str(row.get("ai_verdict", "hold")).lower()
    grade = str(row.get("ai_grade", "C")).upper()[:1]
    conf = float(row.get("ai_confidence", 0))

    if verdict == "reject" and conf >= 0.5:
        return False

    min_comp = float(os.getenv("BOTTOM_FISHER_MIN_TRADE_COMPOSITE", "0.52"))
    min_rec = float(os.getenv("BOTTOM_FISHER_MIN_TRADE_RECOVERY", "0.45"))
    min_cat = float(os.getenv("BOTTOM_FISHER_MIN_TRADE_CATALYST", "0.12"))
    buy_conf = float(os.getenv("BOTTOM_FISHER_AI_BUY_CONF", "0.55"))

    ai_buy = verdict == "buy" and grade in ("A", "B") and conf >= buy_conf
    extraordinary = (
        comp >= min_comp
        and rec >= max(min_rec, cfg.min_recovery_score)
        and (cat >= min_cat or bool(row.get("news_trigger")))
        and verdict != "reject"
    )
    if not (ai_buy or extraordinary):
        return False

    ret_1d = float(row.get("ret_1d", 0))
    ret_5d = float(row.get("ret_5d", 0))
    ret_20d = float(row.get("ret_20d", 0))
    try:
        from signals.dip_momentum import blocks_bottom_fisher_trade

        blocked, reason = blocks_bottom_fisher_trade(
            ret_1d=ret_1d,
            ret_5d=ret_5d,
            ret_20d=ret_20d,
            recovery_score=float(rec),
            reversal_bar=float(row.get("reversal_bar", 0) or 0),
            trend_stabilizing=float(row.get("trend_stabilizing", 0) or 0),
            momentum_turn_score=float(row.get("momentum_turn_score", 0) or 0),
        )
        if blocked:
            return False
    except Exception:
        pass

    sym = str(row.get("symbol") or row.get("ticker") or "").upper()
    if sym:
        try:
            from intel.algo_risk_filter import blocks_buy

            if blocks_buy(sym)[0]:
                return False
        except Exception:
            pass
    return True
