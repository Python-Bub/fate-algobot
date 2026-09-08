#!/usr/bin/env python3
"""Investing-book encyclopedia + multi-family screen.

  ./run_all.sh investing-book                 # topic counts
  ./run_all.sh investing-book --family growth
  ./run_all.sh investing-book --screen AAPL KO
  ./run_all.sh investing-book --search moat
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser(description="Investing book catalog + screens")
    ap.add_argument("--deep", nargs="*", default=None, help="Render deep chapter(s) by topic id (or --deep alone for coverage)")
    ap.add_argument("--beginner", action="store_true", help="Render beginner investing guide curriculum")
    ap.add_argument("--beginner-deep", action="store_true", help="Beginner guide + linked deep chapters")
    ap.add_argument("--family", default="", help="Filter topics by family")
    ap.add_argument("--status", default="", choices=["", "live", "soft", "knowledge"])
    ap.add_argument("--search", default="", help="Substring search in title/summary")
    ap.add_argument("--screen", nargs="*", default=[], help="Tickers to run book_rank_boost")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--limit", type=int, default=40)
    args = ap.parse_args()

    from investing.catalog import all_topics, by_family, by_status, topic_count

    if args.beginner or args.beginner_deep:
        from investing.beginner_guide import coverage_check, render_markdown

        if args.json:
            print(json.dumps({"coverage": coverage_check()}, indent=2))
        else:
            print(render_markdown(deep=bool(args.beginner_deep)))
            cov = coverage_check()
            print(f"\n# Linked chapters: {cov['linked']}  missing={cov['missing'] or 'none'}")
        return 0

    # Deep encyclopedia path
    if args.deep is not None:
        from investing.knowledge import coverage, get_chapter, chapters_by_family

        cov = coverage()
        if not args.deep:
            if args.json:
                print(json.dumps(cov, indent=2))
            else:
                print(
                    f"Deep chapters: {cov['deep_chapters']}/{cov['catalog_topics']} "
                    f"({cov['pct']}% coverage)"
                )
                if cov["missing"]:
                    print("Missing:", ", ".join(cov["missing"][:40]))
            return 0
        for tid in args.deep:
            ch = get_chapter(tid)
            if not ch:
                print(f"No deep chapter for '{tid}'", file=sys.stderr)
                continue
            if args.json:
                print(json.dumps(ch.to_dict(), indent=2))
            else:
                print(ch.render_markdown())
                print("\n" + ("=" * 72) + "\n")
        return 0

    counts = topic_count()
    topics = list(all_topics())
    if args.family:
        topics = list(by_family(args.family))
    if args.status:
        topics = [t for t in topics if t.status == args.status]
    if args.search:
        q = args.search.lower()
        topics = [
            t
            for t in topics
            if q in t.title.lower() or q in t.summary.lower() or q in t.id.lower()
        ]

    if args.screen:
        from investing.integrate import book_rank_boost

        rows = []
        for sym in args.screen:
            boost, meta = book_rank_boost(sym)
            rows.append({"symbol": sym.upper(), "boost": round(boost, 4), "meta": meta})
        if args.json:
            print(json.dumps({"counts": counts, "screens": rows}, indent=2, default=str))
        else:
            print(f"catalog topics={counts['total']}  live={counts['by_status'].get('live',0)}  "
                  f"soft={counts['by_status'].get('soft',0)}  knowledge={counts['by_status'].get('knowledge',0)}")
            for r in rows:
                fam = (r["meta"] or {}).get("families") or {}
                print(f"{r['symbol']:8} boost={r['boost']:+.4f}  families={list(fam.keys())}")
                for k, v in fam.items():
                    print(f"           {k}: {v}")
        return 0

    shown = topics[: max(1, args.limit)]
    if args.json:
        print(
            json.dumps(
                {
                    "counts": counts,
                    "shown": [
                        {
                            "id": t.id,
                            "title": t.title,
                            "family": t.family,
                            "parent": t.parent,
                            "status": t.status,
                            "formulas": list(t.formulas),
                            "summary": t.summary,
                        }
                        for t in shown
                    ],
                },
                indent=2,
            )
        )
        return 0

    print(
        f"Investing book catalog: {counts['total']} topics  "
        f"(live={counts['by_status'].get('live', 0)} "
        f"soft={counts['by_status'].get('soft', 0)} "
        f"knowledge={counts['by_status'].get('knowledge', 0)})"
    )
    print("Families:", ", ".join(f"{k}:{v}" for k, v in sorted(counts["by_family"].items())))
    print("-" * 72)
    for t in shown:
        parent = f" / {t.parent}" if t.parent else ""
        formulas = f"  formulas={','.join(t.formulas)}" if t.formulas else ""
        print(f"[{t.status:10}] {t.family:12} {t.title}{parent}{formulas}")
        print(f"             {t.summary[:140]}{'…' if len(t.summary) > 140 else ''}")
    if len(topics) > len(shown):
        print(f"… {len(topics) - len(shown)} more (raise --limit)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
