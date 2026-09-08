"""
Canonical catalog of algorithmic trading strategy families in FATE_AlgoBot.

Maps industry-standard families (momentum, mean-reversion, stat-arb, OBI, etc.)
to implementation modules and runtimes. Use this instead of ad-hoc env sprawl.

Research alignment (2024–2026 quant literature):
  - Momentum/trend: ride persistent directional moves (MACD, EMA stack, RS)
  - Mean reversion: fade stretched moves in range / pairs (z-score, Bollinger)
  - Statistical arbitrage: cointegrated spreads, market-neutral pair z
  - Market microstructure: OBI, tape velocity, micro-price (HFT ms horizon)
  - Event-driven: earnings surprise, news/sentiment catalysts
  - ML ensemble: multi-horizon calibrated heads + online neural adaptation

Johnston essentials (entry / exit / size, persistent inefficiency, Sharpe backtest)
live in analytics/robot_core.py — extras stay additive; do not disable sleeves.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Runtime = Literal["daily", "intraday", "subsecond", "paper", "fortress", "day_trade"]
Horizon = Literal["subsecond", "intraday", "swing", "position"]


@dataclass(frozen=True)
class StrategyFamily:
    id: str
    title: str
    horizon: Horizon
    description: str
    module: str
    runtimes: tuple[Runtime, ...]
    env_enable: str = ""
    env_weight: str = ""
    related: tuple[str, ...] = field(default_factory=tuple)


STRATEGY_CATALOG: tuple[StrategyFamily, ...] = (
    StrategyFamily(
        "ml_horizon_heads",
        "ML horizon heads (1d/5d/20d/60d)",
        "swing",
        "Per-ticker RF+XGB+LGBM calibrated heads; blended p_up.",
        "ml_model.py",
        ("daily", "paper", "fortress"),
        "USE_MULTI_ALGO_FUSION",
    ),
    StrategyFamily(
        "lstm_sequence",
        "LSTM sequence meta-head",
        "swing",
        "PyTorch sequence overlay on daily features.",
        "analytics/lstm_head.py",
        ("daily", "paper", "fortress"),
        "USE_LSTM_HEAD",
        "LSTM_BLEND_WEIGHT",
    ),
    StrategyFamily(
        "neural_ensemble",
        "Online neural ensemble",
        "swing",
        "LSTM/CNN/DQN incremental learner from trade replay.",
        "online_learning/neural_ensemble.py",
        ("daily", "paper", "fortress"),
        "USE_NEURAL_ENSEMBLE",
        "NEURAL_BLEND_WEIGHT",
    ),
    StrategyFamily(
        "momentum_trend",
        "Momentum / trend following",
        "swing",
        "EMA stack, MACD, RS vs SPY, rally continuation.",
        "analytics/hedge_fund_stack.py",
        ("daily", "paper", "fortress", "day_trade"),
        "USE_HEDGE_FUND_STACK",
        "HF_W_TREND",
        ("hedge_fund_stack",),
    ),
    StrategyFamily(
        "mean_reversion",
        "Mean reversion / dip buy",
        "swing",
        "RSI+EMA dip, deep pullback, Bollinger %B, HF mean-rev z.",
        "signals/dip_momentum.py",
        ("daily", "paper"),
        "DIP_ENABLE_DEEP_PULLBACK",
        "RANK_W_DIP",
        ("hedge_fund_stack",),
    ),
    StrategyFamily(
        "stat_arb_pairs",
        "Stat-arb / pairs spread",
        "swing",
        "Log-spread z vs peer (KO/PEP, etc.); market-neutral tilt.",
        "analytics/hedge_fund_stack.py",
        ("daily", "paper"),
        "USE_HEDGE_FUND_STACK",
        "HF_W_STAT_ARB",
    ),
    StrategyFamily(
        "undercut_rally",
        "Undercut & rally (Minervini)",
        "position",
        "Shakeout under pivot low then reclaim — structural reversal.",
        "signals/undercut_rally.py",
        ("daily", "paper"),
        "TRAIN_COMPUTE_UR",
        "RANK_W_UR",
    ),
    StrategyFamily(
        "obi_tape",
        "Order book imbalance + tape burst",
        "subsecond",
        "Weighted L2 OBI + trade velocity burst; IOC limits.",
        "hft/src/obi-tape/obi-tape-signals.ts",
        ("subsecond",),
        "HFT_OBI_ENABLED",
        "OBI_NOTIONAL_USD",
    ),
    StrategyFamily(
        "micro_mean_reversion",
        "Micro mean-reversion scalper",
        "subsecond",
        "JP candle dip + VWAP MR + micro-price probability.",
        "hft/src/obi-tape/micro-mean-reversion.ts",
        ("subsecond",),
        "HFT_MR_ENABLED",
    ),
    StrategyFamily(
        "micro_scalp",
        "Micro-scalp / noise harvest",
        "subsecond",
        "Buy near mid/bid; exit entry + tick-aware epsilon (bps/abs). "
        "High attempt-rate paper sidecar with spread sanity + PDT caps. "
        "Additive to OBI/tape — does not replace them.",
        "analytics/micro_scalp.py",
        ("subsecond", "paper", "day_trade"),
        "MICRO_SCALP_ENABLED",
        "MICRO_SCALP_NOTIONAL",
        ("obi_tape", "micro_mean_reversion"),
    ),
    StrategyFamily(
        "noise_harvest",
        "Noise harvest (alias of micro_scalp)",
        "subsecond",
        "Alias family id for micro-scalp / noise harvesting cadence.",
        "tools/micro_scalp_daemon.py",
        ("subsecond", "paper"),
        "MICRO_SCALP_ENABLED",
        "MICRO_SCALP_TARGET_BPS",
        ("micro_scalp",),
    ),
    StrategyFamily(
        "gainz_v2_intraday",
        "Gainz-style 1m–1h structure/momentum",
        "intraday",
        "Public Smart Money Structure math: ATR-adaptive momentum, 7-TF EMA+VWAP, "
        "CVD, BOS/CHoCH, six-layer filter, ATR stop + R:R target. Rotates the full "
        "trained universe (does not shrink). Feeds day-trade entries and HFT overlay.",
        "analytics/gainz_v2.py",
        ("intraday", "day_trade", "subsecond"),
        "GAINZ_V2_ENABLED",
        "GAINZ_RR",
        ("momentum_trend", "micro_scalp", "obi_tape"),
    ),
    StrategyFamily(
        "earnings_surprise",
        "Earnings surprise event",
        "subsecond",
        "EPS/revenue beat vs consensus; IOC on news wire.",
        "hft/src/earnings/earnings-evaluator.ts",
        ("subsecond",),
        "EARN_SURPRISE_PCT_TRIGGER",
        "EARN_NOTIONAL_USD",
    ),
    StrategyFamily(
        "news_sentiment",
        "News / sentiment / LLM intel",
        "swing",
        "Finnhub, NewsAPI, FinBERT, news AI agent, transcripts.",
        "sentiment_pipeline.py",
        ("daily", "paper", "fortress", "subsecond"),
        "USE_NEWS_AI_AGENT",
        "RANK_W_SENT",
    ),
    StrategyFamily(
        "regime_macro",
        "Regime / macro / HMM",
        "position",
        "SPY HMM, bull/bear score, FRED yield spread.",
        "regime_detector.py",
        ("daily", "paper", "fortress"),
        "USE_MONTHLY_DRAWDOWN_HALT",
        "RANK_W_HMM_REGIME",
    ),
    StrategyFamily(
        "jp_candles",
        "Japanese candlestick patterns",
        "intraday",
        "Hammer, engulfing, etc.; daily + HFT + fortress gate.",
        "analytics/jp_candles.py",
        ("daily", "intraday", "subsecond", "fortress", "day_trade"),
        "FORTRESS_USE_JP_CANDLES",
    ),
    StrategyFamily(
        "structure_patterns",
        "Structure / S/R / swing patterns",
        "swing",
        "HH/HL trend, S/R, double top/bottom, H&S, triangles, breakouts; "
        "optional sequence_discover on returns; candles only as shrunk confirmation.",
        "analytics/structure_patterns.py",
        ("daily", "paper", "fortress", "day_trade"),
        "USE_STRUCTURE_PATTERNS",
        "RANK_W_STRUCTURE",
        ("jp_candles", "sequence_discover"),
    ),
    StrategyFamily(
        "sequence_discover",
        "General sequence discovery (poly/geo/recurrence/power/evolve)",
        "swing",
        "Data-only closed-form / recurrence search on return sequences; "
        "feeds a small bias into structure_patterns when USE_SEQUENCE_DISCOVER.",
        "analytics/sequence_discover.py",
        ("daily", "paper"),
        "USE_SEQUENCE_DISCOVER",
    ),
    StrategyFamily(
        "hidden_pattern_anomaly",
        "Hidden pattern anomalies (idio/vol/regime/iforest/seq)",
        "swing",
        "Subtle historical price connections humans miss; IsolationForest + "
        "idio residual + vol divergence + sequence foreshadow. Cache → rank boost.",
        "analytics/hidden_pattern_anomaly.py",
        ("daily", "paper", "fortress"),
        "USE_HIDDEN_PATTERN_ANOMALY",
        "RANK_W_HIDDEN_ANOMALY",
        ("sequence_discover", "ml_model"),
    ),
    StrategyFamily(
        "market_imbalance",
        "Cross-listing / regional price imbalances",
        "swing",
        "Same company different venue (ADR vs local, share class, dual list) "
        "after FX+ratio; sticky premium or z-shock vs historical parity.",
        "analytics/market_imbalance.py",
        ("daily", "paper", "fortress"),
        "USE_MARKET_IMBALANCE",
        "RANK_W_MARKET_IMBALANCE",
        ("hidden_pattern_anomaly", "stat_arb"),
    ),
    StrategyFamily(
        "cross_company_links",
        "Cross-company linkage math (corr/beta/coint/lead-lag)",
        "swing",
        "Inter-name ties: Pearson/Spearman/Kendall, partial corr, rolling beta+idio, "
        "log-spread z, Engle–Granger cointegration, lead–lag, vol/tail co-move, dCorr.",
        "analytics/cross_company_links.py",
        ("daily", "paper", "fortress"),
        "USE_CROSS_COMPANY_LINKS",
        "RANK_W_CROSS_COMPANY",
        ("hidden_pattern_anomaly", "market_imbalance", "stat_arb_pairs", "industry_comovement"),
    ),
    StrategyFamily(
        "bottom_fisher",
        "Bottom fisher / capitulation recovery",
        "position",
        "Capitulation + catalyst + AI recovery thesis.",
        "bottom_fisher/integrate.py",
        ("paper",),
        "USE_BOTTOM_FISHER",
        "RANK_W_BOTTOM_FISHER",
    ),
    StrategyFamily(
        "industry_comovement",
        "Industry AI / peer comovement",
        "swing",
        "300+ industry buckets; neural classifier blend.",
        "analytics/industry_comovement.py",
        ("daily", "paper"),
        "USE_INDUSTRY_AI",
    ),
    StrategyFamily(
        "hedge_fund_composite",
        "Hedge-fund factor composite",
        "swing",
        "Single weighted stack: mom, value, quality, stat-arb, ETF disloc.",
        "analytics/hedge_fund_stack.py",
        ("daily", "paper", "fortress"),
        "USE_HEDGE_FUND_STACK",
        "RANK_W_HEDGE_FUND",
    ),
    StrategyFamily(
        "classic_quant_features",
        "Classic quant feature pack (train+live)",
        "swing",
        "SMA 50/200 golden cross, volume-confirmed momentum, Bollinger MR, ATR, VWAP, Donchian.",
        "analytics/classic_quant_features.py",
        ("daily", "paper", "fortress"),
        "USE_CLASSIC_QUANT_FEATURES",
        "",
        ("momentum_trend", "mean_reversion"),
    ),
    StrategyFamily(
        "quant_risk",
        "Explicit risk (Kelly/heat/slippage/overfit)",
        "swing",
        "Half-Kelly sizing, heat caps, max DD, slippage estimate, overfit gap warnings.",
        "analytics/quant_risk.py",
        ("daily", "paper", "fortress", "day_trade"),
        "FORTRESS_SKIP_HIGH_SLIPPAGE",
        "MAX_PORTFOLIO_HEAT",
        ("hedge_fund_composite", "regime_macro"),
    ),
    StrategyFamily(
        "value_investing",
        "Classic value / DCF intrinsic value",
        "position",
        "Book DCF: IV=Σ CF_t/(1+r)^t + TV/(1+r)^n, TV=CF_n(1+g)/(r−g); "
        "Graham Net-Net, deep value (low P/E + P/B<1), Buffett quality, contrarian.",
        "analytics/value_investing.py",
        ("daily", "paper", "fortress"),
        "USE_VALUE_INVESTING",
        "RANK_W_VALUE",
        ("mean_reversion", "bottom_fisher"),
    ),
    StrategyFamily(
        "investing_book",
        "Full investing-book composite",
        "position",
        "GARP/PEG, Gordon dividend, Fama-French-style tilts, technical RSI/MACD/z; "
        "taxonomy in investing/catalog.py (strategies+assets+sectors+analysis).",
        "investing/integrate.py",
        ("daily", "paper", "fortress"),
        "USE_INVESTING_BOOK",
        "RANK_W_BOOK",
        ("value_investing", "factor", "garp"),
    ),
    StrategyFamily(
        "open_web_intel",
        "Wikipedia / SEC / analyst consensus",
        "swing",
        "Public Wikipedia summaries, EDGAR 8-K/Form 4, Yahoo Street ratings. "
        "No LinkedIn scraping. Cached + paced so 429s rotate to cache.",
        "intel/open_web_intel.py",
        ("daily", "paper", "fortress"),
        "OPEN_WEB_INTEL_ENABLED",
        "UNIFIED_OPEN_WEB_BLEND",
        ("news_sentiment",),
    ),
    StrategyFamily(
        "crypto_spot",
        "Alpaca crypto spot (BTC/ETH/SOL/…)",
        "swing",
        "Yahoo BTC-USD bars, Alpaca BTC/USD orders. Dollar/rates/ETF-flow/breakout math "
        "in analytics/crypto_math.py. Additive sleeve, not a shrink of equities.",
        "alt_assets.py",
        ("daily", "paper", "fortress"),
        "TRADE_CRYPTO",
        "RANK_W_ALT_DRIVERS",
        ("classic_quant_features",),
    ),
    StrategyFamily(
        "crypto_hft_experimental",
        "Experimental crypto HFT sidecar (tiny paper clips)",
        "subsecond",
        "Separate from IEX OBI. Alpaca crypto quotes + crypto_math gate. GTC fill-persist, "
        "does not add into fortress BTC. CRYPTO_HFT_EXPERIMENTAL.",
        "tools/crypto_hft_daemon.py",
        ("paper", "day_trade"),
        "CRYPTO_HFT_EXPERIMENTAL",
    ),
    StrategyFamily(
        "commodity_etf",
        "Commodity ETFs (silver, gold, oil, ag, bitcoin ETFs)",
        "swing",
        "SLV/GLD/USO/UNG/IBIT with per-metal math: silver=GSR+copper+DXY+rates; "
        "gold=real rates+DXY+VIX; oil=trend+XLE+DXY. Miners get 0.45x the metal.",
        "analytics/commodity_math.py",
        ("daily", "paper", "fortress"),
        "TRADE_COMMODITIES",
        "RANK_W_ALT_DRIVERS",
        ("classic_quant_features", "structure_patterns"),
    ),
)


def catalog_by_id() -> dict[str, StrategyFamily]:
    return {s.id: s for s in STRATEGY_CATALOG}


def families_for_runtime(runtime: Runtime) -> list[StrategyFamily]:
    return [s for s in STRATEGY_CATALOG if runtime in s.runtimes]


def strategy_ids_for_runtime(runtime: Runtime) -> list[str]:
    return [s.id for s in families_for_runtime(runtime)]
