# Why we didn't call MSFT earnings "crazy good"

## What happened
- **MSFT printed FY26 Q4 on 2026-07-29** (AMC / call 2:30 PT) — strong AI/cloud print.
- Our shared calendar still said **`next_earnings_date=2026-10-27` (dte≈89)** after Finnhub rolled forward — so **earnings STICK day-of never armed**.
- Stack does **price-direction / stick-to-bullish-model**, not an EPS-beat / "crazy good" fundamental predictor.

## What the bot did instead
- Jul 29 night: FORCE list included MSFT but **Yahoo cooldown → no price features** (couldn't score).
- Jul 30 RTH: repeatedly **`headwind skip BUY MSFT — 9.5% weekly drop; technical gap down`** while treating earnings as 89 days away.
- Peer note: `AMZN earnings in 0d` risk restrict — wrong mega-cap print focus.

## Fix applied
- Calendar override: `last_earnings_date=2026-07-29` + note on MSFT entry.
- Refresh calendar job kicked; need mega-cap print detection so Finnhub roll-forward doesn't erase day-of/day-after STICK window.
