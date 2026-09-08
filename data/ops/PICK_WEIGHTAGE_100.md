# Fortress perfect-pick weightage (100%) — index ETF lockdown

**As of 2026-07-30.** Additive score contributions at max signal, normalized to 100%.  
Single-name path only — `HF_W_ETF_DISLOC` and `HF_W_LIQUIDITY_MM` are **locked at 0** (no index favoritism).

Method: max raw contribution of each term ÷ sum of max contributions × 100  
(same methodology as audit f76dba9c).

---

## A) Fortress perfect-pick table (sums to 100%)

| Factor | % | Max raw | Source |
|--------|--:|--------:|--------|
| Model edge (`p_adj` / ML) | **22** | 0.75 | `analytics/rank_pipeline.py:120` (`FORTRESS_W_EDGE`); fallback `fortress_live.py:261` |
| PRED_FORCE boost | **12** | 0.41 | `fortress_live.py:1421` (`PRED_FORCE_SCORE_BOOST`) |
| Bottom fisher | **10** | 0.34 | `bottom_fisher/integrate.py:21` (`RANK_W_BOTTOM_FISHER`) |
| Earnings STICK boost | **9** | 0.31 | `fortress_live.py:1408` (`EARNINGS_STICK_SCORE_BOOST`) |
| Execution confidence | **8** | 0.27 | `analytics/rank_pipeline.py:121` (`FORTRESS_W_EXEC`) |
| Value investing (DCF / MoS) | **5** | 0.17 | `analytics/value_investing.py:318` (`RANK_W_VALUE`) |
| Cross-company links | **4** | 0.14 | `analytics/cross_company_links.py:996` (`RANK_W_CROSS_COMPANY`) |
| HF: momentum | **3** | 0.11 | `analytics/hedge_fund_stack.py:274` (`HF_W_MOMENTUM`) |
| HF: stat_arb / pairs | **3** | 0.11 | `analytics/hedge_fund_stack.py:279` (`HF_W_STAT_ARB`) |
| Structure / S-R patterns | **3** | 0.10 | `analytics/structure_patterns.py:440` (`RANK_W_STRUCTURE`) |
| Hidden anomaly + mkt imbalance | **3** | 0.10 | `analytics/hidden_pattern_anomaly.py:461` (`RANK_W_HIDDEN_ANOMALY`) |
| Unique playbook (big_brain) | **3** | 0.10 | `intel/unique_style_playbook.py:453-456` (`RANK_W_UNIQUE` / `UNIQUE_RANK_CAP`) |
| HF: trend | **3** | 0.10 | `analytics/hedge_fund_stack.py:278` (`HF_W_TREND`) |
| Investing-book composite | **2** | 0.07 | `investing/integrate.py:263` (`RANK_W_BOOK` × cap) |
| HF: value factor | **2** | 0.07 | `analytics/hedge_fund_stack.py:275` |
| HF: quality | **2** | 0.07 | `analytics/hedge_fund_stack.py:276` |
| HF: mean reversion | **2** | 0.07 | `analytics/hedge_fund_stack.py:281` |
| HF: market-neutral tilt | **1** | 0.04 | `analytics/hedge_fund_stack.py:282` |
| HF: size | **1** | 0.04 | `analytics/hedge_fund_stack.py:277` |
| Top-100 market-cap bonus | **1** | 0.03 | `analytics/rank_pipeline.py:123` (`FORTRESS_TOP100_RANK_BONUS`) |
| Narrative (sent + news impulse) | **1** | ~0.022 | `analytics/rank_pipeline.py:117-122` (`FORTRESS_W_SENT` + `FORTRESS_NEWS_RANK_W`) |
| **HF: ETF dislocation** | **0** | 0.0 | Locked: `HF_W_ETF_DISLOC=0` + `HF_LOCK_ETF_DISLOC_ZERO` (`hedge_fund_stack.py:280,311-312`) |
| **HF: liquidity_mm** | **0** | 0.0 | Locked: `HF_W_LIQUIDITY_MM=0` + `HF_LOCK_LIQUIDITY_MM_ZERO` (`hedge_fund_stack.py:283,313-314`) |
| **Total** | **100** | | |

HF sleeve (ex-ETF / ex-liquidity) ≈ **17–18%** combined.

Water is **not** in this PRED_FORCE row. Live overlay is `water_datacenter` **2%** of
the fortress sleeve table (`analytics/sleeve_weights.py`) — datacenter cooling
demand, gated by the model head. See `data/ops/PICK_WEIGHTAGE_BY_SLEEVE.md`.

Core fortress score before additive hooks:

```text
score = FORTRESS_W_EDGE * edge
      + FORTRESS_W_EXEC * exec_c
      + FORTRESS_W_SENT * sent_imp
      + FORTRESS_NEWS_RANK_W * news_imp
      + RANK_W_HEDGE_FUND * hf_boost
      + [top100 bonus]
```

Then additive: STICK → FORCE → structure → bottom fisher → value → book → unique → anomaly → cross-co  
(`fortress_live.py:1403-1490`).

Env live values: `data/deploy_scale.env` (sourced by `run_all.sh`) + `.env`.

---

## B) Hard gates (not part of the 100% — binary pass/fail)

These **block** buys; they do not add rank points.

| Gate | Default / live | Where |
|------|----------------|-------|
| `volume_confirmed` | fortress mult `VOLUME_CONFIRM_MULT=1.0` | `feature_store.py:102`; applied `fortress_live.py:1085-1086` |
| `mtf_buy_ok` | daily bull + 5m RSI &lt; `MTF_RSI_MAX` (35 fortress) | `multi_timeframe.py` / import `fortress_live.py:28`; applied `:1088` |
| `MATH_P_UP_FLOOR` | code 0.48; live **0.55** (`deploy_scale.env`) | `analytics/execution_confidence.py:73-75` |
| Exec / news / sentiment combo | conf + news + vol + mtf (unless relaxed) | `fortress_live.py:1094-1097` |
| Downward pressure / algo risk / headwind | hard `want_buy=False` | `fortress_live.py:1164-1214` |
| **Index ETF ban** | `FORTRESS_BAN_INDEX_BUYS=true`; list SPY,QQQ,IWM,DIA,VOO,VTI,SOXX,XLK,XLF,XLE | scan `fortress_live.py:1354-1368`; execute belt `:1803+` |
| **No ADD_ON / no rebuy** | `FORTRESS_ALLOW_ADD_ON=false`; `FORTRESS_NO_REBUY_SYMBOLS` | `fortress_live.py:1723-1732`, `:1803-1811` |
| Single-name cap | `FORTRESS_MAX_SINGLE_FRAC=0.10` | sizing path + soft trim |

---

## C) FORCE / STICK / earnings interaction

1. **Earnings STICK** (`intel.historical_events.holdings_earnings_plan`): if `encourage_pre_momentum` or `stick_to_prediction` and `p_adj ≥ EARNINGS_STICK_MIN_P` (0.52) → add **+0.31** score and set `force_priority=True` (`fortress_live.py:1403-1417`).
2. **PRED_FORCE** / force-buy list (`PRED_FORCE_BUY`, `FORTRESS_FORCE_BUY_SYMBOLS`): when `force_priority` → add **+0.41** (`fortress_live.py:1420-1427`). STICK and FORCE **stack**.
3. FORCE / STICK can bypass **soft** day-of gates but **not** `hard_gate_block` (pressure / algo-risk) — see `fortress_live.py:1264-1308`.
4. FORCE names pin ahead of letter-diversify rotation (`analytics/trade_rotation.py` `force_priority`).
5. **Soft index trim for FORCE**: if FORCE singles need cash and overnight hold is ON, partial-trim held index ETFs only (≤25–35% of leg, never wipe) — `fortress_portfolio.py:40` `maybe_trim_index_etfs_for_force`; called `fortress_live.py:1638-1654`.

---

## D) Sleeve differences (brief)

### Paper (`paper_sim_today` / `rank_pipeline.build_buy_rank`)
Full additive `RANK_W_*` stack (PUP, MOM, RS, VOL, SENT, DIP, rally, HMM, fund, Cramer, social, industry, …) — **not** the fortress edge/exec blend. Same HF stack + bottom fisher / structure / value hooks. See `analytics/rank_pipeline.py:75-95` (`core_composite_score`) and `paper_sim_today.py` buy-rank path.

### HFT OBI / micro-MR
Separate microstructure weights (`HFT_W_OBI_PROB`, tape, spread, momentum, …) in `hft/src/obi-tape/microstructure-prob.ts`.  
Hard ban mirrors fortress: `hft/src/obi-tape/micro-mean-reversion.ts` (`HFT_BAN_INDEX_*`).  
Whitelist defaults are **single names only** (`hft/src/common/config.ts` `OBI_TICKER_WHITELIST`) — SPY/QQQ/IWM removed from code defaults.

### Day-trade sleeve
Setup blend (candlestick / VWAP / momentum) in `day_trade_setups.py` + `day_trade_ranker.py` — independent of fortress %.

---

## E) Index ETF lockdown checklist

| Control | Status |
|---------|--------|
| Code defaults ≠ SPY/QQQ/IWM | `fortress_universe.py:132-148`, `micro_scalp.py:159-168`, `hft/src/common/config.ts` OBI/earn lists |
| Ban even if whitelist wrong | fortress execute re-check; HFT `mr_ban_index`; quality ticker set strips bans |
| No ADD_ON / no rebuy held indexes | `FORTRESS_ALLOW_ADD_ON=false`, `FORTRESS_NO_REBUY_SYMBOLS` |
| Soft trim only for FORCE cash | `FORTRESS_INDEX_SOFT_TRIM=true`, overnight hold preserved |
| Equity universe untouched | train / talk / all-ticker coverage **not** reduced |

---

*Optimize never remove: bans kill index favoritism only — not equity coverage or training phases.*
