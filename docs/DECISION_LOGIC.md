# FATE_AlgoBot — Decision Logic

This is a single-page explanation of how the bot decides BUY / SHORT / HOLD / SELL_SIGNAL on a given symbol on a given day. Same logic is used by `paper-sim` (hypothetical) and `fortress-live` (real Alpaca paper/live orders).

## 1. Inputs (per symbol, per day)

For every ticker T we compute a `df` of daily bars from `start_hist` (default 2018-01-01) up to "today" (last available bar). We use the **bar T-1** as the signal bar and realize on **bar T**, so there is no look-ahead.

**Raw features** (in `feature_engineering.build_features`):
- `rsi` — Wilder's RSI(14), strictly bounded to [0, 100].
- `volatility` — 20-day rolling std of returns.
- `vol_ch` — change in volatility (clipped to ±5 to defend against splits).
- `price_range` — (High-Low)/Close, clipped to [0, 1].
- `lag_{1,2,3}_return` — 1/2/3-day percent returns (clipped to ±50% to defend against splits).
- `lag_{1,2,3}_sentiment`, `sentiment` — **0.0 in training data on purpose**: we don't backfill historical news. The live picker overwrites these with `composite_sentiment(T)` at decision time using Finnhub + NewsAPI + (optional) Cramer mentions, scored by FinBERT or keyword fallback.
- `is_earnings_day`, `days_to_earnings` — populated only when `ENABLE_EARNINGS_FEATURES=true`.

**Enriched features** (in `feature_store.enrich_features`):
- `ret_lag_{1,2,5}`, `ret_z`, `rsi_z` — z-scored versions for cross-stock comparability.
- `atr_14` — Average True Range, used for stop placement.
- `vwap_est`, `ad_line`, `volume_ratio` — liquidity / accumulation context.
- `ema_20`, `ema_50`, `daily_bull_trend` — trend filter.
- `rs_spy` — relative strength vs SPY over 20 days.

## 2. Model output

We train **two heads** per ticker (RandomForest + XGBoost + LightGBM, isotonically calibrated):
- **Short head** (`model_short`): predicts P(close_{T+1} > close_T).
- **Long head** (`model_long`): predicts P(close_{T+H} > close_T) where H = `LONG_HORIZON_DAYS` (default 20).

In `ml_model.predict_row` we blend them:

```
p_up = w_s * p_short + (1 - w_s) * p_long      # w_s = SHORT_MODEL_WEIGHT, default 0.55
p_down = 1 - p_up
```

If `|p_up - 0.5| < RL_UNCERTAIN_BAND` (default 0.06), we ask a PPO RL hint from `models/{T}_ppo.zip` (if present) and shift `p_up` slightly toward the RL action.

### 2b. Execution confidence (95%+ gate, tunable trade volume)

Raw `p_up` often sits near **0.5** even when short/long models agree. For **routing** we compute a separate score `execution_confidence` ∈ [0, 1] in `analytics/execution_confidence.py`:

- **Extremity**: `0.5 + 2 * |p_up - 0.5| * EXEC_CERTAINTY_GAIN` (capped at 1.0) — higher `EXEC_CERTAINTY_GAIN` pushes middling probabilities toward the 0.95 bar (more permissive for the same raw `p_up`).
- **Agreement**: blend with how aligned `p_short` and `p_long` are with the final direction (`EXEC_AGREE_BLEND`, default 0.35).

Gating modes (`CONFIDENCE_GATE_MODE`):

- **`exec_only`** (default): BUY / paper picks use `execution_confidence >= MIN_EXECUTION_CONFIDENCE` (default 0.95). Raw `PAPER_SIM_MIN_CONF` still feeds fusion and reporting.
- **`dual`**: require both raw `p_up` floor and execution floor.
- **`raw_only`**: legacy behavior, raw `p_up` only.

Disable the execution gate entirely with `USE_EXECUTION_CONFIDENCE_GATE=false`.

### 2c. Asymmetric dual-threshold meta filter (Phase 10)

Per the master online-RL blueprint, after `execution_confidence` we run an explicit asymmetric verdict in `analytics/asymmetric_meta_filter.py`:

- **LONG** if `p_up >= LONG_DECISION_THRESHOLD` (default 0.90)
- **SHORT** if `1 - p_up >= SHORT_DECISION_THRESHOLD` (default 0.80, i.e. `p_up <= 0.20`)
- **NO_TRADE** otherwise (the explicit no-trade zone)

If `ASYM_REQUIRE_EXEC_CONF=true` (default), `exec_conf` must also clear `MIN_EXECUTION_CONFIDENCE` or the verdict downgrades to `NO_TRADE` regardless of which side hit. This filter sits *after* execution confidence but *before* picking — long picks (`top_k`/`all_good`/`gates`) require `asym_action == LONG`, short picks require `asym_action == SHORT`. Disable with `USE_ASYM_META_FILTER=false`.

### 2d. Asymmetric loss + online single-step weight updater (Phase 8 + 11)

When `USE_ONLINE_UPDATER=true`, every paper-sim BUY/SHORT row runs the loop:
1. `analytics/asymmetric_loss.asymmetric_reward(side, fwd_return)` — losses on shorts are penalized 10x, losses on longs 5x, profits scaled 1x. `ASYM_FRICTION` and `ASYM_TIME_DECAY` shave the reward.
2. `online_learning/weight_updater.online_update_meta_for_trade(...)` loads that ticker's meta `LogisticRegression`, runs **one** SGD step (default `lr=1e-5`) on (coef, intercept) using the trade outcome as the label, clips weights, and persists the updated meta. The deep ensemble bases stay frozen — only the small linear head re-shapes per trade.

`reports/paper_sim_*.json` now records `online_updates_applied` / `online_updates_attempted` and per-trade `delta_l2`/`pre_p`/`post_p`. Start with `USE_ONLINE_UPDATER=true` only in paper.

### 2e. Undercut & Rally pattern (Minervini, Phase 4 alt-data)

`signals/undercut_rally.py` detects the classic O'Neil/Minervini "undercut and rally" reversal:

1. Find the **most recent local swing-low pivot** in the bars `[UR_MIN_PIVOT_AGE, UR_MAX_BARS_PAST_PIVOT]` ago (a bar whose Low is the minimum of the ±`UR_PIVOT_WINDOW` window — a true pivot, not just an absolute min).
2. **Today's Low must undercut** the pivot Low (shake-out).
3. **Today's Close must reclaim** above the pivot Low (the rally).
4. Optionally require trend intact: today's Close must be within `UR_INVALIDATE_PCT` (default 7%) of EMA-50, otherwise the score is suppressed.
5. Score in [0,1] = weighted blend of undercut depth (40%), reclaim strength (40%), and volume expansion vs 20-day average (20%), times a trend bonus.

The U&R score feeds the composite ranking via `RANK_W_UR` (default 0.25), and every paper-sim row carries `ur_score`, `ur_pivot_low`, `ur_pivot_age_bars`, `ur_undercut_depth_pct`, `ur_reclaim_pct`, `ur_volume_expansion`, `ur_trend_ok`, and `ur_rationale` for the dashboard / audit.

## 3. Composite ranking score

Pure `p_up` is great but not enough — we want to rank ~11k symbols. So we add a tunable score (in `paper_sim_today._composite_score`):

```
score =
    RANK_W_PUP  * (p_up - 0.5) * 2
  + RANK_W_MOM  * tanh(momentum_5d * 10)
  + RANK_W_RS   * tanh((rs_spy - 1.0) * 3)
  + RANK_W_VOL  * tanh(max(volume_ratio - 1, 0))
  + RANK_W_SENT * tanh(sentiment)
  + RANK_W_DIP  * dip_signal
  + RANK_W_FUND * fund_score
```

`dip_signal` ∈ [0, 1] fires when:
- `rsi <= 35` (oversold)
- `ema_20 > ema_50` (still in an uptrend on the daily)
- last close at least −3% off the 20-day rolling high (i.e. an actual pullback)

So a true "buy the dip in an uptrend" pattern boosts the score. We do NOT boost the score for falling knives (RSI low + downtrend), because the EMA filter zeros it out.

`fund_score` is a 50/50 mix of value (low PE / PB) and quality (high ROE / margins / growth, low debt) from yfinance fundamentals.

## 4. Mode-specific selection

Set with `PAPER_SIM_MODE` (env). All modes share the same scoring; they differ in how aggressively they pick.

### `gates` (strict / Fortress)
A symbol must pass ALL of:
- `p_up >= PAPER_SIM_MIN_CONF` (default 0.55)
- not blocked by negative sentiment (`SENTIMENT_BLOCK_LONG=true` and score < `SENTIMENT_BLOCK_THRESHOLD`)
- volume confirmed (`volume_ratio >= VOLUME_CONFIRM_MULT`, default 1.5)
- multi-timeframe ok (optional, `PAPER_SIM_USE_MTF=true`)
- regime not bearish (`scale > 0`)
- risk manager `can_open` (heat cap + ATR stop)

If all pass: **BUY**. Otherwise: HOLD or SELL_SIGNAL.

### `top_k`
Rank by `score` desc, take the first `PAPER_SIM_TOP_K` (default 10) that pass the **confidence gate** (`passes_confidence_gates` — default: `execution_confidence >= MIN_EXECUTION_CONFIDENCE`) and risk check. If the filtered pool is empty and `PAPER_RELAX_CONF_IF_EMPTY=true`, fall back to pure rank so `top_k` still fills slots.

### `all_good` (default)
Take everything with `p_up >= min_conf` AND `score >= PAPER_SIM_MIN_SCORE` (default 0.0) AND not sentiment-blocked. If the pool ends up empty, fall back to top-25 by score so we always have something.

## 5. Optional shorts pass

Set `PAPER_SIM_ALLOW_SHORTS=true`. We additionally short symbols where:
- `p_down >= max(min_conf, PAPER_SIM_SHORT_MIN_CONF)` (default 0.55)
- `score <= PAPER_SIM_SHORT_MAX_SCORE` (default −0.10)
- not in an earnings window (`days_to_earnings > 5`) — earnings prints are too whippy for a directional short.
- not crypto (Alpaca spot can't short crypto).
- not already a long pick.

We rank by most negative score and take the worst `PAPER_SIM_SHORT_TOP_K` (default 5).

## 6. Sizing

- `PAPER_SIM_USE_NOTIONAL=true` (default) → every position uses `ORDER_NOTIONAL` (default $500) of buying power. Translates into Alpaca's fractional `notional` field, so even a $3,000 share like AVGO gets a true $500 sliver.
- Otherwise we use `ORDER_QUANTITY` whole shares × regime scale.

For shorts the same notional is applied with the sign flipped on PnL.

## 7. PnL accounting (paper-sim only)

```
hypo_long  = + fwd_1d_return * notional
hypo_short = − fwd_1d_return * notional
```

These are gross (no fees, no slippage, no borrow costs) — they show **edge**, not realistic returns.

## 8. Sell logic in live mode

In live mode (`fortress-live` / `live-market`), an open long is exited when:
- `p_up <= 1 − min_conf` (model flipped against us), OR
- price hits the ATR-based stop (`sig_close − ATR*1.5*regime.stop_widen`), OR
- a take-profit trigger fires (riding winners — set via `TRAIL_STOP_PCT` and `TRAIL_TRIGGER_PCT`).

A short is exited when `p_up >= min_conf` or stop is breached (entry × 1.10 by default).

## 9. The "definite market winner"

Independent of our picks, we publish the highest `fwd_1d_return` symbol from the scored universe (top of the leaderboard). It's the explicit answer to "what *did* go up the most today" — useful as an opportunity-cost benchmark when our picks lag.

## 10. Crypto

Crypto pairs (`BTC-USD`, `ETH-USD`, ...) live in `crypto_universe.CRYPTO_YAHOO`. Train them with `python FATE_AlgoBot.py train-crypto` (uses Yahoo for history, no Alpaca data subscription required). At order time `alpaca_broker._route_symbol` translates `BTC-USD` → `BTC/USD` and `_tif` switches to `gtc` (Alpaca crypto requires GTC).

## 11. Failure handling

If a single ticker can't train (e.g. only 1 sample in one class — happens for newly-listed warrants), it's now logged as `failed` in `data/train_checkpoint.json` and skipped on resume. To retry only failed: `RESET_FAILED=true python FATE_AlgoBot.py train-universe`. To wipe the entire checkpoint: `RESET_TRAINING=true python FATE_AlgoBot.py train-universe`.

## 12. Advanced predictive families

When `USE_ADVANCED_FEATURES=true`, the pipeline also adds:
- volatility regime (`vol_regime_ratio`, `vol_of_vol_20`, `tail_risk_30`)
- event decay (`earnings_decay`, `sentiment_decay_*`, `sentiment_impulse`)
- microstructure proxies (`intraday_spread`, `close_loc_in_range`, `range_compression_5`, `turnover_z_20`)
- sequence state (`trend_state_*`, `regime_transition_flag`, `shock_state`)
- benchmark-relative factors (`mom_*`, `alpha_proxy_20`, `beta_proxy_60`)

These improve cross-regime stability and reduce over-reliance on any one narrow signal family.

## 13. Intel factor engine

When `USE_INTEL_FACTORS=true`, `composite_sentiment()` blends:
- baseline headline sentiment,
- news recommendation factor (`intel.news_factor_engine`),
- transcript factor (`intel.transcript_factor_engine`),
- repetition-thesis persistence (`intel.repetition_weighting`) to up-weight recurring independent narratives.

This turns qualitative recommendation/video chatter into explicit numeric features used in scoring.

## 14. Guarded self-modify controls

The policy agent (`self_modify.policy_agent`) can adapt bounded runtime parameters in live mode, but only if:
- candidate changes are inside strict parameter bounds (`change_validator.BOUNDS`),
- live health checks are acceptable (drawdown/hit-rate/sharpe-proxy guards),
- human lock is not enabled (`POLICY_HUMAN_LOCK=false`).

All adaptation attempts are written to an append-only hash-chained audit log:
- `data/policy/audit_trail.jsonl`

Runtime overrides are isolated from code files:
- `data/policy/runtime_policy_overrides.json`

So strategy can be tuned with rollback and full traceability.

## 15. Multi-Algorithm final decision (2026 stack)

When `USE_MULTI_ALGO_FUSION=true`, final `p_up` is no longer only the base short/long ensemble.
It blends:
- base ensemble probability (`model_short` + `model_long`)
- auxiliary ML models (`SVM-RBF`, `RF`) from training bundle
- intelligence factors (news/transcript/LLM extraction)
- insider-flow proxy signal

This is implemented in `multi_algo_fusion.fused_decision()` and consumed in
`live_market.py`, `fortress_live.py`, and `paper_sim_today.py`.

## 16. Compliance and legal guardrails

Before routing orders, `compliance_guard.pretrade_check()` enforces baseline
constraints:
- block spot-crypto shorts,
- cap oversized concentration relative to equity,
- PDT-style risk block for live accounts below configurable equity threshold,
- reject invalid size payloads.

These are baseline technical controls and not legal advice. Final legal/compliance
responsibility remains with the operator and broker account settings.

## 17. Institutional risk caps (`risk_manager.py`, Phase 14)

Beyond compliance, `RiskManager.can_open_explain()` enforces layered portfolio rules (each returns a string reason on reject):

- **Monthly drawdown halt** — `USE_MONTHLY_DRAWDOWN_HALT` tracks intra-month peak equity in `MONTHLY_EQUITY_STATE_FILE` (default `data/risk/monthly_equity.json`). If `(peak − current) / peak ≥ MONTHLY_DRAWDOWN_HALT_PCT` (default 10%), new risk is blocked.
- **Portfolio heat** — existing ATR-distance vs notional cap (`MAX_PORTFOLIO_HEAT`).
- **Total gross exposure** — sum of absolute open notionals ≤ `MAX_TOTAL_EXPOSURE_FRAC × equity` (default 70%).
- **Single-asset cap** — per underlying (long `TICK` and short `TICK:S` share the same `base_symbol`) gross notional ≤ `MAX_SINGLE_ASSET_FRAC × equity` (default 5%).
- **Sector concentration** — optional `USE_SECTOR_RISK=true`: sum notionals in the same yfinance **sector** ≤ `SECTOR_MAX_EXPOSURE_FRAC × equity` (default 30%). Sectors are cached under `SECTOR_CACHE_FILE`.

Paper simulation and Fortress call `register_open()` after a successful `can_open` so later picks in the same run see cumulative exposure. Set `USE_SECTOR_RISK=true` only when you accept extra yfinance `info` calls (cached on disk).

## 18. FRED macro tilt (`signals/fred_macro.py`, Phase 4)

When `FRED_API_KEY` is set, `get_macro_bundle()` fetches latest **DGS10**, **DGS2**, and **VIXCLS** (optional), computes **10y−2y spread**, and a bounded `macro_score` ∈ [−1, 1]. Paper-sim adds `RANK_W_MACRO * tanh(macro_score * 1.8)` to the composite ranker and stores `fred_macro` + per-row `macro_score` / `fred_spread_10y2y` on each report row.

## 19. Parallel headline fetch (Phase 1)

`intel/headline_fetch_parallel.fetch_headline_groups_parallel()` overlaps Finnhub, NewsAPI, and Cramer HTTP via `ThreadPoolExecutor` (toggle `USE_PARALLEL_NEWS_FETCH`, default on). `intel/news_factor_engine.score_symbol_news_factors()` uses it so intel scoring keeps correct per-source weights for `src_rel`.

## 20. Model training — honest holdout + new signal columns

`model_trainer._train_single_ticker()` defaults to **`TRAIN_TIME_ORDER_SPLIT=true`**: the **last** `TRAIN_TEST_FRACTION` (default 20%) of bars **in calendar order** are the test set. Random `train_test_split` is still available (`TRAIN_TIME_ORDER_SPLIT=false`) but tends to **inflate accuracy** because future regimes leak into the training fold — the pattern you saw (90% collapsing to ~50% live) is classic **distribution / leakage mismatch**.

`feature_engineering.build_features()` now ends with `signals/train_feature_enrich.enrich_train_signals()` when `USE_TRAIN_SIGNAL_FEATURES=true` (default), adding the same **`ur_score`** and **`fred_spread_10y2y`** columns used in the composite ranker logic, so **train features match live inference**.

**Full redo (kill switch)** before a long retrain batch:

1. Set `TRAIN_KILL_SWITCH_ALL=true` once — clears `data/train_checkpoint.json`, forces `FRESH_MODEL_REBUILD` (deletes `models/{TICKER}_model.pkl` and `models/meta/{TICKER}_meta.pkl` before each train), and keeps chronological split defaults.
2. Or manually: `RESET_TRAINING=true` plus `FRESH_MODEL_REBUILD=true` for the same effect on checkpoints + per-ticker purges.

Optional: `TRAIN_COMPUTE_UR=false` speeds up universe batch training (U&R column becomes zeros).

## 21. Classic quant playbook features

`analytics/classic_quant_features.enrich_classic_quant_features()` runs after the advanced family and adds the standard quant-trader toolkit as causal columns (toggle `USE_CLASSIC_QUANT_FEATURES=true`, default on):

- **Trend following**: SMA(50/200) ratio + golden-cross flag, EMA(12/26) ratio, **MACD line / signal / histogram** (normalised to price).
- **Breakouts / new highs / new lows**: **`dist_from_20d_high`**, **`dist_from_52w_high`**, **`dist_from_52w_low`**, **`breakout_20d_high`** flag, **`donchian_pos_55`** (turtle-style channel position).
- **Mean reversion**: **Bollinger %B** (`bb_pct_b`), **`bb_width`**, **`bb_oversold` / `bb_overbought`** flags, **RSI bucket flags** (`rsi_oversold` / `rsi_overbought` / `rsi_centered`).
- **Volatility / risk sizing**: **ATR(14)** and **`atr_frac`** (ATR-as-fraction-of-price) — used by the risk manager for volatility-aware stops.
- **Execution / VWAP**: rolling **VWAP-20** proxy and **`close_vs_vwap`** deviation.

All columns are shifted to avoid look-ahead (e.g. 20d/52w highs are `shift(1)`), so they are safe for chronological holdout training and live inference. They are added to `ml_model.FEATURES`; the trainer prunes near-constant ones per ticker (`_prune_dead_features`).

## 22. AI training grader

At the end of `train_universe_batch`, `analytics.ai_training_grader.grade_training_run()` reads `data/train_run_stats.jsonl` (one line per ticker — `short_acc`, `short_top20`, `long_acc`, `long_top20`, `meta_auc`) and:

1. Logs a deterministic summary block (`[AI-GRADER] Training accuracy summary:`) with mean / median / p25 / p75 / p90 across the run.
2. If **`LLM_API_KEY`** or **`OPENAI_API_KEY`** is set (and `USE_AI_TRAINING_GRADER=true`), it sends the summary to `intel.llm_signal_agent.score_text_with_llm` and logs the LLM verdict (`sentiment`, `confidence`, `action_bias`, `horizon_days`, `key_thesis`).
3. If neither key is set, it logs a single explicit warning (`No LLM_API_KEY / OPENAI_API_KEY set — skipping LLM verdict`) instead of silently returning zeros.

The summary always prints, so even without an API key the operator sees the real accuracy distribution of the run.

## 23. Where news / podcasts / APIs are used

| Source | Env key | Used in training (`build_features`) | Used live (paper / fortress / ranker) |
|--------|---------|--------------------------------------|----------------------------------------|
| **Finnhub company-news** | `FINNHUB_API_KEY` | Yes — chunked historical fetch → `news_*` columns (`signals/train_news_history.py`) when `USE_TRAIN_NEWS_HISTORY=true` | Yes — `sentiment_pipeline.fetch_finnhub_headlines`, `intel/headline_fetch_parallel`, `intel/news_factor_engine` |
| **NewsAPI** | `NEWSAPI_KEY` | No (free tier has weak historical coverage; not wired into daily bars) | Yes — `fetch_newsapi_headlines`, Cramer proxy queries, parallel with Finnhub |
| **LLM signal** | `OPENAI_API_KEY` or `LLM_API_KEY` | Optional in `news_factor_engine` / transcript engine when `USE_LLM_SIGNAL=true` | Same |
| **Transcripts / “podcasts”** | (file-based) | Yes if `data/replay/transcripts/{SYM}.jsonl` lines include `ts` / `date` / `publishedAt` → `transcript_sent_roll_5d` | `intel/transcript_factor_engine.score_symbol_transcripts` reads the same jsonl (undated lines still score as a single bundle for **live** factor, not as a time series) |
| **OpenAI Whisper** | local / `WHISPER_MODEL` | No | `video_analyzer.transcribe_video` only when you pass audio files |

**Heavy intel blend:** `HEAVY_NEWS_INTEL=true` increases weight on `news_factor_engine` + transcript factors in `composite_sentiment`, `paper_sim_today`, and `fortress_live`.

**Universe training off:** `TRAIN_CONFIG_TICKERS_ONLY=true` makes `train_universe_batch` use `config.TRAIN_TICKERS` only (no Nasdaq 11k list). Pair with deleting `data/train_checkpoint.json` when switching modes.

## 24. Jim Cramer pick boost (`intel/cramer_picks.py`)

`intel/cramer_picks.score_symbol_from_cramer(SYM)` extracts ticker mentions from `data/replay/transcripts/CRAMER.jsonl`, scores each mention by **sentence-level** bullish/bearish verbs, and weights recent dates higher (`CRAMER_DECAY_HALF_LIFE_DAYS`, half-life decay). The result is folded into the composite ranker (`RANK_W_CRAMER`) **and** added on top of `composite_sentiment` in the live runner (`fortress_live.py`).

Ingest workflow (no API key required):

```bash
# From stdin (paste a Mad Money transcript, then Ctrl-D):
./venv/bin/python ingest_cramer.py --date 2025-09-12

# From a YouTube URL (requires `pip install youtube-transcript-api`):
./venv/bin/python ingest_cramer.py --youtube https://youtu.be/VIDEOID --date 2025-09-12

# From a local text file:
./venv/bin/python ingest_cramer.py --file path/to/transcript.txt --date 2025-09-12
```

The same file is also read by `intel/transcript_factor_engine` for the broader transcript factor, but Cramer-specific scoring uses sentence proximity for cleaner pick extraction.

## 25. Social sentiment alt-data (`intel/social_sentiment.py`)

StockTwits **public** symbol stream (no API key) is aggregated into a `[-1, 1]` score from `entities.sentiment.basic` (`Bullish` / `Bearish`), per-process cached for 15 min. Used as `social_factor` in the ranker (`RANK_W_SOCIAL`) and as a sentiment overlay in `fortress_live.py`. Toggle via `USE_SOCIAL_SENTIMENT=false` if the endpoint rate-limits — the module auto-disables itself on 401/403/429.

## 26. Alpaca paper trade — how to start

`run_paper_sim.sh` runs the **hypothetical** ranker (no real orders; uses `paper_sim_today.py`). `run_alpaca_paper_live.sh` flips `USE_REAL_MONEY=true` to route real orders to your **paper** Alpaca account via `fortress_live.py` + `alpaca_broker.submit_market_order`.

`.env` paper defaults (already set): `PAPER_SIM_MODE=top_k`, `PAPER_SIM_TOP_K=20`, `PAPER_SIM_MIN_CONF=0.55`, `PAPER_SIM_ALLOW_SHORTS=true`, `PAPER_SIM_SHORT_TOP_K=10`, `ORDER_NOTIONAL=$500`, `PAPER_SIM_CONFIG_TICKERS_ONLY=true`. The default `LIVE_SYMBOL_LIST` includes index ETFs (`SPY`, `QQQ`, `IWM`) and 3× leveraged ETFs (`SOXL`, `SQQQ`, `TQQQ`) for additional churn.

## 27. Cramer high-conviction override

`intel/cramer_picks.STRONG_BUY_PHRASES` flags table-pounding lines such as `buy buy buy`, `screaming buy`, `table pounding`, `in one week`, `must own`, `home run`, `going to soar`, `100%`, `low risk high reward`. When one of these phrases appears in the **same sentence** as a ticker, `extract_picks()` sets `high_conviction_buy=True`, and the paper-sim ranker:

1. Adds **`RANK_W_CRAMER_STRONG_BUY=0.80`** to that ticker's composite score (very large lift).
2. **Force-prepends** the ticker into `picks` regardless of `top_k` cutoff, model confidence, or asym meta filter (still subject to `risk_manager.can_open`).
3. Sizes the position at **`CRAMER_HIGH_CONVICTION_NOTIONAL_MULT * ORDER_NOTIONAL`** (default 1.5× = $750 if base is $500).
4. Holds for **`CRAMER_HOLD_DAYS=10`** days (vs `HOLD_DAYS_DEFAULT=5`) — Cramer picks are days-to-weeks bets, not next-bar scalps.

The default "ordinary" Cramer weight (`RANK_W_CRAMER`) is **0.10** (~10% of the buy decision), down from 0.20.

## 28. Days-to-weeks holding period

`paper_sim_today` now computes `fwd_5d_return`, `fwd_10d_return`, and `fwd_20d_return` per row. `HOLD_DAYS_DEFAULT=5` selects which one drives hypothetical PnL (next-bar `fwd_1d_return` is still recorded for legacy comparisons). Cramer high-conviction picks use `CRAMER_HOLD_DAYS=10`.

### Horizon-aware Cramer weighting

The Cramer factor is **horizon-aware** to match the user model that Cramer's calls inform day-to-week trades, not next-bar fluctuations:

| Mode | Cramer share of decision |
|------|---------------------------|
| Ultra-short / **sub-second HFT** (Node.js `hft/` module — earnings and OBI/Tape) | **0%** (Cramer is *not loaded* in this module) |
| Sub-day (`HOLD_DAYS_DEFAULT < CRAMER_ULTRA_SHORT_CUTOFF_DAYS=2`) | **0%** (Cramer ignored in Python ranker too) |
| Day-long / week-long (`HOLD_DAYS_DEFAULT ≥ 2`) | **~20%** via `RANK_W_CRAMER=0.20` |
| Table-pounding high-conviction | **~70%** via `RANK_W_CRAMER_STRONG_BUY_SHARE=0.70` + force-buy override |

## 29. Feature pruning safeguards

`model_trainer._prune_dead_features` now keeps a curated `KEEP_CROSS_SECTIONAL` set (`fred_spread_10y2y`, classic-quant flags, news rolls, `ur_score`) even if those columns are constant for **this** ticker, because they vary cross-sectionally and the model needs the same column layout at inference. The drop rule is also gentler: only `nunique <= 1` triggers a drop (no low-variance cutoff).

## 30. LSTM / RNN meta head (`analytics/lstm_head.py`)

Opt-in non-linear sequence head. Enable with `USE_LSTM_HEAD=true` to train a 2-layer LSTM (hidden=64, dropout=0.2) on the last `LSTM_SEQ_LEN=30` bars of `FEATURES`, predicting `target_long`. Bundle saved to `models/lstm/{TICKER}_lstm.pt` per ticker (z-score normalisation derived from training rows only — no leakage). Inference blends the LSTM probability into the meta input with weight `LSTM_BLEND_WEIGHT=0.25` when `BLEND_LSTM_INTO_META=true`. Falls back to no-op when PyTorch is unavailable or the per-ticker checkpoint is missing.

Smoke run on AAPL converges in ~4 epochs to **~65% chronological test accuracy** (vs ~76% from the tree ensemble alone — the LSTM is meant to be a non-linear *complement*, not a replacement).

## 31. Walk-forward validator (`walk_forward.py`)

`./run_walk_forward.sh TICKER[,TICKER...]` runs rolling-window training across `WF_SPLITS=6` chunks. Each split logs **`acc`** and **`acc@top20`** plus a summary line so you can see whether the edge holds through time, not just on the static last-20% holdout. Uses `FEATURES` directly so results are comparable to production training.

## 32. Sub-second HFT module (`hft/`, Node.js + TypeScript)

The Python pipeline above optimises **day-to-week** horizons. The genuinely sub-second / sub-millisecond profit path lives in a separate Node.js peer module at `hft/` so each side can specialise:

| File | Phase | Role |
|------|-------|------|
| `hft/src/earnings/earnings-ingestor.ts` | 1 | Premium-wire WebSocket (Benzinga / Polygon / Alpaca), byte-level `Buffer.indexOf` ticker prefilter, `process.hrtime.bigint()` stamp |
| `hft/src/earnings/earnings-evaluator.ts` | 2 | Zero-allocation `Float64Array` state, regex-free `jsonNumberAfter` JSON scan, EPS+Revenue+Guidance surprise math, 10-second rolling VWAP guard, top-of-book sizing |
| `hft/src/earnings/earnings-executor.ts` | 3 | IOC limit at NBBO ± `EARN_LIMIT_TICK_OFFSET=2` ticks via warm undici Pool to Alpaca, 100 ms ingest-to-fire circuit breaker, 400 ms fill deadline |
| `hft/src/earnings/post-trade.ts` | 4 | Async `process.nextTick` JSONL logger, slippage in cents, fee tracking, hard one-trade-per-ticker lock |
| `hft/src/obi-tape/l2-book.ts` | 1 | Flat `Float64Array(20)` per ticker, top-5 levels, OBI recomputed inline per delta |
| `hft/src/obi-tape/tape-velocity.ts` | 2 | 100 ms rolling counter + 5 s baseline + continuous micro-VWAP |
| `hft/src/obi-tape/obi-tape-signals.ts` | 3 | Bit-packed flag byte: `(F_OBI_LONG \| F_TAPE_BURST) == 0b0101` fires buy, mirror for short; IOC limit 1 tick aggressive |
| `hft/src/obi-tape/obi-tape-risk.ts` | 4 | Micro-stop flatten when NBBO walks `OBI_MICRO_STOP_TICKS=3` ticks against entry; ticker locked for `HFT_PER_TICKER_COOLDOWN_MS=60000` ms after fill |

**Cramer is intentionally excluded from this module.** These trades are pure microstructure fluctuation profit; Cramer is loaded only by the Python ranker for the day/week horizons.

### Run

```bash
./run_hft.sh install       # one-time npm install
./run_hft.sh build         # compile TS → dist/
./run_hft.sh test          # hot-path smoke tests (10 cases pass clean)
./run_hft.sh earnings:perf # sub-100ms earnings loop, GC-quieted V8 flags
./run_hft.sh obi-tape:perf # sub-10ms OBI/Tape loop, GC-quieted V8 flags
./run_hft.sh both:perf     # both in parallel (recommended for live trading)
```

V8 flags used by `:perf` scripts (in `hft/package.json`):

```
--no-warnings --max-old-space-size=1024
--predictable-gc-schedule --no-concurrent-marking
--turbo-fast-api-calls --huge-max-old-generation-size
```

These trade peak throughput for **lower GC-pause tail latency** during a market spike, which is the metric that matters for sub-second reactions.

Safety knobs (read by both algorithms):

```ini
HFT_DRY_RUN=true                  # log orders only, never POST to broker
HFT_GLOBAL_KILL=false             # flip true to refuse start
HFT_MAX_ORDERS_PER_MIN=30
HFT_PER_TICKER_COOLDOWN_MS=60000  # post-fill lockdown
```

All hot-path state is pre-allocated typed arrays (`Float64Array`, `Uint8Array`) — no per-message object creation, so V8's generational GC stays idle during market spikes.

## 33. Per-horizon model coverage (every ticker, every timeframe)

Every ticker gets a dedicated head for every holding window the bot trades on. The training pipeline is split into three layers that mirror the data sources we can actually obtain:

| Horizon | Engine | Artifact | Driver | Train command |
|---------|--------|----------|--------|---------------|
| Sub-second | `hft/` Node.js (rule-based: earnings surprise, OBI, tape velocity) | n/a — config-only | Alpaca IEX WS / Polygon (paid plan WS) | `./run_all.sh start subsecond` |
| Minutely (5-min fwd) | `intraday/intraday_trainer.py` | `models/intraday/{T}_intraday.pkl` → `model_minutely` | Alpaca IEX minute bars | `./run_all.sh train-intraday` |
| Hourly (60-min fwd) | same bundle | `model_hourly` | Alpaca IEX minute bars (resampled) | same |
| Daily (1-bar fwd) | `model_trainer.py` (multi-horizon) | `models/{T}_model.pkl` → `model_daily` | Yahoo daily bars | `./run_all.sh train` |
| Weekly (5-bar fwd) | same bundle | `model_short` | same | same |
| Long-term (20-bar fwd) | same bundle | `model_long` | same | same |
| Extra-long (60-bar fwd) | same bundle | `model_xlong` | same | same |

The daily bundle (`models/{T}_model.pkl`) now stores **all four daily-and-up heads** in a single pickle along with the original meta-stack ranker and any auxiliary models. Inference picks the right head via:

```python
from ml_model import predict_row_horizon
result = predict_row_horizon("models/AAPL_model.pkl", feature_row, horizon="daily")
# horizon ∈ {"daily","weekly","long","xlong"} or an int days lookahead (1/5/20/60)
```

Intraday inference uses:

```python
from intraday.intraday_trainer import predict_intraday
result = predict_intraday("AAPL", feature_row, horizon="minutely")  # or "hourly"
```

AAPL smoke-train results on the new pipeline (chronological holdout):

| Horizon | acc | acc@top20% |
|---------|-----|------------|
| Daily (1-bar) | 0.521 | 0.576 |
| Weekly (5-bar) | 0.485 | 0.576 |
| Long (20-bar) | 0.764 | 0.909 |
| Extra-long (60-bar) | **0.739** | **1.000** |
| Minutely (5-min fwd, GBT) | 0.493 | 0.491 |
| Hourly (60-min fwd, GBT) | 0.474 | 0.481 |

The long-horizon heads carry the real edge (as expected — the macro/fundamental/news features speak loudest over weeks/months); the minutely and hourly heads are mostly there as ensemble inputs alongside the HFT microstructure module.

### Run order recommended

```bash
./run_all.sh status            # confirm 6 API keys green + which horizons are trained
./run_all.sh train             # daily-and-up universe (4 heads per ticker, multi-hour job)
./run_all.sh train-intraday    # minute + hourly per ticker (slow — ~3 min/ticker; defaults to config.TRAIN_TICKERS)
./run_all.sh train-all         # both in sequence
./run_all.sh start subsecond   # HFT module (dry-run by default)
./run_all.sh start weekly      # paper sim with HOLD_DAYS_DEFAULT=5
./run_all.sh start longterm    # paper sim with HOLD_DAYS_DEFAULT=20
./run_all.sh logs              # tail every horizon's log
./run_all.sh stop              # graceful shutdown of all horizons
```
