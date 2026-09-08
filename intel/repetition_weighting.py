"""Repetition and thesis-persistence weighting.

Repeated independent mentions of the same thesis should matter more than a
single noisy headline, but duplicate repost spam should be discounted.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass


TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9]{2,}")


@dataclass
class RepetitionMetrics:
    unique_phrases: int
    repeated_phrases: int
    repetition_score: float
    diversity_score: float
    persistence_score: float


def _normalize(text: str) -> list[str]:
    return [t.lower() for t in TOKEN_RE.findall(text or "")]


def phrase_repetition_score(texts: list[str], ngram: int = 3) -> RepetitionMetrics:
    phrases: list[tuple[str, ...]] = []
    for t in texts:
        toks = _normalize(t)
        if len(toks) < ngram:
            continue
        for i in range(len(toks) - ngram + 1):
            phrases.append(tuple(toks[i : i + ngram]))

    if not phrases:
        return RepetitionMetrics(0, 0, 0.0, 0.0, 0.0)

    c = Counter(phrases)
    unique = len(c)
    repeated = sum(1 for _, v in c.items() if v >= 2)
    rep = repeated / max(unique, 1)
    diversity = unique / max(len(phrases), 1)
    # persistence rewards repeated independent mentions but saturates.
    persistence = float(math.tanh(rep * 3.0) * (1.0 - min(diversity, 1.0) * 0.3))
    return RepetitionMetrics(unique, repeated, rep, diversity, persistence)


def weighted_signal(base_score: float, repetition_score: float, cap: float = 2.0) -> float:
    """Boost/attenuate a base sentiment/signal by repetition evidence."""
    boost = 1.0 + min(max(repetition_score, -0.8), cap)
    return float(base_score * boost)

