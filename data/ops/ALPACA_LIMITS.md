# Alpaca limits reference (paper + live) — 2026-07-30

We kept hitting limits because this catalog was missing from the bot.  
Code source of truth: `analytics/alpaca_limits.py`.

## What we were hitting (this account / logs)

| Hit | Code / symptom | Fix |
|-----|----------------|-----|
| **Data API 429** | `quotes/latest` Too Many Requests | Token bucket 180/min + quote cache + Retry-After cooldown |
| **403 insufficient qty / held_for_orders** | Sell while qty locked in open sell orders | Cancel open sells → wait → retry; never double-submit full qty |
| **403 not fractionable** | e.g. BCGS fractional notional | Whole-share snap / skip fractional |
| **No quote → order fail** | 429 cascade then "no quote" | Cache last good quote; pace data calls |
| **NewsAPI 429** | External (not Alpaca) | Already disables for process |

## Market Data (Trading API — Basic / free)

| Limit | Value |
|-------|------:|
| Historical / data HTTP RPM | **200 / min** |
| Real-time equities | **IEX only** |
| Websocket symbol subscriptions | **30** |
| Historical restriction | latest **15 minutes** delayed SIP-equivalent rules apply on Basic |
| Algo Trader Plus | 10,000 / min, full SIP, unlimited WS symbols ($99/mo) |

**Action:** stay under ~180 data calls/min across fortress + day + HFT REST quotes. Prefer WS for HFT; cache REST quotes ≥8s.

## Trading REST

| Topic | Notes |
|-------|--------|
| Rate limits | Correspondent-level; watch `X-RateLimit-*` + `Retry-After`; 429 → exponential backoff |
| Soft self-cap | `ALPACA_ORDERS_PER_MIN_SOFT` (default 30) |
| Max open orders | Soft self-cap `ALPACA_MAX_OPEN_ORDERS` (40) — cancel stale before new exits |
| Min notional | Broker + our `MIN_ORDER_NOTIONAL` |
| Extended hours | Limit orders only for many paths; market may reject AH |
| Fractional | Asset must have `fractionable=true`; else integer shares |

## Buying power / margin (post-PDT, Jul 2026)

| Legacy PDT | New Intraday Margin Rule |
|------------|--------------------------|
| 3 day trades / 5 days under $25k | **Removed** |
| Fixed DTBP | **Dynamic `buying_power`** (intraday P&L included) |
| Day-trade margin call | **Intraday Margin Deficit (IMD)** |
| | Unmet IMD → risk of **90-day** restriction |

**Deprecated API fields (do not rely on):** `pattern_day_trader`, `daytrade_count`, `daytrading_buying_power`, `last_daytrading_buying_power`, `dtbp_check`.  
**Use:** `buying_power`, `equity`, `cash`, `multiplier`.

## Order qty locks

Alpaca rejects sells when `held_for_orders ≈ existing_qty` (another open sell already reserved shares).  
Always: list open orders → cancel sells for symbol → sleep briefly → place one exit.

## Paper vs live

Paper mirrors most trading rules but data feed is still rate-limited. Paper rejects can still be **403** with structured JSON (`code: 40310000`).

## Env knobs

```
ALPACA_DATA_RPM_BUDGET=180
ALPACA_DATA_429_COOLDOWN_SEC=35
ALPACA_QUOTE_CACHE_SEC=8
ALPACA_ORDERS_PER_MIN_SOFT=30
ALPACA_MAX_OPEN_ORDERS=40
ALPACA_REST_RETRIES=3
ALPACA_REST_CACHE_SEC=10
POST_ORDER_SYNC_MIN_SEC=20
```

## Ops check

```bash
./venv/bin/python -c "from analytics.alpaca_limits import summarize_for_ops; print(summarize_for_ops())"
```
