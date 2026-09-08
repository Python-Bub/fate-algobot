"""Johnston robot essentials — entry, exit, size. Not a fourth stack.

Investopedia (Matthew Johnston, 2025): a trading robot is code that generates
and executes buy/sell signals with three components:

  1. Entry rules — when to buy or sell
  2. Exit rules — when to close
  3. Position sizing — how much

Strategies must hunt *persistent* inefficiencies (technical, statistical,
fundamental, news/macro, microstructure), be backtested (Sharpe, not
overfit), paper-traded, then monitored live.

This module does not disable HFT, day-trade, fortress, LSTM, or Gainz.
It names the core contract so extras stay additive instead of the main path.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = ROOT / "data" / "ops" / "robot_core.json"

# Johnston's five strategy types → families we already run (optimize, never remove).
JOHNSTON_TYPES: dict[str, tuple[str, ...]] = {
    "technical": (
        "momentum_trend",
        "classic_quant_features",
        "gainz_v2_intraday",
        "jp_candles",
        "structure_patterns",
        "mean_reversion",
    ),
    "statistical": (
        "stat_arb_pairs",
        "cross_company_links",
        "market_imbalance",
        "hedge_fund_composite",
    ),
    "fundamental": ("earnings_surprise", "value_investing", "investing_book"),
    "news_macro": ("news_sentiment", "regime_macro", "open_web_intel"),
    "microstructure": ("obi_tape", "micro_mean_reversion", "micro_scalp"),
}

# The three rules, per live sleeve. Implementations stay in those modules.
SLEEVES: dict[str, dict[str, str]] = {
    "day_trade": {
        "entry": "analytics.day_trade_setups.scan_setups + day_trade_rank",
        "exit": "analytics.day_trade_engine stop/target (Gainz ATR+R:R when present)",
        "size": "analytics.day_trade_risk.size_position (1% risk, notional cap)",
        "inefficiency": "1m–1h structure/momentum (persistent, not one-print news)",
        "paper": "DAY_TRADE_MODE paper Alpaca",
    },
    "fortress": {
        "entry": "fortress_live rank + BUY_THRESHOLD (ML heads + technical/stat stack)",
        "exit": "fortress_live thesis stop / hygiene (overnight holds allowed)",
        "size": "analytics.quant_risk.half_kelly + heat cap + MAX_ORDER_NOTIONAL",
        "inefficiency": "multi-day forecastable drift + factor tilts",
        "paper": "PAPER_USE_FORTRESS",
    },
    "hft": {
        "entry": "hft/src/obi-tape OBI + tape burst",
        "exit": "IOC unfilled cancel + target/stop bps",
        "size": "OBI_NOTIONAL_USD / HFT_MAX_ORDER_NOTIONAL",
        "inefficiency": "order-book imbalance (microstructure, persistent at ms)",
        "paper": "subsecond-obi paper",
    },
    "gainz_1m_1h": {
        "entry": "analytics.gainz_v2.assess BUY/SELL ≥ GAINZ_MIN_LAYERS",
        "exit": "ATR stop × GAINZ_ATR_STOP_MULT, target GAINZ_RR",
        "size": "day_trade_risk.size_position when routed through day-trade",
        "inefficiency": "volatility-adaptive momentum + 7-TF EMA/VWAP + CVD",
        "paper": "GAINZ_V2_ENABLED",
    },
}

CORE_FAMILY_IDS: tuple[str, ...] = (
    "momentum_trend",
    "classic_quant_features",
    "stat_arb_pairs",
    "gainz_v2_intraday",
    "obi_tape",
    "earnings_surprise",
    "news_sentiment",
    "quant_risk",
)


def catalog_coverage() -> dict[str, Any]:
    from analytics.strategy_registry import catalog_by_id

    have = set(catalog_by_id())
    buckets: dict[str, dict[str, Any]] = {}
    missing_buckets: list[str] = []
    for name, ids in JOHNSTON_TYPES.items():
        present = [i for i in ids if i in have]
        buckets[name] = {"present": present, "expected": list(ids), "ok": bool(present)}
        if not present:
            missing_buckets.append(name)
    core_missing = [i for i in CORE_FAMILY_IDS if i not in have]
    return {
        "johnston_buckets": buckets,
        "missing_buckets": missing_buckets,
        "core_families_missing": core_missing,
        "sleeves": SLEEVES,
        "components": ("entry", "exit", "size"),
    }


def write_status() -> dict[str, Any]:
    doc = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "source": "Investopedia Johnston 2025 — entry/exit/size + persistent inefficiency",
        **catalog_coverage(),
        "backtest": "backtest.py performance_stats (Sharpe, max DD, hit rate)",
        "paper_first": True,
        "own_model": "analytics.gainz_local_brain — local weights, no vendor 429",
        "do_not_disable": ("fortress", "hft", "day_trade", "lstm", "gainz"),
    }
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return doc
