# FATE_AlgoBot HFT Module

Ultra-low-latency Node.js/TypeScript layer for the **sub-second** trades that
drive the main P&L.  The Python side (`fortress_live.py`, `paper_sim_today.py`)
handles the slower day/week horizons — and Cramer's signals are **explicitly
excluded from this module** because they are not informative at microstructure
timescales (see §28 of `docs/DECISION_LOGIC.md`).

Two independent algorithms live here:

| Algorithm | Latency budget | Source |
|-----------|----------------|--------|
| Earnings reaction | **<100 ms** ingest→fire | `src/earnings/` |
| OBI + Tape Velocity | **<10 ms** per L2/tape update | `src/obi-tape/` |

Both speak Alpaca paper by default (`HFT_DRY_RUN=true` until you flip it).

## Install

```bash
cd hft
npm install
npm run build
```

Node ≥ 20 is required (`process.hrtime.bigint`, `Float64Array`, native
`AbortSignal.timeout`, undici v6).

## Configure

Copy `.env.example` to `.env` (or just inherit from the project root `/.env`
— the config loader checks both).  The minimum to go live on Alpaca paper:

```ini
ALPACA_API_KEY=...
ALPACA_API_SECRET=...
ALPACA_BASE_URL=https://paper-api.alpaca.markets
HFT_DRY_RUN=false
```

For premium data wire one of these:

```ini
# Polygon.io / "Massive" — REST works on all plans; WebSocket needs the paid plan.
POLYGON_API_KEY=...
POLYGON_USE_WEBSOCKET=false        # flip true once on a paid Polygon plan
POLYGON_USE_LEVEL2=false           # flip true if you have the L2 add-on

# Benzinga premium news (optional; disabled by default for cost)
BENZINGA_API_KEY=...
```

When `POLYGON_USE_WEBSOCKET=false` (default), live streaming goes through
Alpaca's IEX WS — **free with the paper account** and confirmed working
out of the box.

## Run

```bash
# build once (or `npm run watch` while developing)
npm run build

# Earnings algo, sub-100 ms reaction
npm run earnings              # standard V8
npm run earnings:perf         # GC-quieted V8 flags

# OBI / Tape Velocity, sub-10 ms per update
npm run obi-tape
npm run obi-tape:perf
```

The `:perf` scripts add the following V8 flags (see `package.json`):

```
--no-warnings
--max-old-space-size=2048
--max-semi-space-size=256
--predictable-gc-schedule
```

These trade peak throughput for **lower GC-pause tail latency** during market
spikes.  Run-of-the-mill scripts (`npm run earnings`) keep V8 defaults for
day-to-day dev.

## What's in each phase

### Earnings (`src/earnings/`)

1. **Ingestion** — `ws` with `perMessageDeflate=false`, byte-level
   `Buffer.indexOf` ticker prefilter, `process.hrtime.bigint()` stamp.
2. **Evaluation** — Float64Array per-ticker state, zero-regex JSON number
   extractor (`jsonNumberAfter`), 10-second VWAP guard, top-of-book sizing.
3. **Execution** — `AlpacaExecutor` (warm undici Pool, ~4 ms p50 wire RTT),
   strict IOC limit at NBBO + tick offset, 400 ms fill deadline, 100 ms
   ingest-to-fire circuit breaker.
4. **Post-trade** — async file logging via `process.nextTick`, slippage in
   cents, fee tracking, hard "one earnings trade per ticker" lock.

### OBI + Tape (`src/obi-tape/`)

1. **L2 Book** — flat Float64Array(20) per ticker, top-5 levels, OBI computed
   on every delta, exchange→local clock skew histogram per ticker.
2. **Tape Velocity** — 100 ms rolling counter + 5 s baseline counter +
   continuous micro-VWAP, all backed by typed arrays.
3. **Dual-Signal Match** — bit-packed flag byte:
   `(F_OBI_LONG | F_TAPE_BURST) == 0b0101` fires a buy, mirror for short.
   IOC limit priced 1 tick aggressive.
4. **Risk** — micro-stop flattens when NBBO walks `OBI_MICRO_STOP_TICKS=3`
   ticks against entry; ticker locked for `HFT_PER_TICKER_COOLDOWN_MS=60000`
   ms after each fill to prevent toxic multi-fills.

## Safety / kill switch

- `HFT_DRY_RUN=true` — log orders, never POST.  Keep this on for paper
  rehearsal.
- `HFT_GLOBAL_KILL=true` — refuse to start the process (use in tooling /
  config-management).
- `HFT_MAX_ORDERS_PER_MIN=30` — hard ceiling regardless of signal volume.
- Per-ticker bit flag `F_LOCKED` + cooldown window in `KillSwitch`.

## Logs

`hft/logs/hft-YYYY-MM-DD.jsonl` — one event per line, async-written.
Fields are stable (use `jq` to filter):

```bash
jq -r 'select(.event=="earn_fire") | [.ts,.ticker,.side,.surprisePct,.wireMs] | @tsv' \
   hft/logs/hft-*.jsonl
```
