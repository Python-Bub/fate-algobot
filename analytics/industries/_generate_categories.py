#!/usr/bin/env python3
"""Generate 50 user-facing category modules (biotechnology.py, marine_transportation.py, ...)."""

from __future__ import annotations

from pathlib import Path

from analytics.industries._generate_industry_handlers import MASTER
from analytics.industries.categories._registry import USER_CATEGORIES

ROOT = Path(__file__).resolve().parents[2]
CAT_DIR = ROOT / "analytics" / "industries" / "categories"
MASTER_BY_ID = {s["id"]: s for s in MASTER}


def _cls(slug: str) -> str:
    return "".join(p.capitalize() for p in slug.split("_")) + "Category"


def _category_source(num: int, slug: str, display: str, iid: str, spec: dict) -> str:
    cls = _cls(slug)
    leaders = ", ".join(repr(x) for x in spec["leaders"])
    bull = spec["bull"][:5]
    bull_lines = "\n".join(f"    {p!r}," for p in bull)
    comm = ", ".join(repr(x) for x in spec["commodities"][:4])
    notes = spec["notes"].replace('"', "'")

    return f'''\
"""
{num}. {display}

Internal id: {iid}
ETF proxy: {spec["etf"]} | Mode: {spec["mode"]}
Notes: {notes}

Unified category module — handler, specialized pipeline, enhancement layer, anchor.
Import this file directly: from analytics.industries.categories.{slug} import CATEGORY
"""

from __future__ import annotations

from typing import Any

from analytics.industries.base import IndustryContext
from analytics.industries.categories._registry import category_slug_for_industry
from analytics.industries.pipeline_models import IndustryPipelineResult


class {cls}:
    CATEGORY_NUMBER = {num}
    CATEGORY_SLUG = {slug!r}
    DISPLAY_NAME = {display!r}
    INDUSTRY_ID = {iid!r}
    ETF_PROXY = {spec["etf"]!r}
    COMOVEMENT_MODE = {spec["mode"]!r}

    LEADER_TICKERS = (
        {leaders}
    )

    NEWS_BULL_PHRASES = (
{bull_lines}
    )

    COMMODITY_KEYS = ({comm})

    @property
    def handler(self):
        from analytics.industries.registry import get_handler
        return get_handler(self.INDUSTRY_ID)

    @property
    def specialized(self):
        from analytics.industries.specialized import get_specialized
        return get_specialized(self.INDUSTRY_ID)

    @property
    def enhancement(self):
        from analytics.industries.enhancements import get_enhancement
        return get_enhancement(self.INDUSTRY_ID)

    @property
    def anchor(self):
        from analytics.industries.anchors import get_anchor
        return get_anchor(self.INDUSTRY_ID)

    @property
    def spec(self):
        from analytics.industries.categories.specs import get_spec
        return get_spec(self.CATEGORY_SLUG)

    def evaluate_buy_decision(
        self,
        symbol: str,
        row: dict | None = None,
        *,
        macro: dict | None = None,
        headlines: list[str] | None = None,
    ):
        from analytics.industries.category_decision import evaluate_category_decision
        rf = dict(row or {{}})
        rf.setdefault("industry_id", self.INDUSTRY_ID)
        return evaluate_category_decision(symbol, rf, macro, headlines)

    def build_context(
        self,
        symbol: str,
        *,
        macro: dict | None = None,
        news_headlines: list[str] | None = None,
        row_features: dict | None = None,
    ) -> IndustryContext:
        from analytics.industries.engine import build_context
        return build_context(
            symbol,
            macro_bundle=macro,
            news_headlines=news_headlines,
            row_features=row_features or {{}},
        )

    def run_pipeline(
        self,
        symbol: str,
        row: dict | None = None,
        *,
        macro_bundle: dict | None = None,
        news_headlines: list[str] | None = None,
    ) -> dict[str, Any]:
        from analytics.industries.pipeline import run_industry_pipeline
        return run_industry_pipeline(symbol, row, macro_bundle=macro_bundle, news_headlines=news_headlines)

    def enhance_row(self, row: dict[str, Any]) -> dict[str, Any]:
        from analytics.industries.project_wiring import wire_paper_sim_row
        out = wire_paper_sim_row(row)
        out["category"] = {{
            "number": self.CATEGORY_NUMBER,
            "slug": self.CATEGORY_SLUG,
            "name": self.DISPLAY_NAME,
            "industry_id": self.INDUSTRY_ID,
        }}
        return self.anchor.enhance_row(out)

    def enhance_score(self, symbol: str, score: float, p_up: float, row: dict | None = None):
        s, p = float(score), float(p_up)
        ctx = self.build_context(symbol, row_features=row or {{}})
        base = IndustryPipelineResult()
        part = self.specialized.run(ctx, self.handler)
        part = self.enhancement.enhance(part, ctx, self.handler)
        s += float(part.score_delta) * 0.11
        p = min(1.0, p + float(part.p_up_delta))
        return self.anchor.enhance_score(symbol, s, p, row=row)

    def feature_weights(self, symbol: str) -> dict[str, float]:
        ctx = self.build_context(symbol)
        res = IndustryPipelineResult()
        self.enhancement.enhance(res, ctx, self.handler)
        return dict(res.feature_weights)

    def high_level_test(self) -> dict[str, Any]:
        rep = self.enhancement.high_level_test(self.handler)
        rep["category_slug"] = self.CATEGORY_SLUG
        rep["category_number"] = self.CATEGORY_NUMBER
        rep["display_name"] = self.DISPLAY_NAME
        return rep

    def historical_smoke(self) -> dict[str, Any]:
        rep = self.anchor.historical_smoke()
        rep["category_slug"] = self.CATEGORY_SLUG
        rep["category_number"] = self.CATEGORY_NUMBER
        rep["display_name"] = self.DISPLAY_NAME
        return rep


CATEGORY = {cls}()
INDUSTRY_ID = CATEGORY.INDUSTRY_ID
CATEGORY_SLUG = CATEGORY.CATEGORY_SLUG


def get_category():
    return CATEGORY


def slug_for_symbol(symbol: str) -> str:
    from analytics.industries.integration import get_industry_profile
    prof = get_industry_profile(symbol.strip().upper())
    return category_slug_for_industry(prof.get("primary_industry_id") or "unclassified")
'''


def generate_all() -> int:
    CAT_DIR.mkdir(parents=True, exist_ok=True)
    init_lines = ['"""50 user-facing industry category modules."""\n']
    init_lines.append("from analytics.industries.categories._registry import (\n")
    init_lines.append("    INDUSTRY_TO_SLUG,\n    SLUG_TO_INDUSTRY,\n    USER_CATEGORIES,\n")
    init_lines.append("    category_slug_for_industry,\n    resolve_industry_id,\n)\n")

    count = 0
    imports = []
    all_map = []
    for num, slug, display, iid in USER_CATEGORIES:
        spec = MASTER_BY_ID.get(iid)
        if not spec:
            continue
        (CAT_DIR / f"{slug}.py").write_text(_category_source(num, slug, display, iid, spec), encoding="utf-8")
        cls = _cls(slug)
        imports.append(f"from analytics.industries.categories.{slug} import CATEGORY as _c_{slug}")
        all_map.append(f'    "{slug}": _c_{slug},')
        all_map.append(f'    "{iid}": _c_{slug},  # alias')
        count += 1

    init_lines.extend(imports)
    init_lines.append("\nALL_CATEGORIES = {\n")
    init_lines.extend(all_map)
    init_lines.append("}\n")
    init_lines.append(
        "\n\n"
        "def get_category(key: str):\n"
        '    """Lookup by slug (marine_transportation) or internal id (marine_shipping)."""\n'
        "    from analytics.industries.categories._registry import resolve_industry_id\n"
        "    k = str(key or '').strip().lower()\n"
        "    if k in ALL_CATEGORIES:\n"
        "        return ALL_CATEGORIES[k]\n"
        "    iid = resolve_industry_id(k)\n"
        "    from analytics.industries.categories._unclassified import CATEGORY as _unclassified\n"
        "    return ALL_CATEGORIES.get(iid) or _unclassified\n"
        "\n\n"
        "def list_category_slugs() -> list[str]:\n"
        "    from analytics.industries.categories._registry import USER_CATEGORIES\n"
        "    return [slug for _, slug, _, _ in USER_CATEGORIES]\n"
    )
    (CAT_DIR / "__init__.py").write_text("\n".join(init_lines), encoding="utf-8")
    return count


if __name__ == "__main__":
    n = generate_all()
    print(f"Generated {n} category modules in {CAT_DIR}")
