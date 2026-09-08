"""Backward-compatible shim — picks are generated dynamically by club_conviction_engine."""

from intel.club_conviction_engine import (
    proven_pick_boost,
    proven_pick_tickers,
    refresh_dynamic_conviction,
)

__all__ = ["proven_pick_boost", "proven_pick_tickers", "refresh_dynamic_conviction"]
