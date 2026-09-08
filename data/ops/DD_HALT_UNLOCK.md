# Monthly DD halt unlock — 2026-07-30

## Root cause
`data/risk/monthly_equity.json` had `peak_equity=100000` vs live equity ~$75,215 → DD≈24.8% ≥ `MONTHLY_DRAWDOWN_HALT_PCT=0.20`.
FORCE/STICK fired but `risk_manager.monthly_drawdown_ok` rejected every buy. Book was already flat cash.

## Action (risk module KEPT)
- Backed up state → `data/risk/monthly_equity.json.bak_pre_unlock`
- Re-baselined `peak_equity` and `start_equity` to current equity `$75,214.98`
- `USE_MONTHLY_DRAWDOWN_HALT=true` and `MONTHLY_DRAWDOWN_HALT_PCT=0.20` unchanged — halt re-arms if we bleed 20% from the new peak
- Cleared day-trade session halt via `clear_trading_halt()`

## Why not disable
Optimize-never-remove: do not kill monthly DD protection. Peak was a stale $100k paper ceiling vs post-trim cash book; re-baseline after forced flat is the recovery path.
