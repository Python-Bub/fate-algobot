"""Distill the investing-guide taxonomy (292 topics + deep chapters) into talk Q&A.

Durable corpus: data/talk_brain/investing_guide_corpus.txt
Never shrinks coverage — every catalog topic and deep chapter yields multiple pairs.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "talk_brain" / "investing_guide_corpus.txt"
META = ROOT / "data" / "talk_brain" / "investing_guide_fetch.json"
QUEUE = ROOT / "data" / "talk_brain" / "investing_guide_question_bank.jsonl"


def _clip(s: str, n: int = 420) -> str:
    s = re.sub(r"\s+", " ", (s or "").strip())
    if len(s) <= n:
        return s
    cut = s[: n - 1].rsplit(" ", 1)[0]
    return (cut or s[: n - 1]) + "…"


def _pairs_for_topic(topic) -> list[tuple[str, str]]:
    title = topic.title
    tid = topic.id
    fam = topic.family
    status = topic.status
    summary = _clip(topic.summary or f"{title} is an investing topic in the FATE book taxonomy.")
    pairs: list[tuple[str, str]] = [
        (f"what is {title}", summary),
        (f"what is {tid}", summary),
        (f"explain {title}", summary),
        (f"tell me about {title}", summary),
        (
            f"{title} family",
            f"{title} sits in the `{fam}` family of the investing guide taxonomy.",
        ),
        (
            f"{title} status in FATE",
            f"{title} (`{tid}`) is wired as `{status}` "
            f"({'live rank/formula path' if status == 'live' else 'soft formula proxy' if status == 'soft' else 'knowledge encyclopedia — still covered'}).",
        ),
        (
            f"is {title} in the investing guide",
            f"Yes. `{tid}` is one of the 292 catalog topics from the investing guide.",
        ),
    ]
    if topic.formulas:
        fl = ", ".join(topic.formulas)
        pairs.append(
            (
                f"{title} formula",
                f"{title} formulas in FATE: {fl}.",
            )
        )
        pairs.append(
            (
                f"formula for {tid}",
                f"Use {fl} for {title}.",
            )
        )
    if topic.module:
        pairs.append(
            (
                f"where is {title} implemented",
                f"{title} hooks into `{topic.module}` (read-only for talk).",
            )
        )
    if topic.parent:
        pairs.append(
            (
                f"{title} parent topic",
                f"{title} is nested under `{topic.parent}` in the sector/asset tree.",
            )
        )
    return pairs


def _pairs_for_chapter(ch) -> list[tuple[str, str]]:
    title = ch.title
    tid = ch.topic_id
    pairs: list[tuple[str, str]] = [
        (
            f"philosophy of {title}",
            _clip(ch.philosophy, 480),
        ),
        (
            f"how does {title} work",
            _clip(ch.how_it_works, 480),
        ),
        (
            f"how {tid} works",
            _clip(ch.how_it_works, 480),
        ),
    ]
    if ch.fate_hook:
        pairs.append((f"{title} in FATE", _clip(ch.fate_hook, 420)))
        pairs.append((f"{tid} fate hook", _clip(ch.fate_hook, 420)))
    for f in ch.formulas or ():
        pairs.append(
            (
                f"what is the {f.name} formula",
                _clip(f"{f.name}: {f.latex}. {f.meaning}", 480),
            )
        )
        pairs.append(
            (
                f"{title} {f.name}",
                _clip(f"{f.name} ({f.latex}): {f.meaning}", 480),
            )
        )
        if f.code_fn:
            pairs.append(
                (
                    f"code for {f.name}",
                    f"{f.name} is implemented at `{f.code_fn}`.",
                )
            )
    for s in (ch.screens or ())[:6]:
        pairs.append((f"{title} screen", _clip(str(s), 360)))
        pairs.append((f"{tid} checklist", _clip(str(s), 360)))
    for t in (ch.traps or ())[:5]:
        pairs.append((f"{title} trap", _clip(str(t), 360)))
        pairs.append((f"{title} failure mode", _clip(str(t), 360)))
    for c in (ch.catalysts or ())[:4]:
        pairs.append((f"{title} catalyst", _clip(str(c), 360)))
    if ch.related:
        rel = ", ".join(f"`{r}`" for r in ch.related[:8])
        pairs.append((f"topics related to {title}", f"Related: {rel}."))
    return pairs


def _guide_meta_pairs() -> list[tuple[str, str]]:
    return [
        (
            "what is the investing guide",
            "The FATE investing guide is the full book taxonomy (~292 topics) covering "
            "strategies, assets, sectors, and analysis — with deep chapters and formulas.",
        ),
        (
            "how many investing topics",
            "The catalog has 292 topics: strategies, asset classes, sectors, and analysis methods.",
        ),
        (
            "292 topics",
            "Yes — 292 investing-guide topics are mapped into the bot (live, soft, or knowledge).",
        ),
        (
            "math first investing",
            "Math-first means sleeve weights and formula scores lead rank; encyclopedia topics stay covered even when not live-traded.",
        ),
        (
            "sleeve weights",
            "Sleeve weights allocate book boost across value, growth, income, quant, technical, and related families — never drop a sleeve to finish faster.",
        ),
        (
            "where is the investing guide file",
            "Canonical text: data/books/investing_guide_full.md; chapter index: data/books/chapters/INDEX.md.",
        ),
    ]


def build_investing_guide_pairs() -> list[tuple[str, str]]:
    from investing.catalog import ALL_TOPICS
    from investing.knowledge import all_chapters

    pairs: list[tuple[str, str]] = list(_guide_meta_pairs())
    seen_ids: set[str] = set()
    for topic in ALL_TOPICS:
        pairs.extend(_pairs_for_topic(topic))
        seen_ids.add(topic.id)
    for ch in all_chapters():
        pairs.extend(_pairs_for_chapter(ch))
        if ch.topic_id not in seen_ids:
            # Extra coverage if chapter exists without catalog row
            pairs.append(
                (
                    f"what is {ch.title}",
                    _clip(ch.philosophy or ch.how_it_works, 420),
                )
            )
    # Deduplicate exact (user, answer) while preserving order
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for u, a in pairs:
        key = (u.strip().lower(), a.strip())
        if not u.strip() or not a.strip() or key in seen:
            continue
        seen.add(key)
        out.append((u.strip(), a.strip()))
    return out


def save_investing_guide_corpus(*, path: Path | None = None) -> dict:
    """Write full Q&A bank + jsonl question bank. Always regenerates completely."""
    dest = path or OUT
    dest.parent.mkdir(parents=True, exist_ok=True)
    pairs = build_investing_guide_pairs()
    text = "\n".join(f"you: {u}\nai: {a}\n" for u, a in pairs)
    dest.write_text(text, encoding="utf-8")
    with QUEUE.open("w", encoding="utf-8") as fh:
        for i, (u, a) in enumerate(pairs):
            fh.write(
                json.dumps(
                    {
                        "i": i,
                        "q": u,
                        "a": a,
                        "done": True,
                        "source": "investing_guide",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    meta = {
        "path": str(dest),
        "queue_path": str(QUEUE),
        "pairs": len(pairs),
        "chars": len(text),
        "topics": 292,
        "mode": "full_guide_distill",
        "complete": True,
        "remaining": 0,
    }
    try:
        from investing.catalog import topic_count
        from investing.knowledge import coverage

        meta["catalog"] = topic_count()
        meta["deep_coverage"] = coverage()
    except Exception as e:
        meta["coverage_error"] = str(e)[:120]
    META.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(
        f"[talk-investing-guide] wrote {meta['pairs']:,} pairs → {dest} "
        f"(remaining={meta['remaining']})",
        flush=True,
    )
    return meta


def corpus_path() -> Path:
    return OUT


def ensure_corpus() -> Path:
    if not OUT.is_file() or OUT.stat().st_size < 10_000:
        save_investing_guide_corpus()
    return OUT


def status() -> dict:
    if META.is_file():
        try:
            return json.loads(META.read_text(encoding="utf-8"))
        except Exception:
            pass
    pairs = 0
    if OUT.is_file():
        pairs = OUT.read_text(encoding="utf-8", errors="replace").count("you:")
    return {
        "pairs": pairs,
        "complete": pairs > 0,
        "remaining": 0 if pairs > 0 else None,
        "path": str(OUT),
    }


if __name__ == "__main__":
    os.chdir(ROOT)
    print(json.dumps(save_investing_guide_corpus(), indent=2))
