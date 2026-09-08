"""Conservative foundation-model + top-100 weighting helpers."""

from __future__ import annotations

import os


def top100_score_boost(is_top100: bool) -> float:
    """Additive rank boost for top-100 names (deprecated — use top100_rank_score_boost)."""
    if not is_top100:
        return 0.0
    return float(os.getenv("RANK_W_TOP100_BOOST", "0.35"))


def top100_rank_score_boost(symbol: str) -> float:
    """Graduated boost from market-cap rank (same formula for every top-100 member)."""
    try:
        from fortress_universe import is_top100_equity, top100_rank

        if not is_top100_equity(symbol):
            return 0.0
        rank = top100_rank(symbol)
        if rank is None:
            return float(os.getenv("RANK_W_TOP100_BOOST", "0.35")) * 0.5
        # Rank 1 → full boost; rank 100 → ~10% of full boost (linear, not name-specific).
        n = max(1, int(os.getenv("TOP100_COUNT", "100")))
        frac = max(0.1, 1.0 - (rank - 1) / max(1, n - 1))
        return float(os.getenv("RANK_W_TOP100_BOOST", "0.35")) * frac
    except Exception:
        return 0.0


def top100_score_multiplier(is_top100: bool) -> float:
    if not is_top100:
        return 1.0
    return float(os.getenv("TOP100_SCORE_MULT", "1.18"))


def foundation_blend_weight(is_top100: bool) -> float:
    """How much to trust online foundation forecast vs local GBDT."""
    if is_top100:
        return float(os.getenv("FOUNDATION_BLEND_WEIGHT_TOP100", "0.18"))
    return float(os.getenv("FOUNDATION_BLEND_WEIGHT", "0.08"))


def blend_foundation_safe(
    p_up_base: float,
    foundation_p: float | None,
    *,
    is_top100: bool,
) -> tuple[float, float, str]:
    """Blend foundation p_up into GBDT — dampen when models disagree (never override hard)."""
    if foundation_p is None:
        return float(p_up_base), 0.0, "none"

    p_base = float(max(0.0, min(1.0, p_up_base)))
    p_f = float(max(0.0, min(1.0, foundation_p)))
    w = foundation_blend_weight(is_top100)

    disagree = abs(p_f - p_base)
    if disagree > float(os.getenv("FOUNDATION_DISAGREE_DAMPEN", "0.22")):
        w *= float(os.getenv("FOUNDATION_DISAGREE_MULT", "0.35"))

    # Opposite side of 0.5 → minimal nudge only
    if (p_f - 0.5) * (p_base - 0.5) < 0:
        w *= float(os.getenv("FOUNDATION_OPPOSE_MULT", "0.20"))

    w = max(0.0, min(float(os.getenv("FOUNDATION_BLEND_MAX", "0.25")), w))
    try:
        from analytics.vector_math import lea_enabled, logit_pair_blend

        if lea_enabled():
            out = float(logit_pair_blend(p_base, p_f, w))
            return out, w, "blended_logit"
    except Exception:
        pass
    out = float((1.0 - w) * p_base + w * p_f)
    return out, w, "blended"
