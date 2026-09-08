"""
Sum-of-the-parts (SOTP) valuation — book chapter alignment.

Sum-of-the-parts values each business segment separately and aggregates them,
often revealing a conglomerate discount when the consolidated stock price
trades below the implied breakup value.

  SOTP equity = Σ segment values − net debt
  Conglomerate discount = (SOTP equity − market cap) / SOTP equity

Positive discount ⇒ market undervalues the parts vs the whole.
"""

from __future__ import annotations

from investing.formulas.analysis import (
    comps_implied_price,
    conglomerate_discount,
    enterprise_value,
    ev_ebitda,
    sotp_equity,
)

__all__ = [
    "sotp_equity",
    "conglomerate_discount",
    "enterprise_value",
    "ev_ebitda",
    "comps_implied_price",
]
