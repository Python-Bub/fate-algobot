"""
Bridge to analytics.value_investing — classic value formulas and screens.
"""

from __future__ import annotations

from analytics.value_investing import (
    analyze_value,
    intrinsic_value,
    is_graham_net_net,
    margin_of_safety,
    ncav,
    terminal_value,
    value_investing_rank_boost,
)
from investing.formulas.value_extras import (
    graham_buy_below_ncavps,
    graham_number,
    nnwc,
    owner_earnings,
)

__all__ = [
    "intrinsic_value",
    "terminal_value",
    "ncav",
    "is_graham_net_net",
    "margin_of_safety",
    "analyze_value",
    "value_investing_rank_boost",
    "owner_earnings",
    "nnwc",
    "graham_number",
    "graham_buy_below_ncavps",
]
