"""
Agent-editable extension hooks — safe surface for self-modifying rank/execution logic.
GENERATION=31253  RATIONALE='grow_equity — deploy idle capital'
Objective: Make portfolio account larger
"""

VERSION = 1
GENERATION = 31253
RATIONALE = 'grow_equity — deploy idle capital'


def equity_rank_boost(symbol: str, score: float, metrics: dict) -> float:
    boost = 0.0
    if float(metrics.get('deployed_frac') or 0.0) < 0.60:
        boost += 0.025
    if float(metrics.get('equity_delta') or 0.0) <= 0:
        boost += 0.02
    return max(-0.08, min(0.08, float(boost)))


def fortress_size_mult(metrics: dict) -> float:
    mult = 1.0
    if float(metrics.get('deployed_frac') or 0.0) < 0.65:
        mult += 0.08
    return max(0.85, min(1.25, float(mult)))


def policy_priority_hints(metrics: dict) -> dict:
    hints: dict = {}
    hints["ORDER_NOTIONAL"] = min(float(metrics.get("cur_notional", 8000)) * 1.08, 48000.0)
    hints["BUY_THRESHOLD"] = max(0.52, float(metrics.get("cur_buy", 0.55)) - 0.012)
    return hints
