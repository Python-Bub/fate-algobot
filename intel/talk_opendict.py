"""Full open English dictionary → talk-brain corpus.

Uses Princeton WordNet via NLTK (~148k lemmas, ~117k synsets) — free for
research/use, downloadable by anyone. This is NOT Merriam-Webster (proprietary
HTML); it's the dictionary we can legally train on in full offline.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "talk_brain" / "opendict_corpus.txt"
META = ROOT / "data" / "talk_brain" / "opendict_fetch.json"


def _ensure_wordnet() -> Any:
    import nltk
    from nltk.corpus import wordnet as wn

    try:
        _ = wn.synsets("test")
    except LookupError:
        nltk.download("wordnet", quiet=True)
        nltk.download("omw-1.4", quiet=True)
    return wn


def iter_entries(limit: int | None = None) -> Iterable[tuple[str, str, str]]:
    """Yield (lemma, pos, definition)."""
    wn = _ensure_wordnet()
    pos_map = {"n": "noun", "v": "verb", "a": "adj", "s": "adj", "r": "adv"}
    seen: set[tuple[str, str]] = set()
    n = 0
    for syn in wn.all_synsets():
        definition = (syn.definition() or "").strip()
        if not definition:
            continue
        # ASCII for char LSTM
        definition = definition.encode("ascii", "ignore").decode("ascii").strip()
        if not definition:
            continue
        pos = pos_map.get(syn.pos(), syn.pos())
        for lem in syn.lemmas():
            word = lem.name().replace("_", " ").strip().lower()
            word = word.encode("ascii", "ignore").decode("ascii")
            if not word or len(word) > 40:
                continue
            key = (word, definition[:80])
            if key in seen:
                continue
            seen.add(key)
            yield word, pos, definition
            n += 1
            if limit is not None and n >= limit:
                return


def build_dialogue(limit: int | None = None, *, every_n: int = 1) -> tuple[str, int]:
    """Convert dictionary into you:/ai: lines the talk brain trains on."""
    blocks: list[str] = []
    count = 0
    for i, (word, pos, definition) in enumerate(iter_entries(limit=limit)):
        if every_n > 1 and (i % every_n) != 0:
            continue
        # compact formats — variety helps the tiny model
        if count % 3 == 0:
            blocks.append(f"you: what does {word} mean\nai: {word} ({pos}): {definition}\n")
        elif count % 3 == 1:
            blocks.append(f"you: define {word}\nai: {definition}\n")
        else:
            blocks.append(f"you: dictionary {word}\nai: {word} — {definition}\n")
        count += 1
    return "\n".join(blocks), count


def save_corpus(*, limit: int | None = None, every_n: int = 1) -> dict[str, Any]:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    text, n = build_dialogue(limit=limit, every_n=every_n)
    OUT.write_text(text, encoding="utf-8")
    meta = {
        "ts": time.time(),
        "source": "Princeton WordNet (NLTK)",
        "license_note": "WordNet freely available; not Merriam-Webster",
        "entries": n,
        "corpus_path": str(OUT),
        "corpus_chars": len(text),
        "limit": limit,
        "every_n": every_n,
    }
    META.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def define_word(word: str, *, limit: int = 3) -> list[str]:
    """Runtime WordNet definitions (open data) — used for FAQ, not MW scrape."""
    w = (word or "").strip().lower().replace(" ", "_")
    if len(w) < 2:
        return []
    try:
        wn = _ensure_wordnet()
        out: list[str] = []
        for syn in wn.synsets(w)[:limit]:
            d = (syn.definition() or "").strip()
            if d:
                out.append(d.encode("ascii", "ignore").decode("ascii") or d)
        return out
    except Exception:
        return []


def ingest_and_train(
    *,
    steps: int | None = None,
    limit: int | None = None,
    every_n: int = 1,
) -> dict[str, Any]:
    """Build full open dictionary corpus and retrain talk brain."""
    # Force dictionary focus so opendict pairs are not filtered out of the mix.
    os.environ["TALK_FOCUS"] = "dict"
    os.environ["TALK_INCLUDE_DICT"] = "true"
    os.environ.setdefault("TALK_DICT_WEIGHT", os.getenv("TALK_DICT_WEIGHT", "8000"))
    meta = save_corpus(limit=limit, every_n=every_n)
    from intel.talk_brain import train

    n_steps = steps or int(os.getenv("TALK_DICT_TRAIN_STEPS", "2500"))
    # denser corpus → longer seq helps a bit
    train_meta = train(
        steps=n_steps,
        seq=int(os.getenv("TALK_DICT_SEQ", "128")),
        batch=int(os.getenv("TALK_DICT_BATCH", "48")),
        extra_paths=[OUT],
    )
    return {"corpus": meta, "train": train_meta}
