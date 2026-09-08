"""Extra value formulas (Buffett owner earnings, NNWC, Graham number)."""

from __future__ import annotations


def owner_earnings(
    net_income: float,
    da: float,
    *,
    maintenance_capex: float,
    delta_wc_maint: float = 0.0,
) -> float:
    """
    Buffett owner earnings ≈ NI + D&A − maintenance CapEx − maint. ΔWC.
    """
    return float(net_income) + float(da) - float(maintenance_capex) - float(delta_wc_maint)


def nnwc(
    cash: float,
    receivables: float,
    inventory: float,
    total_liabilities: float,
    *,
    ar_haircut: float = 0.75,
    inv_haircut: float = 0.50,
) -> float:
    """
    Net-Net Working Capital (stricter Graham):
    NNWC = Cash + h_ar·AR + h_inv·Inv − Total Liabilities
    """
    return (
        float(cash)
        + float(ar_haircut) * float(receivables)
        + float(inv_haircut) * float(inventory)
        - float(total_liabilities)
    )


def graham_number(eps: float, bvps: float) -> float:
    """P_max ≈ √(22.5 × EPS × BVPS). Returns 0 if inputs non-positive."""
    eps = float(eps)
    bvps = float(bvps)
    if eps <= 0 or bvps <= 0:
        return 0.0
    return (22.5 * eps * bvps) ** 0.5


def graham_buy_below_ncavps(price: float, ncavps: float, *, frac: float = 2.0 / 3.0) -> bool:
    """True if P ≤ frac × NCAVPS (classic Graham ~2/3 rule)."""
    if ncavps <= 0 or price <= 0:
        return False
    return float(price) <= float(frac) * float(ncavps)
