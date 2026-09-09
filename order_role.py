"""Which host may POST orders to Alpaca paper.

Laptop + trainer VMs must not dual-order the same account as the GCP paper box.
Set FATE_ORDER_ROLE=gcp-paper on fate-algobot-paper; Mac forever defaults to observe.
"""

from __future__ import annotations

import os
import socket


def hostname() -> str:
    return (os.getenv("HOSTNAME") or os.getenv("HOST") or socket.gethostname() or "").lower()


def order_role() -> str:
    hn = hostname()
    if "algobot-paper" in hn:
        return "gcp-paper"
    if "algobot-trainer" in hn:
        return "train"
    if os.getenv("FATE_ALLOW_LOCAL_ORDERS", "").lower() in ("1", "true", "yes"):
        raw = (os.getenv("FATE_ORDER_ROLE") or "").strip().lower()
        return raw or "observe"
    return "observe"


def orders_allowed_here() -> bool:
    """True only on the GCP paper VM (or an explicit order role)."""
    role = order_role()
    if role in ("observe", "mac", "train", "none", "off"):
        return False
    if role in ("gcp-paper", "order", "paper-vm"):
        return True
    return "algobot-paper" in hostname()
