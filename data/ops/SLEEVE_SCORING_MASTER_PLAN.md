# Sleeve Scoring Master Plan

**Total phases: 5** (this is the complete program — there is no Phase 6).  
**As of 2026-07-30.** Optimize never remove. Index ETF buys banned on active sleeves. No HFT↔longterm weight bleed.

Source of truth for live %: `analytics/sleeve_weights.py`  
Live tables doc: `data/ops/PICK_WEIGHTAGE_BY_SLEEVE.md`  
Research inventory: `data/ops/SLEEVE_SCORING_RESEARCH.md`  
Curriculum sleeve map: `investing/knowledge/sleeve_curriculum_map.py`

---

## Phase 1 — Separate 100% tables (DONE)
- [x] `analytics/sleeve_weights.py` with HFT / day_trade / fortress / weekly / longterm
- [x] Each active-% table sums to 100; index_etf_buy = 0 everywhere
- [x] Curriculum persisted (`data/books/investing_curriculum_macro_alt_passive.md`) + sleeve map
- [x] `data/ops/PICK_WEIGHTAGE_BY_SLEEVE.md` generated
- [x] Wire fortress / rank_pipeline / day_trade / paper_sim to `apply_sleeve_env`

## Phase 2 — End-to-end sleeve load + orphan fill (DONE)
- [x] Fortress loads fortress sleeve only
- [x] Paper resolves weekly vs longterm via `HOLD_DAYS_DEFAULT` / `FATE_SLEEVE`
- [x] Explicit Cramer/social/club/macro factors in correct sleeves (not HFT)
- [x] ETF_DISLOC + LIQUIDITY_MM locked 0 on non-HFT; liquidity lives on HFT as `spread_liquidity`
- [x] Curriculum soft knobs: `RANK_W_INFLATION`, `RANK_W_RATE_CYCLE`, `RANK_W_BUY_HOLD`, `RANK_W_ALT_CONTEXT` (weekly/LT only)

## Phase 3 — Launcher env + HFT export + overlay hard-locks (DONE this catch-up)
- [x] Export HFT weights → `data/ops/hft_sleeve.env` via `tools/export_sleeve_env.py`
- [x] `run_all.sh` sets `FATE_SLEEVE=` for fortress / OBI / day-trade / weekly / longterm
- [x] Source `hft_sleeve.env` on OBI launch (microstructure only — no Cramer/macro)
- [x] Overlay cannot unlock `HF_W_ETF_DISLOC` / `HF_W_LIQUIDITY_MM` when locks ON

## Phase 4 — Tests + doc perfection (DONE this catch-up)
- [x] `tests/test_sleeve_weights.py` — sum 100, no HFT↔LT bleed, index ban, curriculum soft gated
- [x] Regenerate `PICK_WEIGHTAGE_BY_SLEEVE.md` from live tables
- [x] Research doc written

## Phase 5 — Lock-in / verify / restart (THIS PHASE — FINAL)
- [x] Research + master plan committed to `data/ops/`
- [x] Smoke: `assert_tables_valid` + `no_cross_bleed` + pytest sleeve tests
- [x] Restart trading heads only (fortress / HFT OBI / day-trade / weekly / longterm) — **not** train/talk
- [x] Stamp `KEEP_WORKING_LOG.md` with Phase 5 complete + total phase count = 5
- [x] No further weight-table redesign unless a new taught strategy appears (then extend sleeve table only)

---

## What belongs where (permanent)

| Sleeve | Owns | Must stay 0% |
|--------|------|--------------|
| **HFT/OBI** | OBI, tape, micro-price, spread/liquidity, micro-mom, pair-micro, tiny news-micro | Cramer, value, book, macro, inflation, DCA/buy-hold, index buys |
| **Day-trade** | JP/RL candles, VWAP, ORB, momentum, pullback, gap, morning club, news impulse | Cramer-heavy, value/book, macro, OBI, index buys |
| **Fortress** | ML edge, FORCE/STICK, bottom fisher, value, structure, book, unique, anomaly, cross-co, HF stack (ex ETF/liq), Cramer/social/club, soft macro_cycle | OBI, DCA, index buys, inflation primary, liquidity_mm |
| **Weekly** | 5d edge, news, Cramer, value/book, macro cycle, industry, soft inflation/rates, soft buy-hold | OBI, index buys, PRED_FORCE event path |
| **Longterm** | 20d edge, value, book, top-down/bottom-up, inflation/deflation, rates/cycle, DCA/buy-hold quality, fund, industry, alt soft context, Cramer | OBI/tape/spread, HF short-mom, index ETF buys, PRED_FORCE |

Passive/index knowledge = educational + RS-vs-benchmark context on weekly/LT only — **never** re-enable SPY/QQQ/IWM buys.

---

## Keep-alive
After Phase 5, watchdog continues ensuring fortress/OBI/day/weekly/longterm. Weight changes go through `sleeve_weights.py` only; regenerate PICK doc with:

```bash
./venv/bin/python tools/export_sleeve_env.py --write-md
```
