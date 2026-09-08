# FATE lock-in plan — 2026-07-29

## Critical bugs (money)
1. **Cross-sleeve wipe:** HFT/day/micro `closePosition` / `DELETE /v2/positions/{sym}` sells **entire** Alpaca qty. Long-term 100 + HFT 50 → HFT exit sells 150.
2. **Registry is one-owner-only:** `heads[NVDA]=fortress` cannot express split qty; HFT ignores slot ownership on exit.
3. **Current book:** short **NVDA −64** (unintended risk); equity ~$77.3k vs SOD ~$79.0k.

## Plan (execute now)
### P0 — Stop the bleed
- Sleeve-scoped closes: only sell `min(requested_sleeve_qty, available)`.
- Never Alpaca DELETE full position when other sleeves own shares.
- Track `qty_by_sleeve` in `portfolio_head_registry.json`.
- HFT flatten/orphan uses **open leg qty only**, never broker full qty.
- Cover/trim toxic unintended shorts.

### P1 — All timeframes online
- fortress, HFT OBI, day-trade, micro-scalp, weekly, longterm — RUNNING + heartbeats.
- Watchdog/daemon_loop KeepAlive.

### P2 — Missing data
- Earnings calendar, env, features NaN scrub — re-audit green.

### P3 — Finish trainings
- Letter-fair daily+intraday gaps, LSTM, enhancement, listing.
- Talk 1B harness: unstick if looping tests-only; resume teacher `--continue`.

### P4 — Permanent uptime
- launchd watchdog; no silent stopped cores.

## Honesty
Cannot guarantee markets only go up. Can guarantee: no cross-sleeve wipe, processes stay up, training progresses.
