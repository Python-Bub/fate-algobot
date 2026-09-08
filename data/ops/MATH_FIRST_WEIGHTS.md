# Math-first weights + order dedupe

## Principle
No emotions in sizing. Model edge, exec confidence, structure, HF factors, value math ≫ news/Cramer/social.

## Fortress
- Math cluster ≈ **96%**
- Narrative (news+cramer+morning+social) = **4%**
- Cramer blend env cut 0.90 → **0.12**; news rank 0.14 → **0.04**

## Order dedupe
- Skip BUY if open buy already queued (`pending_buy_order`)
- Skip SELL if close already queued / unlock held_for_orders once
- No stacked identical buy/sell spam

## Apply
`apply_sleeve_env` with `MATH_FIRST_WEIGHTS=true` overwrites stale .env megablends.
