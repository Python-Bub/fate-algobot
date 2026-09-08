# Strategy Centralization (2026)

This project now uses a centralized strategy-family registry and a unified buy-rank pipeline.

## Why

- Avoid duplicate logic paths between `paper_sim_today.py` and `fortress_live.py`
- Prevent silent double-counting (trend + pair + hedge-fund stack together)
- Keep strategy coverage explicit when adding new alpha families

## Core modules

- `analytics/strategy_registry.py`
  - Canonical strategy-family catalog (momentum, mean-reversion, stat-arb, OBI, event-driven, ML, etc.)
  - Runtime mapping (`paper`, `fortress`, `subsecond`, `day_trade`, ...)
- `analytics/rank_pipeline.py`
  - Shared core score primitive
  - Unified ranking extension order
  - Hedge-fund stack applied once

## Runtime integration

- Paper: `paper_sim_today.py` uses unified path when `USE_UNIFIED_RANK_PIPELINE=true`
- Fortress: `fortress_live.py` buy ranking delegates to unified rank pipeline
- Day trade: `analytics/day_trade_ranker.py` now uses the same core score primitive

## Operational commands

- `./run_all.sh strategy-audit`
  - Print strategy families grouped by runtime and key env knobs
- `./run_all.sh train-100gb`
  - Full proper-finish path targeting ~100 GB model footprint

## Research-backed family taxonomy used

The registry follows current practitioner taxonomy:

- trend/momentum
- mean-reversion
- stat-arb/pairs
- market microstructure (order-book imbalance / micro-price)
- market making / liquidity logic
- execution-aware modeling (slippage/impact realism)
- event-driven (earnings/news/sentiment)
- ML ensemble and regime overlays

This keeps new strategy work additive and centralized instead of scattered edits.
