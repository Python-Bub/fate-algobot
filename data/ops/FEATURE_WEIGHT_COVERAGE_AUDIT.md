# Feature Weight Coverage Audit

**As of 2026-07-30.** Source: `analytics/sleeve_weights.py` + catalog/knowledge.

## Summary

| Metric | Count |
|--------|------:|
| Catalog topics | 292 |
| Deep knowledge chapters | 291+ |
| Curriculum sleeve mappings | 292 |
| Book themes tracked in weights | 22 / 22 weighted |
| Sleeves @ 100% | hft, day_trade, fortress, weekly, longterm |
| HFT↔LT forbidden overlap | **none** (index_etf shared theme only) |
| HFT Cramer % | **0** |
| LT OBI % | **0** |

## Index ETF policy

| Control | Value |
|---------|-------|
| `FORTRESS_BAN_INDEX_BUYS` | **false** (allowed) |
| `HFT_BAN_INDEX_BUYS` | **false** |
| Sleeve `index_etf` % | HFT 1 / day 3 / fortress 5 / weekly 5 / LT 7 |
| `FORTRESS_MAX_SINGLE_FRAC` | 0.10 |
| `FORTRESS_NO_REBUY_SYMBOLS` | SPY,QQQ,IWM,… (anti-spam rebuy) |

## Wired factor families (non-exhaustive)

- **ML / neural:** `model_edge` / `model_edge_5d` / `model_edge_20d` (RF/XGB/LGBM + LSTM/CNN/DQN blend into p_adj)
- **Cramer daily:** fortress 5%, day 4%, weekly 5%, LT 4%; post-market + succession on fortress
- **Book:** value_dcf, graham, buffett, garp, compounder, dividend, turnaround, REIT context
- **Macro:** cycle, inflation/deflation, rates, FX/commodity soft
- **Passive:** index_etf, dca_buy_hold
- **Alt/deriv soft:** alt_context, derivatives_context (no Alpaca options/VC execution)
- **HFT micro:** OBI, tape, micro-price, spread, JP micro, pair, news_micro, stat_arb_micro

## Orphans → placement

Previously buried or 0%: Cramer (now explicit), succession, post-market, graham, GARP, compounder, dividend, inflation, rates, DCA, index_etf, alt/deriv context, industry AI, HMM, fund, transcript, event-driven, HF ETF disloc (re-enabled under cap).

Liquidity_mm stays **0** off HFT (lives as `spread_liquidity` on HFT).

## Docs

- Live tables: `data/ops/PICK_WEIGHTAGE_BY_SLEEVE.md`
- Book: `data/books/investing_guide_full.md` + `data/books/chapters/INDEX.md`
- Map: `investing/knowledge/sleeve_curriculum_map.py`
