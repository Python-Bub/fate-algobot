"""RL-weighted ranking — top picks from Yahoo setup scans."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from analytics.day_trade_setups import SetupScan
from utils import log

ROOT = Path(__file__).resolve().parents[1]
LEADER_PATH = ROOT / "data" / "intel" / "day_trade_leaderboard.json"
POS_PATH = ROOT / "data" / "intel" / "day_trade_positions.json"


@dataclass
class RankedPick:
    ticker: str
    scan: SetupScan
    pattern: str
    rl_weight: float
    final_score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "final_score": round(self.final_score, 4),
            "bias": self.scan.bias,
            "confidence": self.scan.confidence,
            "rl_weight": round(self.rl_weight, 3),
            "pattern": self.pattern,
            "bullish": self.scan.bullish[:8],
            "bearish": self.scan.bearish[:4],
            "last_close": self.scan.last_close,
            "vwap": self.scan.vwap,
        }


def _primary_pattern(scan: SetupScan) -> str:
    for label in scan.bullish:
        if label.startswith("candle_"):
            return label.replace("candle_", "").upper()
    for label in scan.bullish:
        if label not in ("above_vwap", "trend_up"):
            return label.upper()
    return "NONE"


def rl_weight_for_scan(scan: SetupScan) -> float:
    from analytics.jp_candle_rl import pattern_weight

    pat = _primary_pattern(scan)
    w = pattern_weight(pat)
    if os.getenv("DAY_TRADE_USE_NEURAL", "true").lower() in ("1", "true", "yes"):
        try:
            from online_learning.neural_ensemble import neural_ensemble_details

            nb = neural_ensemble_details(
                scan.ticker,
                {
                    "p_up_base": max(0.0, min(1.0, 0.5 + scan.bias * 0.5)),
                    "execution_confidence": scan.confidence,
                    "momentum_5d": scan.details.get("momentum", 0.0),
                    "dip_signal": max(0.0, -scan.bias) if scan.bias < 0 else 0.0,
                },
            )
            if nb and nb.get("ensemble_p_up") is not None:
                nu = float(nb["ensemble_p_up"])
                w *= 0.85 + 0.30 * nu
        except Exception:
            pass
    return w


def final_score(scan: SetupScan) -> float:
    from analytics.rank_pipeline import core_composite_score

    rl_w = rl_weight_for_scan(scan)
    setup_boost = 1.0 + 0.04 * min(len(scan.bullish), 6)
    candle_bonus = 1.12 if any(b.startswith("candle_") for b in scan.bullish) else 1.0
    # Day-trade rank now uses the same core scoring primitive as paper/fortress.
    core = core_composite_score(
        p_up=max(0.0, min(1.0, 0.5 + 0.5 * float(scan.bias))),
        mom_5d=float(scan.details.get("momentum", 0.0)),
        rs_spy=float(scan.details.get("rs_spy", 1.0)),
        vol_ratio=float(scan.details.get("vol_ratio", 1.0)),
        sent=float(scan.details.get("sentiment", 0.0)),
        dip_signal=max(0.0, -float(scan.bias)) if float(scan.bias) < 0 else 0.0,
    )
    return float(core * max(0.1, scan.confidence) * rl_w * setup_boost * candle_bonus)


def rank_scan(scan: SetupScan) -> RankedPick:
    pat = _primary_pattern(scan)
    rl_w = rl_weight_for_scan(scan)
    return RankedPick(
        ticker=scan.ticker,
        scan=scan,
        pattern=pat,
        rl_weight=rl_w,
        final_score=final_score(scan),
    )


def update_leaderboard(picks: list[RankedPick]) -> None:
    LEADER_PATH.parent.mkdir(parents=True, exist_ok=True)
    doc: dict[str, Any] = {"updated_utc": datetime.now(timezone.utc).isoformat(), "picks": {}}
    if LEADER_PATH.is_file():
        try:
            doc = json.loads(LEADER_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    table = doc.setdefault("picks", {})
    now = datetime.now(timezone.utc).isoformat()
    for p in picks:
        table[p.ticker] = {**p.to_dict(), "scored_utc": now}
    doc["updated_utc"] = now
    LEADER_PATH.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def top_picks(*, limit: int | None = None) -> list[RankedPick]:
    if not LEADER_PATH.is_file():
        return []
    try:
        doc = json.loads(LEADER_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    rows = list((doc.get("picks") or {}).values())
    rows.sort(key=lambda r: float(r.get("final_score", 0)), reverse=True)
    n = limit or int(os.getenv("DAY_TRADE_TOP_N", "3"))
    out: list[RankedPick] = []
    for row in rows[:n]:
        sym = str(row.get("ticker", "")).upper()
        if not sym:
            continue
        scan = SetupScan(
            ticker=sym,
            bias=float(row.get("bias", 0)),
            confidence=float(row.get("confidence", 0)),
            bullish=list(row.get("bullish") or []),
            bearish=list(row.get("bearish") or []),
            details={},
            vwap=float(row.get("vwap", 0)),
            last_close=float(row.get("last_close", 0)),
        )
        out.append(
            RankedPick(
                ticker=sym,
                scan=scan,
                pattern=str(row.get("pattern", "NONE")),
                rl_weight=float(row.get("rl_weight", 1)),
                final_score=float(row.get("final_score", 0)),
            )
        )
    return out


def save_position_meta(
    ticker: str,
    *,
    entry_px: float,
    qty: int,
    stop_px: float,
    target_px: float,
    pattern: str,
    final_score: float,
) -> None:
    POS_PATH.parent.mkdir(parents=True, exist_ok=True)
    doc: dict[str, Any] = {}
    if POS_PATH.is_file():
        try:
            doc = json.loads(POS_PATH.read_text(encoding="utf-8"))
        except Exception:
            doc = {}
    legs = doc.setdefault("legs", {})
    legs[ticker.upper()] = {
        "entry_px": entry_px,
        "qty": qty,
        "stop_px": stop_px,
        "target_px": target_px,
        "pattern": pattern,
        "final_score": final_score,
        "opened_utc": datetime.now(timezone.utc).isoformat(),
    }
    doc["updated_utc"] = datetime.now(timezone.utc).isoformat()
    POS_PATH.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    try:
        from analytics.jp_candle_rl import record_signal

        record_signal(ticker, pattern=pattern, bias=1, composite_bias=1, p_adj=final_score)
    except Exception:
        pass


def pop_position_meta(ticker: str) -> dict[str, Any] | None:
    if not POS_PATH.is_file():
        return None
    try:
        doc = json.loads(POS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    legs = doc.get("legs") or {}
    return legs.pop(ticker.upper(), None)


def position_meta(ticker: str) -> dict[str, Any] | None:
    if not POS_PATH.is_file():
        return None
    try:
        doc = json.loads(POS_PATH.read_text(encoding="utf-8"))
        return (doc.get("legs") or {}).get(ticker.upper())
    except Exception:
        return None


def record_exit_learning(ticker: str, entry_px: float, exit_px: float) -> None:
    if entry_px <= 0:
        return
    pnl_frac = (exit_px - entry_px) / entry_px
    meta = pop_position_meta(ticker)
    try:
        from analytics.jp_candle_rl import record_outcome

        record_outcome(ticker, pnl_frac)
    except Exception:
        pass
    try:
        from online_learning.trade_feedback import learn_from_realized_trade

        learn_from_realized_trade(ticker, "LONG", pnl_frac, source="day_trade")
    except Exception:
        pass
    log.info("[DAY_TRADE] RL learn %s pnl=%.3f%% pattern=%s", ticker, 100 * pnl_frac, (meta or {}).get("pattern"))
