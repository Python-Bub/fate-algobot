"""
Agent-editable extension hooks — safe surface for self-modifying rank/execution logic.
GENERATION=35612  RATIONALE='stop chasing losses — tighten when equity is down'
Objective: Make portfolio account larger
"""

VERSION = 1
GENERATION = 35612
RATIONALE = 'stop chasing losses — tighten when equity is down'


def equity_rank_boost(symbol: str, score: float, metrics: dict) -> float:
    boost = 0.0
    # Do not boost every name just because the account is red or cash is idle.
    # That was buying more while equity fell.
    if float(metrics.get('equity_delta') or 0.0) > 0 and float(metrics.get('deployed_frac') or 0.0) < 0.60:
        boost += 0.015
    return max(-0.08, min(0.08, float(boost)))


def fortress_size_mult(metrics: dict) -> float:
    mult = 1.0
    delta = float(metrics.get('equity_delta') or 0.0)
    if delta < 0:
        mult -= 0.08
    elif float(metrics.get('deployed_frac') or 0.0) < 0.65:
        mult += 0.05
    return max(0.85, min(1.25, float(mult)))


def policy_priority_hints(metrics: dict) -> dict:
    hints: dict = {}
    cur_n = float(metrics.get("cur_notional", 8000) or 8000)
    cur_buy = float(metrics.get("cur_buy", 0.55) or 0.55)
    delta = float(metrics.get("equity_delta") or 0.0)
    if delta <= 0:
        hints["ORDER_NOTIONAL"] = max(500.0, cur_n * 0.90)
        hints["BUY_THRESHOLD"] = min(0.72, cur_buy + 0.01)
    else:
        hints["ORDER_NOTIONAL"] = min(cur_n * 1.04, 12000.0)
        hints["BUY_THRESHOLD"] = max(0.55, cur_buy)
    return hints
