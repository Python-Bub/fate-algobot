#!/usr/bin/env python3
"""Ingest investing book markdown into structured strategy knowledge.

  ./venv/bin/python tools/ingest_investing_book.py
  ./venv/bin/python tools/ingest_investing_book.py data/books/investing_guide_part2.md
  ./venv/bin/python tools/ingest_investing_book.py --text-file /tmp/paste.md

Follow-up pastes: drop next part under data/books/ and re-run.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default=str(ROOT / "data" / "books" / "investing_guide_part1.md"))
    ap.add_argument("--text-file", default="", help="Raw paste file to save as next part then ingest")
    args = ap.parse_args()

    from intel.book_ingest import ingest_markdown_file, save_book_text

    path = Path(args.path)
    if args.text_file:
        raw = Path(args.text_file).read_text(encoding="utf-8", errors="replace")
        path = save_book_text(raw)
        print(f"saved {path}")

    doc = ingest_markdown_file(path)
    print(json.dumps({"families": doc.get("families"), "n_strategies": len(doc.get("strategies") or []), "path": str(path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
