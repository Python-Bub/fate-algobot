# Sell / rotate / conviction sizing — 2026-07-30

## Principles (no emotions)
1. **Size by conviction** — high confidence / low risk → buy closer to the 10% single-name cap; weak / high pressure → small probe only (`analytics/conviction_exit.conviction_size_mult`).
2. **Modest diversification** — ~12 names max (`FORTRESS_MAX_POSITIONS`), not 28 equal slots.
3. **Take profit / rotate** — at ~+0.8% scale out 50%; at full TP close; if green and capital needed for better names, trim ~40%.
4. **Thesis death ≠ noise** — sell permanent damage only when loss ≥ ~1.2% **and** ≥2 confirms (model sell, pred flip, hard pressure, earnings fear-dump). Lone `p_adj` flicker → **NOISE_HOLD**.
5. **Hard stop** still cuts structural risk (~2.5%, tighter near earnings).
6. **Trade quality** tracked in `data/ops/trade_quality.json` (MFE/MAE/quality).

## Priority order (open long)
1. Confirmed thesis death → full exit  
2. Stop-loss → full exit  
3. Take-profit → full exit  
4. Scale-out / rotate-on-profit → partial trim  
5. Signal sell (confirmed) → full exit  
6. Else hold  

## HFT
Separate microstructure sleeve. Must place orders in session (`OBI_TRIGGER_*` softened). Never wipe fortress overnight qty (sleeve-scoped closes).

## Knobs
See `data/deploy_scale.env` (`FORTRESS_CONVICTION_*`, `FORTRESS_SCALE_OUT_*`, `FORTRESS_THESIS_DEATH_*`, `FORTRESS_SIGNAL_SELL_*`).
