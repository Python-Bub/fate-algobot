# STICK + LOCK-IN notes — 2026-07-29

## Root cause: missed SBUX / BX buys

### SBUX (earnings day-of, then +~5%)
1. **`encourage_pre_momentum` was false on `dte=0`** until `EARNINGS_BUY_DAY_OF` — radar watched SBUX but did not treat day-of as a buy window.
2. **STICK was score-only, not force-buy.** Even after day-of encourage, fortress only *boosted* score if soft gates already passed (`want_buy`). Volume / MTF / JP / news soft gates → watch-only; QQQ/SPY/IWM filled slots instead.
3. **`stick_to_prediction` was always `True`** for every symbol (meaningless), so the STICK path never meant “earnings stick → must size.”
4. Late buy (~66 @ $109, ~9.5% equity) happened only after the partial day-of fix.

### BX (predicted UP, +~4%, never bought)
1. **Not in earnings window** (`dte≈84`) → no earnings STICK priority / force-scan.
2. **No general “high-conviction UP → FORCE buy” path** — prediction could be right and still lose the pass to index ETF favorites.
3. Soft gates + letter diversify + index churn crowded single-name UP names out of `top_buys`.

## What we changed

| Area | Change |
|------|--------|
| `intel/historical_events.py` | `stick_to_prediction` only true in pre/day-of encourage window |
| `fortress_live.py` | **FORCE STICK BUY** + **FORCE PRED BUY** (`PRED_FORCE_*`); heartbeat file; force-scan from env + `data/ops/force_buy_watch.json` |
| `analytics/trade_rotation.py` | `force_priority` candidates pinned first (beat index spam) |
| `hft/.../micro-mean-reversion.ts` | Ban index ETF buys; no rebuy if SPY/QQQ/IWM/… already held |
| `data/deploy_scale.env` | Ban list expanded; `EARNINGS_STICK_FORCE_BUY`; `PRED_FORCE_*`; `FORTRESS_FORCE_BUY_SYMBOLS=BX,SBUX`; OBI whitelist single-name first; hang idle 2400s |
| `tools/stack_watchdog.py` | Heartbeat-aware hang kill (default 2400s); **single-instance flock** |
| `run_all.sh` | `KEEP_WATCHDOG_ON_STOP=true` — `stop` no longer kills watchdog (was leaving cores dead) |

Risk caps still apply: **10% single-name**, cash/BP, `FORTRESS_BAN_INDEX_BUYS` (no new SPY/QQQ/IWM adds).

## Why processes “randomly” stopped

1. **`cmd_stop` killed `stack-watchdog`** → nothing restarted cores; status showed STOPPED minutes after start.
2. **`pause-all` → `cmd_stop` + `pkill daemon_loop`** mass-killed weekly/longterm/day-trade/etc.
3. **`FORTRESS_HANG_WATCH` @ 600s log idle** thrash-killed fortress during long quiet feature builds (dozens of hang_kill events in `data/watchdog_log.jsonl`).
4. Multiple watchdog starts without a lock → restart thrash.
5. **Watchdog blocked on Cramer sync / autorun BEFORE ensuring cores** (up to 5–120 min) — looked like “watchdog RUNNING but not restarting.”
6. Wrong invocation: `./run_all.sh start day-trade` is not the ensure path — use `./run_all.sh ensure-day-trade` or `./run_all.sh day-trade`.

## Keep the stack alive

```bash
./run_all.sh unpause                 # if paused
./run_all.sh stack-watchdog          # supervisor (kept on stop)
./run_all.sh ensure-intraday
./run_all.sh ensure-subsecond
./run_all.sh ensure-weekly
./run_all.sh ensure-longterm
./run_all.sh ensure-day-trade        # NOT: start day-trade
./run_all.sh status
```

- Leave **paper-awake / caffeinate** on AC power; lid-close still kills local processes unless launchd + awake.
- Do **not** run `pause-all` unless you intend a full halt (it still pkill’s daemon loops).
- Watchdog lock: `data/stack_watchdog.lock` — only one supervisor.
- Heartbeat: `data/fortress_heartbeat.txt` — hang kill uses this + log, idle ≥ 2400s.
- Watchdog now **ensures trading cores first**, then runs Cramer/intel side jobs.
- **OBI wrapped in `daemon_loop.sh`** (5s retry) so WS drops / SIGTERM cannot leave HFT permanently STOPPED.

## Positions snapshot (at fix time)

- Equity ~$75.4k — **SBUX 66sh held (~9.5%)**; IWM/SPY/QQQ ~10% each (no further index adds); **BX not held** (now on FORCE watch for next pass).
