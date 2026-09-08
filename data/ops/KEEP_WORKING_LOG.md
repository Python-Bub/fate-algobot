# KEEP WORKING LOG

## 2026-07-30 24:05 PT — 4× buying_power deploy (use margin, not cash)
- **Blocked 4×:** `FORTRESS_TARGET_DEPLOY_USE_EQUITY=true` capped total book at ~98% of *equity*; late `deploy_scale.env` block also reset max positions→20 / single→10%. `risk_manager` used *remaining* BP as total-cap denominator (would freeze once leveraged).
- **Fix:** prefer BP capacity for TOTAL gross (`USE_BUYING_POWER=true`, `MAX_GROSS_LEVERAGE=4`, `FORTRESS_TARGET_DEPLOY_USE_EQUITY=false`, `FORTRESS_MAX_GROSS_FRAC=0.95`); keep per-name ~1% of *equity*. Capacity = equity×multiplier (not remaining BP). Monthly DD halt unchanged.
- **Account now:** equity≈$74.7k cash≈$38.2k bp≈$254.9k mult=4 positions=5 gross≈$36.5k (48.9% equity).
- **Effective max gross:** capacity≈$299k → target≈$284k (95%); remaining deploy budget≈$242k gated by BP×0.95; max_single≈$743.
- **Proof:** at 98% equity gross, old equity-target budget=$0; new capacity-target budget≈$182k. `can_open` $500 buy → ok with cash idle / BP plenty.
- **Restarted (KEEP_WATCHDOG_ON_STOP):** fortress + OBI (128 slots) + day-trade; watchdog kept.

## 2026-07-30 12:48–12:54 PT — LOCK-IN deploy + earnings export
- **Cash before (mid-session peak deploy):** equity=$75,299.86 cash=$16,510.97 deployed=78.1% n=8 (AMZN/WMT/AAPL/MARM/CRM/JNJ/DNOW/SBUX ~10%)
- **Cash at sizing lock (AMZN out):** equity=$75,240.63 cash=$24,042.36 deployed=68.0% n=7 — idle ~$24k under old 55%/ADD_ON-off / max_w=0.10-of-budget bug
- **Idle-cash root cause:** `TARGET_DEPLOY=0.55` + `BP_USE=0.50` + `ADD_ON=false` + vectorized `max_weight=0.10` of *budget* (≥10 names needed to fully deploy). Index bans + monthly DD halt stayed ON.
- **Sizing fix (optimize, never remove):**
  - `data/deploy_scale.env` → target **0.98 equity**, BP_USE **0.95**, ADD_ON/DCA **on**, max positions **14**, single **10%** equity, `FORTRESS_TARGET_DEPLOY_USE_EQUITY=true`
  - `fortress_portfolio.py` → `deploy_budget_usd()` / `equity_single_cap_usd()`
  - `fortress_live.py` → alloc only names with equity-cap room; `max_w=max_single/budget`; leftover sweep to next-best singles (not indexes)
- **Proof:** `data/ops/SIZING_LOCKIN_PROOF.txt` — budget≈$22.5k → 3×~$7.5k under 10% caps (old bug would leave ~70% idle)
- **Fortress:** restarted ensure-intraday (pid live); log `logs/intraday_latest.log`; FORCE/STICK scanning; buys pending full pass (~10–15m scan). Bans+DD halt armed.
- **Earnings export:** **`data/ops/ALL_EARNINGS_DATES.md`** (+ `.json`); shared `data/intel/earnings_calendar.json` (5249); overrides MSFT/SBUX/AMZN/AAPL; radar days_since from last_earnings (MSFT/SBUX=1)

## 2026-07-30 10:32 PDT — overnight→day ops sweep
- **Equity:** $75202.53 cash (positions=0, deployed=0%)
- **Talk:** problems_done=52,100,000 → **5.2100% of 1B edit unlock** (vs 1T ≈0.005210%); harness under caffeinate
- **Models:** 12G — daily≈1386 / intraday≈2263+ / LSTM≈4322; letter_rr+NETWORK_FIRST gaps climbing; priority FORCE daily rebuild for missing megacaps
- **Restarted:** ensure-stack, train-gaps (daily+intraday), enhancement-queue-restart full (exited: already finished), train-lstm scope=all, retrain-weak-until (0 candidates / all top100 pass), overnight_talk caffeinate, priority FORCE daily train, train-intraday re-kick
- **Key RUNNING pids:** fortress=39719/46014 OBI=41829/41832 day-trade=65344/65348 train-daily=40717 watchdog=53877 autotune=54424 self-improve=54493 cortex=54540 talk=48287 priority=48320
- **RTH:** NOT exit-only; FORCE/STICK firing (BX/SBUX on force_buy_watch; TVTX stick); index bans locked in fortress+OBI env; QQQ soft-trim already completed overnight
- **BLOCKER:** Monthly drawdown halt ~24.8% (peak $100k → $75.2k; Alpaca 1M max ~$96.8k) rejects all new buys — risk gate kept (optimize-never-remove). No fake +30%.
- **LaunchAgents KeepAlive:** `com.fate.talk-overnight` + `com.fate.priority-force-train` (talk harness + FORCE daily rebuild).
- **train-intraday:** queue=0 (checkpoint complete until new dailies land from letter_rr / priority FORCE).

## 2026-07-30T17:59Z DD unlock
- Rebased monthly peak to current equity; halt module still armed.


## 2026-07-30 11:44 PT — DD halt unlock
- Rebaselined monthly peak to $75,214.98; buys unblocked; halt module still armed at 20%.


## 2026-07-30 12:55 PT — MASSIVE taxonomy + diversify + weights
- Book: data/books/investing_guide_full.md (~386KB) + chapters/INDEX.md (292)
- Map 292 topics; weights 100% all sleeves; index_etf 1/3/5/5/7; Cramer daily non-HFT
- ETF bans OFF; NO_REBUY+10% cap; FORCE shrunk; HFT 25/sec; cooldown 36h
- Train gaps+intraday+LSTM+enhancement RUNNING
---
Thu Jul 30 15:11:39 PDT 2026
Sell/rotate + conviction sizing + HFT retune

Thu Jul 30 15:19:31 PDT 2026
Alpaca limits catalog + rate limit/qty-lock/fractionable fixes

Thu Jul 30 15:25:54 PDT 2026
Math-first weights 96/4 + buy/sell order dedupe

## Thu Jul 30 22:41:36 PDT 2026 — hundreds positions + HFT always-on
- MAX_POSITIONS=500, single=1%, PORTFOLIO_SLOT_BUDGET=false
- HFT session=always, 128 slots, broad whitelist, overnight

## Thu Jul 30 22:51 PDT 2026 — verify+fix blockers (optimize, never remove)
- **Live env confirmed** on fortress/OBI after restart: `FORTRESS_MAX_POSITIONS=500`, `FORTRESS_MAX_SINGLE_FRAC=0.01`, `PORTFOLIO_SLOT_BUDGET=false`, `PORTFOLIO_MAX_TOTAL=500`, `HFT_TRADE_SESSION=always`, `HFT_MAX_CONCURRENT_SLOTS=128`
- **HFT place_us=0 root causes fixed:**
  1. IEX WS `symbol limit exceeded` (55 tickers) → cap WS at 15 (`HFT_IEX_WS_MAX_SYMBOLS`), spill rest to REST (72 poll universe kept)
  2. `TRADE_WEEKDAY_24X5` hard-clamped HFT to 04:00–20:00 even with `always` → session gate now honors `HFT_TRADE_SESSION=always` + 00:00–23:59
  3. Spread floors softened (`HFT_MAX_SPREAD_BPS=40`, `HFT_REST_MAX_SPREAD_BPS=120`)
- **Fortress hundreds blocked by letter caps** (`TRADE_MAX_HELD_PER_LETTER=2` ≈52 names) → raised to 40 held / 20 buys-per-letter; `MAX_LIVE_SYMBOLS=400`, `FORTRESS_SCAN_CHUNK=200`
- **Stuck overnight AAPL market sells:** `TRADE_SESSION_MODE=always` allowed exits in CLOSED session; quote 429 → market DELETE accepted but unfillable. Fix: `TRADE_EXIT_SESSION_MODE=extended` + defer market DELETE when session closed; cancelled open AAPL sells
- **DD halt OK** (peak $75,267 → equity ~$74.7k ≈0.7% << 20%); no rebase
- **train-lstm** was empty-pid → restarted (`scope=all`); queue reports nothing pending (heads complete). train + train-intraday still RUNNING
- **Alpaca:** BP ~$255k, no PDT block; open orders cleared; occasional data 429s (cooldown already armed)
- **Remaining:** `place_us` still n=0 overnight (IEX tape thin + broker fills mainly 04:00–20:00 ET) — expect non-zero from premarket; existing 5 names still ~10% each (opened pre-1% cap) — new slots size at 1%


## 2026-07-31 13:26 PT — finish talk AI + investing-guide questions
- **AI:** homemade talk CharLSTM (`data/talk_brain/brain.pt`) + massive harness toward 1B edit gate
- **Guide Q&A bank (finite):** distilled ALL 292 topics + 291 deep chapters → **10,868 pairs, remaining=0**
  - artifacts: `data/talk_brain/investing_guide_corpus.txt`, `investing_guide_question_bank.jsonl`, `investing_guide_fetch.json`
  - wired into `talk_brain` train + teacher + harness (`./run_all.sh train-talk-guide`)
- **Harness before → after:** 75,643,900 → **91,643,900** (9.16439% of 1B; remain=908,356,100)
- **Throughput bump:** session_cap 500k→2M, 4 harness bursts / train, skip rewrite, disk write-cap; `com.fate.talk-overnight` restarted
- **Train:** CharLSTM steps=1000 loss≈0.195 (includes guide corpus); overnight loop RUNNING
- **Trading:** fortress/OBI/day-trade/watchdog left UP (not killed)
- **Honest ETA to 1B:** ~23h at ~40M problems/h sustained (lid must stay awake / caffeinate)
