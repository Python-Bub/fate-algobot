"""Structured trading pipeline: features → models → signals → risk → execution.

This module does not replace fortress_live / paper_sim; it documents and exposes
the canonical stage order so sleeves stay modular and mathematical.

Stages
------
1. **Features** — ``feature_engineering.build_features`` / intraday FE
2. **Models** — daily/short/long + LSTM + neural ensemble (``ml_model``, ``lstm_head``)
3. **Signal aggregator** — ``analytics.rank_pipeline.build_buy_rank`` (weights ∈ ℝ, gated)
4. **Risk / portfolio** — ``RiskManager`` + ``fortress_portfolio.fortress_order_notional``
5. **Execution** — Alpaca/IBKR / HFT sleeves (async trainers never block this loop)
6. **Algorithm factory** — ``analytics.algo_generation.run_generation`` distills a student
   from old per-ticker models (11 phases) and enqueues the next train batch forever.
   New generations mint only when teacher rows change; live rank stays on ``current.json``
   until freeze-train OOS beats the teacher.


State flags
-----------
Use ``model_ready(symbol)`` before consuming predictions in a live loop.
Heavy training belongs in background daemons (``parallel_train``, ``train-lstm``).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from utils import log


@dataclass
class PipelineDecision:
    ticker: str
    p_up: float
    score: float
    notional: float
    ok: bool
    reason: str
    meta: dict[str, Any]


def model_ready(ticker: str) -> bool:
    """Thread-safe readiness: daily bundle present (LSTM optional but preferred)."""
    try:
        from model_trainer import training_saved_model

        if not training_saved_model(ticker):
            return False
        if os.getenv("PIPELINE_REQUIRE_LSTM", "false").lower() in ("1", "true", "yes"):
            from analytics.lstm_head import has_lstm_head

            return has_lstm_head(ticker)
        return True
    except Exception:
        return False


def aggregate_signal(
    ticker: str,
    *,
    p_up: float,
    exec_conf: float,
    sent: float = 0.0,
    row=None,
    closes=None,
    mom_5d: float = 0.0,
    rs_spy: float = 1.0,
    vol_ratio: float = 1.0,
    dip_signal: float = 0.0,
    top100: bool = False,
) -> tuple[float, dict]:
    """Normalize model outputs into a rank score via the shared rank pipeline."""
    try:
        from analytics.rank_pipeline import RankInputs, build_buy_rank, use_unified_rank

        if use_unified_rank():
            rank = build_buy_rank(
                RankInputs(
                    ticker=ticker,
                    p_up=float(p_up),
                    exec_conf=float(exec_conf),
                    sent=float(sent),
                    mom_5d=float(mom_5d),
                    rs_spy=float(rs_spy),
                    vol_ratio=float(vol_ratio),
                    dip_signal=float(dip_signal),
                    row=row,
                    closes=closes,
                    top100=bool(top100),
                ),
                runtime="live",
            )
            return float(rank.score), dict(rank.meta or {})
    except Exception as e:
        log.debug("[PIPELINE] rank fallback %s: %s", ticker, e)
    # Mathematical fallback: map p_up to [-1, 1] weight then to score
    w = max(-1.0, min(1.0, (float(p_up) - 0.5) * 2.0)) * float(exec_conf)
    return float(w), {"fallback": True, "weight": w}


def risk_size(
    rm,
    ticker: str,
    score: float,
    px: float,
    *,
    portfolio_ctx: dict | None = None,
    scale: float = 1.0,
    existing_mv: float = 0.0,
    existing_gain: float | None = None,
    p_adj: float | None = None,
) -> PipelineDecision:
    """Apply portfolio / heat caps before any order is built.

    Maps score → p_adj when needed: score≈0 → p≈0.5, higher scores → higher p_adj.
    """
    try:
        from fortress_portfolio import can_add_position, fortress_order_notional

        ctx = dict(portfolio_ctx or {"equity": getattr(rm, "equity", 100_000.0)})
        # Fortress sizing is conviction-driven off p_adj ∈ (0.5, 1]
        _p = float(p_adj) if p_adj is not None else min(0.99, 0.5 + max(0.0, float(score)) * 0.25)
        notional = float(
            fortress_order_notional(
                ticker=ticker,
                p_adj=_p,
                scale=float(scale),
                portfolio=ctx,
                existing_mv=float(existing_mv),
                existing_gain=existing_gain,
            )
        )
        if notional <= 0:
            return PipelineDecision(ticker, _p, score, 0, False, "zero_notional", {})
        stop = px * (1.0 - float(os.getenv("ATR_STOP_FALLBACK_FRAC", "0.03")))
        if not can_add_position(rm, ticker, notional, px, stop, float(existing_mv)):
            return PipelineDecision(ticker, _p, score, notional, False, "risk_block", {})
        return PipelineDecision(ticker, _p, score, notional, True, "ok", {})
    except Exception as e:
        return PipelineDecision(ticker, 0, score, 0, False, f"risk_error:{e}", {})
