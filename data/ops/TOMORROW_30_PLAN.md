# TOMORROW ~30% EDGE PLAN — RTH 2026-07-30 (Pacific)

**Honesty first:** no P&L is guaranteed. Markets can gap against any book. This plan does **not** fake returns. It maximizes real overnight→RTH edge: sticky high-conviction singles, earnings/radar, all trading heads UP, models still training full universe — within **~10% equity per name** and no reckless PDT/leverage blow-ups.

**Book now (~20:50 PT 2026-07-29):** equity ≈ **$75.4k**, cash ≈ **$46.1k**. Held: **IWM / QQQ / SPY** (~10% each, **no rebuy**), **SBUX 66sh** (~9.5%, hold). **BX not held** — must FORCE on next valid UP.  
**FORCE path verified live:** fortress logged `FORCE STICK BUY` (ABBV, ETN) and `FORCE PRED BUY SBUX` — stick is not watch-only. Master plan: `MASTER_ALL_ALGORITHMS_PLAN.md`.

With `MAX_SINGLE_ASSET_FRAC=0.10`, a single-name moonshot cannot alone deliver +30% portfolio. Path to a large day = **multiple sticky winners** + deploy idle cash into conviction (target deploy ~55%) + avoid index churn that burned slots today.

---

## Risk caps (do not loosen overnight)

| Cap | Value | Source |
|-----|------:|--------|
| Single-name | **10% equity** (~$7.5k) | `FORTRESS_MAX_SINGLE_FRAC` / `MAX_SINGLE_ASSET_FRAC` |
| Fortress positions | 10 | `FORTRESS_MAX_POSITIONS` |
| Top buys / pass | 8 | `FORTRESS_TOP_BUYS_PER_PASS` |
| Target deploy | 55% equity | `FORTRESS_TARGET_DEPLOY_FRAC` |
| BP use | 50% | `FORTRESS_BP_USE_FRAC` |
| Index new buys | **BANNED** | `FORTRESS_BAN_INDEX_BUYS` + `HFT_BAN_INDEX_BUYS` |
| Index rebuy | **BANNED** | `FORTRESS_NO_REBUY_SYMBOLS=SPY,QQQ,IWM,…` |
| Add-on / DCA | off | `FORTRESS_ALLOW_ADD_ON=false` |
| Monthly DD halt | 20% | keep ON |
| Micro-scalp | paused | PDT-aware sleeve left off |

---

## FORCE / STICK path (why predicted-UP must buy)

Root cause (see `STICK_LOCKIN_NOTES.md`): soft gates + index slot spam beat singles; STICK was score-only; BX had no earnings stick.

**Locked ON in `data/deploy_scale.env`:**

- `PRED_FORCE_BUY=true` · `PRED_FORCE_MIN_P=0.60` · boost `0.35`
- `EARNINGS_STICK_FORCE_BUY=true` · day-of buy · stick boost
- `FORTRESS_FORCE_BUY_SYMBOLS=BX,SBUX,COST,WMT,NOW,CRM,JNJ,AAPL,AMZN,META,NVDA,AMD,AVGO,MSFT`
- Watch file: `data/ops/force_buy_watch.json` (+ HFT mirror)

**RTH open checklist**

1. Fortress heartbeat fresh (`data/fortress_heartbeat.txt`).
2. Log lines contain **FORCE PRED BUY** / **FORCE STICK BUY** for UP names — not watch-only.
3. Rotation pins `force_priority` ahead of ETF noise (`analytics/trade_rotation.py`).
4. Day-trade via **`./run_all.sh ensure-day-trade`** (never `start day-trade` as the ensure path).

---

## Concrete symbol pipelines for RTH

### A — Must-act (sticky / missed)

| Symbol | Why | Action at open |
|--------|-----|----------------|
| **BX** | Predicted UP, missed; **daily model rebuilt overnight** (`models/BX_model.pkl`) | FORCE BUY to ≤10% if `p_up≥0.60` / force list; do **not** let SPY/QQQ take the slot |
| **SBUX** | Earnings day-of held (~9.5%); daily model restored after FRESH rebuild | **HOLD** — no churn; trim only if overweight >10% |
| **COST, WMT, NOW, CRM, JNJ** | Cramer hot / high tilt | FORCE scan; size ≤10% each if pred/gates agree |

### B — Earnings radar (calendar `2026-07-30`, verify live)

Liquid / quality names flagged near session: **AAPL (amc), AMZN (amc), AEP/AGCO/ALNY/ADT (bmo), AJG (amc), AMGN**.  
Treat calendar as **input to STICK**, not automatic market orders — confirm hour + print before size-up.

### C — HFT / OBI whitelist (singles first)

`NVDA,AMD,TSLA,MSFT,NFLX,AMZN,AAPL,META,GOOGL,SBUX,BX,AVGO` — index ETF buys banned in micro-MR.

### D — Horizon sleeves (all keep running)

| Sleeve | Role at open |
|--------|----------------|
| Fortress / intraday | Primary FORCE/STICK deploy of cash |
| HFT OBI | Tape/OBI singles; no index rebuy |
| Day-trade | `ensure-day-trade` — RTH scalp/rotation within PDT discipline |
| Weekly / longterm | 5d / 20d paper_sim bias — do not flatten SBUX |
| Pattern / bottom-fisher / Cramer | Signal boost into rank — not sole trigger |

**Pipeline:** data (NETWORK_FIRST Yahoo/Alpaca) → features → models → signals → **FORCE/STICK** → execution across HFT/fortress/day/weekly/longterm.

---

## Overnight → open timeline (PT)

| When | Action |
|------|--------|
| Now → 01:00 | Keep train-gaps / LSTM-all / enhancement-queue / strengthened retrain-weak; talk harness climb (edits locked until 1B) |
| 01:00–03:30 | Earnings radar refresh; force_buy_watch intact; slim caches only if disk <10G free — **never delete models/** |
| 03:30–06:00 | Confirm all trade PIDs RUNNING; `refresh-paper` only if env drift (trainers untouched) |
| 06:30–09:30 ET (03:30–06:30 PT) | Pre-market: fortress extended + HFT; stage FORCE list; no new SPY/QQQ/IWM |
| RTH open | Sticky buys on FORCE list; deploy toward 55% with singles; log trade-reasons |

---

## Training (optimize, never remove)

- Universe **11959** — full; no shrink.
- Keep: `train` (letter_rr gaps), `train-intraday`, `train-lstm` (all), `enhancement-queue` **full**, `retrain-weak` / strong loop, priority file `data/priority_force_train.json` (**BX** first).
- Talk: `talk-overnight` + `talk_massive_harness --continue` + `train_talk_reward` — climb as far as overnight allows; **do not claim 1B early**; `TALK_ALLOW_EDITS=false` until gate.
- `NETWORK_FIRST=true`; `./run_all.sh slim-disk` = caches only.
- Quality audit: `data/ops/MODEL_QUALITY_AUDIT.md` — strengthen weak (meta≥0.55), re-queue, never drop names.

---

## Self-learn / keepalive

```bash
./run_all.sh stack-watchdog          # KEEP_WATCHDOG_ON_STOP=true
./run_all.sh ensure-intraday
./run_all.sh ensure-subsecond
./run_all.sh ensure-weekly
./run_all.sh ensure-longterm
./run_all.sh ensure-day-trade
./run_all.sh ensure-self-improve
./run_all.sh ensure-free-agent
./run_all.sh ensure-cortex
./run_all.sh ensure-paper-awake
./run_all.sh ensure-paper-hygiene
./run_all.sh ensure-execution-monitor
./run_all.sh ensure-training
```

Also keep: stack-autotune, pattern-anomaly-watch, bottom-fisher, universe-lifecycle, industry-ai, hft-rotator, hft-news-watch. **Do not `pause-all`.** Do not kill trainers when restarting trade heads.

HFT: dist fresher than src as of plan write — rebuild only if TS changes (`./run_all.sh hft-build`).

---

## Success criteria (measurable, not fantasy P&L)

1. BX (or next FORCE UP) **actually bought** if pred/stick fires — not watch-only.
2. Zero new SPY/QQQ/IWM adds; SBUX still held unless hard risk exit.
3. Idle cash deployed into **singles** toward ~55% without >10%/name.
4. All trade + train + talk + self-learn PIDs RUNNING at open.
5. Talk `% of 1B` higher than overnight start; edits still locked.
6. Model coverage / weak queue progressing (`MODEL_QUALITY_AUDIT` counts move pass↑ / pending↓).

If the tape does not offer edge, capital preservation under caps beats forced hero trades.
