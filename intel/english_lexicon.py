"""Open English lexicon helpers — WordNet (not Merriam-Webster).

Used to expand ticker/news search queries and light polarity without burning
NewsAPI/Polygon quota. No copyrighted commercial dictionary dumps.
"""

from __future__ import annotations

import json
import os
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

_WORD = re.compile(r"[A-Za-z][A-Za-z\-']{1,32}")

ROOT = Path(__file__).resolve().parents[1]
_EXPANDED_PATH = ROOT / "data" / "intel" / "english_lexicon_expanded.json"

# Compact finance lexicon (open / original) — complements WordNet.
_POS_SEED = frozenset(
    {
        "surge", "rally", "beat", "upgrade", "growth", "bullish", "outperform",
        "record", "profit", "gain", "soar", "jump", "strong", "optimism",
        "breakthrough", "accelerate", "expand", "raise", "buy", "overweight",
        "boom", "rebound", "tailwind", "momentum", "exceed", "thrive",
    }
)
_NEG_SEED = frozenset(
    {
        "plunge", "crash", "miss", "downgrade", "lawsuit", "fraud", "bearish",
        "layoff", "probe", "investigation", "loss", "weak", "cut", "slash",
        "warning", "risk", "sell", "underweight", "decline", "drop", "fear",
        "slump", "tumble", "scandal", "bankrupt", "dilution", "overhang",
    }
)
_POS = _POS_SEED
_NEG = _NEG_SEED


def _b(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in ("1", "true", "yes", "on")


@lru_cache(maxsize=1)
def _wordnet_ready() -> bool:
    if not _b("USE_ENGLISH_LEXICON", True):
        return False
    try:
        from nltk.corpus import wordnet as wn  # noqa: F401

        # Touch once to ensure corpora present
        _ = wn.synsets("profit")
        return True
    except Exception:
        try:
            import nltk

            nltk.download("wordnet", quiet=True)
            nltk.download("omw-1.4", quiet=True)
            from nltk.corpus import wordnet as wn

            _ = wn.synsets("profit")
            return True
        except Exception:
            return False


def tokenize(text: str) -> list[str]:
    return [m.group(0).lower() for m in _WORD.finditer(text or "")]


def _synonym_lemmas(word: str, *, limit: int = 12) -> set[str]:
    if not _wordnet_ready():
        return set()
    try:
        from nltk.corpus import wordnet as wn

        out: set[str] = set()
        for syn in wn.synsets(word)[:6]:
            for name in syn.lemma_names():
                n = name.replace("_", " ").lower()
                if " " in n or len(n) < 3 or len(n) > 24:
                    continue
                out.add(n)
                if len(out) >= limit:
                    return out
        return out
    except Exception:
        return set()


def expand_and_save_lexicon(path: Path | None = None) -> dict[str, Any]:
    """Grow finance POS/NEG via WordNet synonyms; persist for news polarity."""
    pos: set[str] = set(_POS_SEED)
    neg: set[str] = set(_NEG_SEED)
    for seed in list(_POS_SEED):
        pos |= _synonym_lemmas(seed)
    for seed in list(_NEG_SEED):
        neg |= _synonym_lemmas(seed)
    # Drop ambiguous overlaps (e.g. "cut" vs "raise" neighbors)
    overlap = pos & neg
    pos -= overlap
    neg -= overlap
    out_path = path or _EXPANDED_PATH
    out_path.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "ts": time.time(),
        "source": "Princeton WordNet via NLTK + open finance seeds",
        "license_note": "WordNet freely available; not Merriam-Webster full dictionary",
        "n_pos": len(pos),
        "n_neg": len(neg),
        "n_overlap_dropped": len(overlap),
        "pos": sorted(pos),
        "neg": sorted(neg),
    }
    out_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    _load_expanded.cache_clear()
    return {k: meta[k] for k in ("ts", "source", "n_pos", "n_neg", "n_overlap_dropped")}


@lru_cache(maxsize=1)
def _load_expanded() -> tuple[frozenset[str], frozenset[str]]:
    if not _EXPANDED_PATH.is_file():
        return _POS_SEED, _NEG_SEED
    try:
        raw = json.loads(_EXPANDED_PATH.read_text(encoding="utf-8"))
        pos = frozenset(str(x).lower() for x in (raw.get("pos") or []) if str(x).isalpha())
        neg = frozenset(str(x).lower() for x in (raw.get("neg") or []) if str(x).isalpha())
        if not pos or not neg:
            return _POS_SEED, _NEG_SEED
        return pos | _POS_SEED, neg | _NEG_SEED
    except Exception:
        return _POS_SEED, _NEG_SEED


def lexicon_polarity(text: str) -> float:
    """Simple [-1, 1] polarity from open finance lexicon (+ WordNet-expanded sets)."""
    toks = tokenize(text)
    if not toks:
        return 0.0
    pos_set, neg_set = _load_expanded()
    pos = sum(1 for t in toks if t in pos_set)
    neg = sum(1 for t in toks if t in neg_set)
    if pos == 0 and neg == 0:
        return 0.0
    return float(max(-1.0, min(1.0, (pos - neg) / max(3.0, pos + neg))))


def synonyms(word: str, *, limit: int = 6) -> list[str]:
    """WordNet synonyms for query expansion (open data)."""
    w = (word or "").strip().lower()
    if len(w) < 3 or not _wordnet_ready():
        return []
    try:
        from nltk.corpus import wordnet as wn

        out: list[str] = []
        seen = {w}
        for syn in wn.synsets(w)[:8]:
            for name in syn.lemma_names():
                n = name.replace("_", " ").lower()
                if n in seen or " " in n or len(n) < 3:
                    continue
                seen.add(n)
                out.append(n)
                if len(out) >= limit:
                    return out
        return out
    except Exception:
        return []


def expand_news_query(symbol: str, company_hint: str = "") -> list[str]:
    """Build several Google-News-friendly queries without paid NewsAPI.

    Returns distinct query strings (caller should try a few, not all).
    """
    sym = symbol.strip().upper()
    queries = [sym, f"{sym} stock", f"{sym} earnings"]
    hint = (company_hint or "").strip()
    if hint and hint.upper() != sym:
        queries.append(hint)
        queries.append(f"{hint} stock")
        # Expand one key noun from company name
        for tok in tokenize(hint)[:3]:
            if tok in {"inc", "corp", "ltd", "plc", "the", "and", "co"}:
                continue
            for syn in synonyms(tok, limit=2):
                queries.append(f"{syn} {sym}")
    # Dedupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        k = q.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(q)
    return out[: int(os.getenv("ENGLISH_LEXICON_MAX_QUERIES", "5"))]


def enrich_headline_score(text: str, base: float) -> float:
    """Soft-blend lexicon polarity into an existing sentiment score (LEA when on)."""
    if not _b("USE_ENGLISH_LEXICON", True):
        return float(base)
    w = float(os.getenv("ENGLISH_LEXICON_BLEND", "0.15"))
    # Map polarity [-1,1] → pseudo-prob for logit blend
    pol = lexicon_polarity(text)
    p_lex = 0.5 + 0.5 * float(pol)
    try:
        from analytics.vector_math import lea_enabled, logit_pair_blend

        if lea_enabled():
            # base may already be in [-1,1] or [0,1]
            b = float(base)
            p0 = b if 0.0 <= b <= 1.0 else 0.5 + 0.5 * max(-1.0, min(1.0, b))
            p1 = logit_pair_blend(p0, p_lex, w)
            if 0.0 <= b <= 1.0:
                return float(p1)
            return float(2.0 * p1 - 1.0)
    except Exception:
        pass
    return float((1.0 - w) * float(base) + w * pol)