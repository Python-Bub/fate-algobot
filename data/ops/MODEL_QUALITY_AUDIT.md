# MODEL QUALITY AUDIT

Updated: `2026-07-30T17:32:39.845454+00:00` (UTC)  
Thresholds: **acc@top20 ≥ 0.6**, **meta_auc ≥ 0.55** (strengthen; never drop names).

## Counts

| Bucket | Count | Notes |
|--------|------:|-------|
| Daily models on disk | 1386 | climbing via train-gaps letter_rr |
| Intraday models | 2267 | train-intraday-gap |
| LSTM heads | 4322 | scope=all mostly complete |
| PENDING (no daily) | n/a | vs full universe |
| Universe | n/a | full — not shrunk |

## Coverage vs universe

- Daily: **1386**
- Intraday: **2267**
- LSTM: **4322**

## Priority trade names

| Symbol | Daily | Intra | LSTM | Status |
|--------|:-----:|:-----:|:----:|--------|
| BX | Y | N | Y | PENDING_COVERAGE |
| SBUX | Y | N | Y | PENDING_COVERAGE |
| COST | N | N | Y | PENDING_COVERAGE |
| WMT | N | N | Y | PENDING_COVERAGE |
| NOW | Y | N | Y | PENDING_COVERAGE |
| CRM | N | N | Y | PENDING_COVERAGE |
| JNJ | N | N | Y | PENDING_COVERAGE |
| AAPL | N | N | Y | PENDING_COVERAGE |
| AMZN | N | N | Y | PENDING_COVERAGE |
| META | N | N | Y | PENDING_COVERAGE |
| NVDA | Y | N | Y | PENDING_COVERAGE |
| AMD | N | Y | Y | PENDING_COVERAGE |
| AVGO | N | N | Y | PENDING_COVERAGE |
| MSFT | N | N | Y | PENDING_COVERAGE |
| GOOGL | N | N | Y | PENDING_COVERAGE |
| NFLX | N | N | Y | PENDING_COVERAGE |
| TSLA | N | N | Y | PENDING_COVERAGE |

## How weak names are strengthened

1. ensure-training + retrain-weak-until + enhancement-queue full
2. Thresholds 0.60 / 0.55 — re-queue, never drop
3. NETWORK_FIRST; never delete models/
4. Priority FORCE names rebuilt when missing daily

## Ops blocker

- Monthly drawdown halt ~24.8% (peak $100k → ~$75.2k) — new buys rejected; risk gate kept. No fake +30%.
