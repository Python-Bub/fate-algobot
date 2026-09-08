# Sleeve Scoring Research — wired vs orphaned

**As of 2026-07-30.** Inventory of scoring/strategy contributions vs fortress/HFT/day/weekly/longterm sleeves.  
Optimize never remove — orphans get wired into the right sleeve, not deleted.

---

## Executive findings

1. **Fortress "perfect pick 100%"** (`PICK_WEIGHTAGE_100.md`) listed ML/FORCE/STICK/fisher/value/HF… but **buried** Cramer/social/morning club inside sentiment blend — looked "missing" in the %. Fixed: explicit rows in fortress/weekly/LT tables (`sleeve_weights.py`).
2. **Zeros that are correct (not bugs):** `HF_W_ETF_DISLOC=0`, `HF_W_LIQUIDITY_MM=0` on fortress/weekly/LT (index ban). Liquidity belongs on **HFT** as `spread_liquidity` (10%).
3. **Paper path** (`paper_sim_today` / `rank_pipeline.build_buy_rank`) had full `RANK_W_*` (HMM, fund, Cramer, social, macro, industry…) — fortress used a thinner edge/exec path + additive hooks. Phase 2+ unified via sleeve env apply.
4. **HFT** already had separate `HFT_W_*` microstructure weights — must never import `RANK_W_CRAMER` / macro / value / buy-hold.
5. **Curriculum** (macro/alt/passive) chapters already existed in `investing/knowledge/short_macro.py` + `alt_passive.py`. New paste → `data/books/investing_curriculum_macro_alt_passive.md` + `sleeve_curriculum_map.py` (no duplicate DeepChapters).

---

## Strategy → sleeve map

| Strategy | Paths | Env knobs | Fortress | Weekly | Longterm | Day | HFT | Status |
|----------|-------|-----------|----------|--------|----------|-----|-----|--------|
| ML edge / p_adj | `rank_pipeline.fortress_buy_score`, `ml_model` | `FORTRESS_W_EDGE` | ✓ 17% | ✓ 5d | ✓ 20d | soft | — | wired |
| PRED_FORCE | `fortress_live` | `PRED_FORCE_*` | ✓ 10% | 0 | 0 | — | — | wired fortress |
| Earnings STICK | `intel.historical_events` | `EARNINGS_STICK_*` | ✓ 7% | soft | soft | — | — | wired |
| Exec conf | `execution_confidence` | `FORTRESS_W_EXEC` / `RANK_W_EXEC_CONF` | ✓ | ✓ | ✓ | — | — | wired |
| Bottom fisher | `bottom_fisher/integrate.py` | `RANK_W_BOTTOM_FISHER` | ✓ | ✓ | ✓ | — | — | wired |
| Value DCF | `analytics/value_investing.py` | `RANK_W_VALUE` | ✓ | ✓ | ✓ primary | 0 | 0 | wired |
| Book composite | `investing/integrate.py` | `RANK_W_BOOK` | ✓ | ✓ | ✓ primary | 0 | 0 | wired |
| Unique / big_brain | `intel/unique_style_playbook.py` | `RANK_W_UNIQUE` | ✓ | ✓ | soft | — | — | wired |
| Structure / S-R | `analytics/structure_patterns.py` | `RANK_W_STRUCTURE` | ✓ | ✓ | ✓ | — | — | wired |
| Hidden anomaly | `analytics/hidden_pattern_anomaly.py` | `RANK_W_HIDDEN_ANOMALY` | ✓ | ✓ | ✓ | — | — | wired |
| Cross-company | `analytics/cross_company_links.py` | `RANK_W_CROSS_COMPANY` | ✓ | ✓ | ✓ | — | — | wired |
| HF stack | `analytics/hedge_fund_stack.py` | `HF_W_*` | ✓ ex ETF/liq | ✓ | quality/value only | — | — | wired; ETF/liq locked 0 |
| Cramer + succession | `intel/cramer_picks.py`, `investor_succession.py` | `FORTRESS_CRAMER_BLEND`, `RANK_W_CRAMER` | ✓ explicit | ✓ | ✓ | 0 | **0** | was buried → explicit |
| Social | `intel/social_sentiment.py` | `FORTRESS_SOCIAL_BLEND`, `RANK_W_SOCIAL` | ✓ | ✓ | soft | — | 0 | wired |
| Morning club | `intel/morning_club_intel.py` | `FORTRESS_MORNING_CLUB_BLEND` | ✓ | ✓ | soft | ✓ | 0 | wired |
| News / transcript | intel factor engines | `FORTRESS_NEWS_RANK_W`, `RANK_W_NEWS_FACTOR` | ✓ | ✓ | ✓ | ✓ impulse | micro only | wired |
| HMM regime | paper / rank_pipeline | `RANK_W_HMM_REGIME` | via HF tilt | ✓ | soft | — | 0 | wired paper |
| Industry AI | `analytics/industries/*` | `RANK_W_INDUSTRY_*` | soft | ✓ | ✓ | — | 0 | wired paper |
| Macro / cycle | `signals/fred_macro`, `investing.formulas.macro` | `RANK_W_MACRO`, `RANK_W_RATE_CYCLE` | soft 2% | ✓ | ✓ primary | 0 | **0** | curriculum soft |
| Inflation / deflation | formulas.macro | `RANK_W_INFLATION` | 0 | soft | ✓ | 0 | **0** | curriculum soft |
| DCA / buy-hold | curriculum | `RANK_W_BUY_HOLD` | 0 | soft | ✓ | 0 | **0** | quality proxy — not index buy |
| Alt VC/PE context | knowledge | `RANK_W_ALT_CONTEXT` | 0 | 0 | soft 1% | 0 | 0 | knowledge + soft |
| Index / ETF investing | knowledge | — | **ban buys** | edu/RS | edu | ban | **ban** | never buy SPY/QQQ/IWM |
| JP candles / RL | `jp_candles`, `jp_candle_rl` | day candle W / HFT MR | context | — | — | ✓ primary | MR dip | wired |
| OBI / tape / micro | `hft/.../microstructure-prob.ts` | `HFT_W_*` | 0 | 0 | 0 | 0 | ✓ 100% | isolated |
| Micro-scalp | `analytics/micro_scalp.py` | `MICRO_SCALP_*` | — | — | — | sidecar | adjacent | separate head |
| RL trader / cortex | `cortex/*`, `rl_*` | paper overlay | — | paper | paper | RL candle | conf delta | paper/HFT conf only |

---

## Dead / capped (intentional)

| Item | Why |
|------|-----|
| `HF_W_ETF_DISLOC=0` + lock | Index favoritism ban |
| `HF_W_LIQUIDITY_MM=0` on fortress/LT | Liquidity scoring is HFT `spread_liquidity` |
| HFT Cramer/macro/value | Wrong horizon — would bleed LT into ms |
| Passive index **buy** signals | User ban; knowledge only |

---

## Cross-bleed proof

`analytics.sleeve_weights.no_cross_bleed()` → `ok=True`, `forbidden_overlap=[]`, HFT cramer=0, LT obi=0, index_etf_buy all zero.
