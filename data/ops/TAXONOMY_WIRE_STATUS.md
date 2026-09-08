# Taxonomy Wire Status

**2026-07-30 — MASSIVE wire pass**

## Book
- Canonical: `data/books/investing_guide_full.md` (~386 KB)
  - User paste: Introduction → Strategies → Macro → Alternative → Passive
  - Appendix: Advanced / Asset classes / Real assets / Sectors / Analysis from catalog (200 topics)
- Chapter index: `data/books/chapters/INDEX.md` (all 292 catalog ids)
- Stubs: part1 + curriculum_macro point to full guide (no conflicting duplicate body)

## Sleeve map
- `investing/knowledge/sleeve_curriculum_map.py` — **292** topic→sleeve tuples
- HFT forbidden: value/Buffett/Graham/DCA/Cramer essays/deriv/alt primary

## Weights
- `analytics/sleeve_weights.py` — all sleeves sum **100%**
- Index ETF allowed: 1/3/5/5/7% by sleeve
- Daily Cramer: day/fortress/weekly/LT > 0; HFT = 0
- Soft context: alt_context, derivatives_context on weekly/LT

## Diversification / HFT
- FORCE list shrunk (BX,NOW,CRM,SBUX) — PRED_FORCE/STICK still pin conviction
- `TRADE_COOLDOWN_HOURS=36`, score mult `0.12`, last-pick mult `0.55`
- Fortress max positions **28**, top buys/pass **22**, scan symbols **80**
- HFT: `HFT_MAX_ORDERS_PER_SEC=25`, per-ticker cooldown 800ms, broader OBI whitelist (~20)

## Training
- Resume train-gaps / train-intraday / LSTM / enhancement-queue (NETWORK_FIRST)
- Universe not shrunk

## Bans
- Index buy bans OFF; NO_REBUY + 10% cap ON
