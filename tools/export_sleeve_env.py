#!/usr/bin/env python3
"""Export per-sleeve env files + regenerate PICK_WEIGHTAGE_BY_SLEEVE.md.

  ./venv/bin/python tools/export_sleeve_env.py
  ./venv/bin/python tools/export_sleeve_env.py --write-md
  ./venv/bin/python tools/export_sleeve_env.py --sleeve hft
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OPS = ROOT / "data" / "ops"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sleeve", default="", help="Optional single sleeve")
    ap.add_argument("--write-md", action="store_true", help="Regenerate PICK_WEIGHTAGE_BY_SLEEVE.md")
    ap.add_argument("--force-env", action="store_true", help="Overwrite raw env values when applying")
    args = ap.parse_args()

    from analytics.sleeve_weights import (
        SLEEVES,
        _ENV_RAW,
        assert_tables_valid,
        markdown_table,
        no_cross_bleed,
        pct_sum,
    )

    assert_tables_valid()
    bleed = no_cross_bleed()
    OPS.mkdir(parents=True, exist_ok=True)

    targets = [args.sleeve] if args.sleeve else list(SLEEVES)
    for s in targets:
        if s not in SLEEVES:
            print(f"unknown sleeve {s}", file=sys.stderr)
            return 2
        raw = _ENV_RAW.get(s, {})  # type: ignore[arg-type]
        lines = [
            f"# Auto-exported sleeve={s} from analytics/sleeve_weights.py",
            f"# active_pct_sum={pct_sum(s):.0f}",
            f"FATE_SLEEVE={s}",
            "HF_W_LIQUIDITY_MM=0.0",
            "HF_LOCK_LIQUIDITY_MM_ZERO=true",
        ]
        # Index ETF / ETF disloc allowed when sleeve table has weight
        from analytics.sleeve_weights import pct_table

        t = pct_table(s)
        if float(t.get("index_etf", 0) + t.get("hf_etf_disloc", 0)) > 0:
            lines.append("HF_LOCK_ETF_DISLOC_ZERO=false")
            lines.append("FORTRESS_BAN_INDEX_BUYS=false")
            if s == "hft":
                lines.append("HFT_BAN_INDEX_BUYS=false")
        else:
            lines.append("HF_W_ETF_DISLOC=0.0")
            lines.append("HF_LOCK_ETF_DISLOC_ZERO=true")
        for _factor, (env_key, raw_val) in raw.items():
            lines.append(f"{env_key}={raw_val}")
        out = OPS / f"{s}_sleeve.env"
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"wrote {out}")

    if args.write_md:
        parts = [
            "# Pick weightage by sleeve (100% each)\n",
            "**As of 2026-07-30 Phase 5 lock-in.** Source: `analytics/sleeve_weights.py`. "
            "Master plan: **5 phases total** (`SLEEVE_SCORING_MASTER_PLAN.md`).\n",
            "Index ETF **buys** = 0% on every active sleeve. HFT never carries Cramer/macro/value/book/passive.\n",
            "\n## Cross-bleed proof\n",
            f"- `ok={bleed['ok']}` forbidden_overlap={bleed['forbidden_overlap']}\n",
            f"- HFT cramer%={bleed['hft_cramer']} · LT obi%={bleed['lt_obi']} · "
            f"index_etf={bleed.get('index_etf_allowed')}\n",
            "\n---\n",
        ]
        for s in SLEEVES:
            parts.append("\n" + markdown_table(s) + "\n")
        parts.append(
            """
---

## Env resolution
| Sleeve | How selected |
|--------|----------------|
| `hft` | OBI launch + `data/ops/hft_sleeve.env` (`HFT_W_*` only) |
| `day_trade` | `FATE_SLEEVE=day_trade` / `apply_sleeve_env` |
| `fortress` | `FATE_SLEEVE=fortress` |
| `weekly` | `HOLD_DAYS_DEFAULT=5` + `FATE_SLEEVE=weekly` |
| `longterm` | `HOLD_DAYS_DEFAULT=20` + `FATE_SLEEVE=longterm` |

Curriculum soft (weekly/LT only): `RANK_W_MACRO`, `RANK_W_INFLATION`, `RANK_W_RATE_CYCLE`, `RANK_W_BUY_HOLD`, `RANK_W_ALT_CONTEXT`.

Regenerate: `./venv/bin/python tools/export_sleeve_env.py --write-md`
"""
        )
        md = OPS / "PICK_WEIGHTAGE_BY_SLEEVE.md"
        md.write_text("".join(parts), encoding="utf-8")
        print(f"wrote {md}")

    print("bleed", bleed)
    return 0 if bleed["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
