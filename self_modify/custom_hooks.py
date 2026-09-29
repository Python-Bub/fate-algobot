"""
Agent-editable extension hooks — safe surface for self-modifying rank/execution logic.
GENERATION=34940  RATIONALE='grow_equity — high-conviction tilt'
Objective: Make portfolio account larger
"""

VERSION = 1
GENERATION = 34940
RATIONALE = 'grow_equity — high-conviction tilt'


def equity_rank_boost(symbol: str, score: float, metrics: dict) -> float:
    boost = 0.0
    p = float(metrics.get('p_up') or metrics.get('neural_p_up') or 0.5)
    if p > 0.60:
        boost += 0.03
    return max(-0.08, min(0.08, float(boost)))


def fortress_size_mult(metrics: dict) -> float:
    mult = 1.0
    if float(metrics.get('equity_delta') or 0.0) > 0:
        mult += 0.04
    return max(0.85, min(1.25, float(mult)))


def policy_priority_hints(metrics: dict) -> dict:
    hints: dict = {}
    hints["BUY_THRESHOLD"] = max(0.52, float(metrics.get("cur_buy", 0.55)) - 0.008)
    return hints
