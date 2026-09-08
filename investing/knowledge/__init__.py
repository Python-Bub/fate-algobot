"""
Deep encyclopedia chapters for each investing-book topic.

Each DeepChapter is book-length depth: philosophy, mechanics, formulas,
screens, traps, and FATE wiring notes. Lookup via get_chapter(topic_id).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class FormulaSpec:
    name: str
    latex: str
    meaning: str
    code_fn: str = ""  # investing.formulas.* or analytics.* path


@dataclass(frozen=True)
class DeepChapter:
    topic_id: str
    title: str
    family: str
    philosophy: str
    how_it_works: str
    formulas: tuple[FormulaSpec, ...] = ()
    screens: tuple[str, ...] = ()
    traps: tuple[str, ...] = ()
    catalysts: tuple[str, ...] = ()
    fate_hook: str = ""
    related: tuple[str, ...] = ()
    further_reading: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic_id": self.topic_id,
            "title": self.title,
            "family": self.family,
            "philosophy": self.philosophy,
            "how_it_works": self.how_it_works,
            "formulas": [
                {"name": f.name, "latex": f.latex, "meaning": f.meaning, "code_fn": f.code_fn}
                for f in self.formulas
            ],
            "screens": list(self.screens),
            "traps": list(self.traps),
            "catalysts": list(self.catalysts),
            "fate_hook": self.fate_hook,
            "related": list(self.related),
            "further_reading": list(self.further_reading),
        }

    def render_markdown(self) -> str:
        lines = [
            f"# {self.title}",
            "",
            f"*Family: `{self.family}` · id: `{self.topic_id}`*",
            "",
            "## Philosophy",
            self.philosophy.strip(),
            "",
            "## How it works",
            self.how_it_works.strip(),
            "",
        ]
        if self.formulas:
            lines.append("## Formulas")
            for f in self.formulas:
                lines.append(f"### {f.name}")
                lines.append(f"$${f.latex}$$")
                lines.append(f.meaning.strip())
                if f.code_fn:
                    lines.append(f"*Implemented:* `{f.code_fn}`")
                lines.append("")
        if self.screens:
            lines.append("## Screens / checklist")
            lines.extend(f"- {s}" for s in self.screens)
            lines.append("")
        if self.traps:
            lines.append("## Traps & failure modes")
            lines.extend(f"- {t}" for t in self.traps)
            lines.append("")
        if self.catalysts:
            lines.append("## Catalysts")
            lines.extend(f"- {c}" for c in self.catalysts)
            lines.append("")
        if self.fate_hook:
            lines.append("## In FATE_AlgoBot")
            lines.append(self.fate_hook.strip())
            lines.append("")
        if self.related:
            lines.append("## Related topics")
            lines.append(", ".join(f"`{r}`" for r in self.related))
            lines.append("")
        if self.further_reading:
            lines.append("## Further reading")
            lines.extend(f"- {r}" for r in self.further_reading)
            lines.append("")
        return "\n".join(lines)


_REGISTRY: dict[str, DeepChapter] = {}
_LOADED = False


def register(chapter: DeepChapter) -> DeepChapter:
    _REGISTRY[chapter.topic_id] = chapter
    return chapter


def get_chapter(topic_id: str) -> DeepChapter | None:
    _ensure_loaded()
    return _REGISTRY.get(topic_id.strip().lower())


def all_chapters() -> tuple[DeepChapter, ...]:
    _ensure_loaded()
    return tuple(_REGISTRY[k] for k in sorted(_REGISTRY))


def chapters_by_family(family: str) -> tuple[DeepChapter, ...]:
    return tuple(c for c in all_chapters() if c.family == family)


def coverage() -> dict[str, Any]:
    from investing.catalog import all_topics

    _ensure_loaded()
    ids = {t.id for t in all_topics()}
    deep = set(_REGISTRY)
    return {
        "deep_chapters": len(deep),
        "catalog_topics": len(ids),
        "missing": sorted(ids - deep),
        "extra": sorted(deep - ids),
        "pct": round(100.0 * len(deep & ids) / max(1, len(ids)), 1),
    }


def _ensure_loaded() -> None:
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    # Import family modules for side-effect registration
    from investing.knowledge import (  # noqa: F401
        value,
        growth,
        income,
        quant,
        trading,
        derivatives,
        short_macro,
        alt_passive,
        advanced_analysis,
        assets_sectors,
        sleeve_curriculum_map,
        lee_chin,
    )
