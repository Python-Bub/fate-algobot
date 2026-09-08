# Online-RL & Hybrid DNN Master Roadmap

This is the honest tracker for the 15-phase, 150-step blueprint. Every line is one of:

- **DONE** — code exists in this repo and has tests / runtime wiring
- **PARTIAL** — analog exists, doesn't fully match the spec
- **QUEUED** — designed but not coded yet, ordered by leverage
- **NOT-PLANNED** — explicitly out of scope for a single-laptop paper account (the work isn't valuable until you have a budget for clustered infra)

The goal is to keep the bot honest about what's real. We will not ship vaporware modules.

---

## Phase 1 — High-Speed Continuous Ingestion Infrastructure

| # | Step | Status | Notes |
|---|------|--------|-------|
| 1 | Enterprise Linux array, low-latency async I/O | NOT-PLANNED | Single dev machine. Re-evaluate if/when a hosted budget exists. |
| 2 | TimescaleDB / ClickHouse cluster | QUEUED → SQLite/Parquet first | Will add a single-node TimescaleDB shim once we actually need >1 GB/day intra-day data. |
| 3 | TCP order-book sockets | QUEUED | Today we use REST polling (Alpaca/Yahoo). Adding a websocket client to Alpaca quotes is the first realistic step. |
| 4 | Parallel low-latency headline fetch | **DONE** | `intel/headline_fetch_parallel.py` — Finnhub + NewsAPI + Cramer in parallel (`ThreadPoolExecutor`). Wired from `intel/news_factor_engine.py`. Toggle `USE_PARALLEL_NEWS_FETCH`. |
| 5 | High-frequency news webhooks | NOT-PLANNED | Requires paid feed (Benzinga / RavenPack). |
| 6 | RabbitMQ / Kafka broker | NOT-PLANNED | Premature for our throughput. |
| 7 | Topic split | NOT-PLANNED | Same. |
| 8 | Rotating API tokens | PARTIAL | Tokens already in `.env`; rotation is manual. |
| 9 | Auto reconnect | PARTIAL | yfinance/Alpaca clients retry, but no monitor. |
| 10 | NTP daemon | NOT-PLANNED | macOS handles this; not infra we own. |

**Realistic next step**: optional `aiohttp` batch across *many* symbols in one paper-sim pass (still QUEUED); parallel per-symbol fetch is already live.

---

## Phase 2 — NLP & Audio

| # | Step | Status | Notes |
|---|------|--------|-------|
| 11 | GPU cluster | NOT-PLANNED | |
| 12 | FinBERT on GPU | PARTIAL | We use a FinBERT-style scorer in `signals/sentiment_finbert.py` (CPU). |
| 13 | Triton Inference Server | NOT-PLANNED | |
| 14 | News HTML cleaner | DONE | `intel_factors._clean_text`. |
| 15 | Real-time pos/neg/neu scoring | DONE | `signals/sentiment_finbert.py`. |
| 16 | HF tokenizer pipeline | DONE | Inside FinBERT scorer. |
| 17 | Earnings audio scraper | NOT-PLANNED | Need a stable source; SEC doesn't host audio. |
| 18 | Whisper transcription | NOT-PLANNED | Same. |
| 19 | Q&A vs prepared-remarks splitter | QUEUED | Lightweight regex once we have transcripts. |
| 20 | Hesitation/filler-word detector | QUEUED | Trivial when transcripts exist. |

---

## Phase 3 — Math feature store

All ten of these were already shipped in `feature_engineering.build_features` + `feature_store.enrich_features` from prior turns. Status: **DONE**.

| 21–30 | Log returns, multi-window vol, vol-of-vol, price range, intraday spread, position locator, momentum acceleration, range compression, shock state, beta proxy | DONE |

---

## Phase 4 — Alternative data

| # | Step | Status | Notes |
|---|------|--------|-------|
| 31 | Sentiment velocity | DONE | `intel_factors.sentiment_velocity`. |
| 32 | Exponential sentiment decay | DONE | Same module. |
| 33 | News volume impulse | DONE | Same module. |
| 34 | Executive hesitation | QUEUED | Blocked on Phase 2 audio. |
| 34a | **Undercut & Rally pattern (Minervini)** | **DONE** | `signals/undercut_rally.py` — wired into composite + reports. Tests in `tests/integration/test_undercut_rally.py`. |
| 35 | Corporate event alignment (non-destructive) | DONE | `feature_engineering` earnings fillna fixes from prior turn. |
| 36 | Linear days-to-earnings | DONE | `days_to_earnings` w/ `EARNINGS_NEUTRAL_DTE=90`. |
| 37 | Exponential earnings decay | DONE | `earnings_decay` feature. |
| 38 | FRED macro vector | **DONE** | `signals/fred_macro.py` — DGS10, DGS2, optional VIXCLS; `macro_score` + `spread_10y2y`. Cached JSON + in-memory TTL. Wired into `paper_sim_today` composite via `RANK_W_MACRO`. |
| 39 | 10y-2y spread | **DONE** | Same module (`spread_10y2y`). |
| 40 | VIX context | DONE | `regime.simple_regime_from_spy` consumes ^VIX. |

---

## Phase 5 — Non-destructive alignment

| # | Step | Status |
|---|------|--------|
| 41 | Forward-fill merge engine | DONE (in `feature_store`) |
| 42 | Strict shape assertion | DONE |
| 43 | Padding for missing values | DONE (`fillna(0)` for sentiment / 90 for earnings) |
| 44 | shift(1) for look-ahead | DONE |
| 45 | 3-sigma winzorization | PARTIAL — clipping is per-feature ad-hoc; a generic 3σ pass is QUEUED |
| 46 | Future-correlation leakage check | QUEUED — design exists in `tests/integration/test_data_quality.py`, expand. |
| 47 | Index alignment across 11k assets | DONE |
| 48 | Per-ticker completeness logger | PARTIAL — `_score_symbol` logs skips. |
| 49 | Quality-failure feature exclusion | DONE — `_prune_dead_features`. |
| 50 | Serialize aligned matrices | PARTIAL — `feature_store` writes parquet snapshots. |

---

## Phase 6 — DNN architecture

| # | Step | Status | Notes |
|---|------|--------|-------|
| 51–60 | PyTorch hybrid LSTM+attention dual-head net | NOT-PLANNED YET | Until we have ground truth that meta+ensemble has plateaued, adding a 58-d LSTM is premature complexity. The existing meta `LogisticRegression` is what the online updater modifies. When/if we cross AUC≥0.7 sustained, we'll add `models/dnn_torch.py` with policy + value heads. |

---

## Phase 7 — RL environment

| # | Step | Status | Notes |
|---|------|--------|-------|
| 61–70 | Custom Gym env with cost/slippage/time-exhaustion | PARTIAL | `rl_trading_env.py` — `RL_USE_ASYM_REWARD=true` wires `analytics.asymmetric_loss` into `step()` (prev-bar position × return + switch friction). Risk caps still live in `RiskManager`, not yet injected into env. |

---

## Phase 8 — Asymmetric reward

| # | Step | Status |
|---|------|--------|
| 71 | Asymmetric reward engine | **DONE** — `analytics/asymmetric_loss.py` |
| 72 | Profit reward | DONE |
| 73 | Wrong-direction penalty | DONE |
| 74 | 5x failed-long multiplier | DONE (`ASYM_PENALTY_LONG=5.0`) |
| 75 | 10x failed-short multiplier | DONE (`ASYM_PENALTY_SHORT=10.0`) |
| 76 | Friction per side-switch | DONE (`ASYM_FRICTION`) |
| 77 | Sharpe modifier | QUEUED — easy follow-up |
| 78 | Time-decay penalty | DONE (`ASYM_TIME_DECAY`) |
| 79 | Explosive milestone bonus | QUEUED |
| 80 | NaN/inf guards | DONE |

---

## Phase 9 — Stacking ensemble

| # | Step | Status |
|---|------|--------|
| 81–90 | RF/XGB/LGB bases, calibration, time-series CV, meta LR, drop-zero-importance, accuracy logging | DONE in `model_trainer.py`, `ensemble_model.py`, `analytics/meta_stack.py` (prior turns). |

---

## Phase 10 — Asymmetric dual-threshold meta filter

| # | Step | Status |
|---|------|--------|
| 91 | Filter module | **DONE** — `analytics/asymmetric_meta_filter.py` |
| 92 | LONG threshold ≥0.90 | DONE |
| 93 | SHORT threshold ≤0.20 (i.e. p_short ≥ 0.80) | DONE |
| 94 | No-trade zone | DONE (rationale = `in_no_trade_zone`) |
| 95 | Per-day yield monitor | **DONE** | `paper_sim_today` → `asym_filter_metrics` in report JSON + console line (long/short/no-trade counts + zone hit-rates). |
| 96 | Auto-drop ticker if <5 trades | QUEUED |
| 97 | Filtered precision metric | **DONE** | `hypothetical_long_zone_precision` / `hypothetical_short_zone_precision` in `asym_filter_metrics`. |
| 98 | Notification on precision drop | QUEUED — wire into Slack/email when we have a hook |
| 99 | Spike-bypass guard | DONE (filter is purely on probabilities, no price-spike override) |
| 100 | Per-asset filtered precision log | QUEUED |

---

## Phase 11 — Single-step online weight editing

| # | Step | Status |
|---|------|--------|
| 101 | Real-time weight modifier | **DONE** — `online_learning/weight_updater.py` |
| 102 | Online loop on every closed trade | DONE — wired into `paper_sim_today.run_paper_simulation_today` |
| 103 | SGD with `lr=1e-5` | DONE (`ONLINE_LR`) |
| 104 | Cache entry-state vector | DONE — `online_learning/trade_memory.py` |
| 105 | Capture exit reward scalar | DONE — fwd return → `asymmetric_reward` |
| 106 | Single-item batch | DONE |
| 107 | Predict-vs-actual error | DONE |
| 108 | Backprop with asymmetric loss | DONE (target derived from asymmetric reward via `reward_to_target`) |
| 109 | Modify weight matrices | DONE |
| 110 | Weight clipping | DONE (`ONLINE_PARAM_CLIP`, default 10.0) |

---

## Phase 12 — Distributed multiprocessing

| # | Step | Status |
|---|------|--------|
| 111–120 | Ray / multiprocessing pool, GPU partitioning, Redis cache | PARTIAL → `concurrency/signal_bus.py` exists, multi-process trainer is QUEUED |

---

## Phase 13 — Paper trading & execution safeguards

| # | Step | Status |
|---|------|--------|
| 121 | Broker paper API | DONE (Alpaca paper) |
| 122 | Action → order | DONE |
| 123 | Routing + slippage tracker | PARTIAL |
| 124 | Local order book | PARTIAL |
| 125 | 60s reconciliation | QUEUED |
| 126 | Duplicate-order safeguard | DONE in `fortress_live` |
| 127 | Independent stop-loss fallback | PARTIAL |
| 128 | 5-min connectivity emergency exit | QUEUED |
| 129 | Daily perf log | DONE (`reports/`) |
| 130 | 48-h paper sim | RUNBOOK item |

---

## Phase 14 — Risk management

| # | Step | Status | Notes |
|---|------|--------|-------|
| 131 | Institutional risk framework | **PARTIAL → expanded** | `risk_manager.py` — `can_open_explain`, `register_open`, gross exposure accounting, optional sector cap, monthly drawdown gate (file-backed). |
| 132 | Max risk per trade 3% | DONE | `MAX_SINGLE_POSITION_FRAC` / Kelly kernel in `target_notional`; heat cap `MAX_PORTFOLIO_HEAT`. |
| 133 | Per-asset 5% cap | **DONE** | `MAX_SINGLE_ASSET_FRAC` (default 0.05) vs `symbol_gross_exposure`. |
| 134 | Total exposure 70% cap | **DONE** | `MAX_TOTAL_EXPOSURE_FRAC` (default 0.70) vs `total_gross_exposure`. |
| 135 | 10%-monthly drawdown halt | **DONE** | `USE_MONTHLY_DRAWDOWN_HALT` + `MONTHLY_DRAWDOWN_HALT_PCT` + `data/risk/monthly_equity.json` (override path via `MONTHLY_EQUITY_STATE_FILE`). |
| 136 | Sector concentration filter | **DONE** | `USE_SECTOR_RISK` + `SECTOR_MAX_EXPOSURE_FRAC` + yfinance sector cache (`SECTOR_CACHE_FILE`). |
| 137 | Liquidity filter | PARTIAL (volume_ratio) |
| 138 | Trailing stop | PARTIAL |
| 139 | 2-second data-staleness gate | QUEUED |
| 140 | Risk-override audit log | QUEUED |

---

## Phase 15 — Monitoring & continuous optimization

| # | Step | Status | Notes |
|---|------|--------|-------|
| 141 | **Central monitoring dashboard (Streamlit + TradingView candles)** | **DONE** | `dashboard/app.py` — renders today's picks as TradingView Lightweight candle charts with EMA-20/50, U&R pivot line + arrow marker, asym verdict, exec_conf, and online-update overlays. Run with `./venv/bin/python -m streamlit run dashboard/app.py`. |
| 142 | Long/short rolling precision metric cards | **PARTIAL** | Dashboard expander shows `asym_filter_metrics` + `fred_macro` from latest paper-sim JSON. |
| 143 | Gradient-update tracker | DONE | Each pick card shows `delta_l2` and `pre_p → post_p` from the online updater. |
| 144 | Slack/email alert network | QUEUED |
| 145 | Anomaly detection on features/preds | QUEUED |
| 146 | Weekly cleanup of logs/checkpoints | QUEUED |
| 147 | Buy-and-hold benchmark per ticker | QUEUED |
| 148 | Dynamic threshold updater | PARTIAL — `self_modify` exists |
| 149 | Daily remote backup | QUEUED |
| 150 | Full-universe live launch | RUNBOOK item |

---

## What we built today (deltas across turns)

**Turn 1:**
- `analytics/asymmetric_meta_filter.py` — Phase 10 verdict (LONG / SHORT / NO_TRADE)
- `analytics/asymmetric_loss.py` — Phase 8 reward formula
- `online_learning/weight_updater.py` — Phase 11 single-step SGD on meta head
- `online_learning/trade_memory.py` — entry-state cache for online updates
- `paper_sim_today.py` — wired all three
- `tests/integration/test_online_learning.py` — 9 tests passing
- `.env` — Phase 8/10/11 knobs, `USE_ONLINE_UPDATER=false` by default
- `docs/DECISION_LOGIC.md` — sections 2c & 2d added

**Turn 3 (batch — Phases 1 / 4 / 7 / 10 / 14 / 15):**
- `risk_manager.py` — `can_open_explain`, `register_open`, total + per-asset exposure caps, optional sector cap, monthly drawdown gate (JSON state file), `base_symbol` / `get_sector`
- `signals/fred_macro.py` — FRED DGS10/DGS2/VIXCLS bundle + `macro_score`; wired into paper-sim composite + report
- `intel/headline_fetch_parallel.py` — parallel Finnhub/NewsAPI/Cramer fetch; `news_factor_engine` wired
- `paper_sim_today.py` — FRED macro once per run, `_asym_filter_metrics` in JSON + console, `register_open` after each accepted pick/short, `fred_macro` summary block
- `fortress_live.py` — `register_open` after successful BUY
- `rl_trading_env.py` — optional `RL_USE_ASYM_REWARD` path using `asymmetric_reward`
- `dashboard/app.py` — expander for `asym_filter_metrics` + `fred_macro`
- `tests/integration/test_risk_and_fred.py` — risk + FRED + parallel headline tests
- `.env` — Phase 14 / FRED / parallel news / RL env knobs
- `self_modify/change_validator.py` — bounds for new tunables
- `docs/DECISION_LOGIC.md` — sections 17–19 (risk, FRED, parallel news)
- `docs/ONLINE_RL_ROADMAP.md` — status rows updated for Phases 1, 4, 7, 10, 14, 15

## What we are NOT pretending to ship

- We did **not** build a TimescaleDB cluster, RabbitMQ broker, GPU Triton service, NTP daemon, Whisper audio pipeline, or PyTorch LSTM+attention dual-head network. All of those are valid next steps but each is multi-day work that requires real infra and budget; we'll add them deliberately, with tests, when they're justified.
- The "online weight update" only edits the **meta logistic head** (small, linear, safe). It does **not** retrain the boosted bases per trade — doing that would destabilize the system within hours. When we add the PyTorch dual-head net (Phase 6), the same updater pattern extends naturally.

## Recommended next 4 sessions (in order)

1. **Phase 6 — PyTorch hybrid LSTM + dual-head policy/value net** — only after paper-sim meta AUC holds ≥0.65–0.70 for multiple weeks.
2. **Phase 12 — Ray / multi-process trainer** for full-universe nightly retrains + online meta coexistence.
3. **Phase 1 — Alpaca websocket L2 / quotes** + optional single-node TimescaleDB for tick storage.
4. **Phase 13–14 remainder** — 60s broker reconcile, connectivity emergency flatten, risk-override audit JSONL.

After those, the stack is ready for unattended multi-day paper with institutional-grade telemetry.
