#!/usr/bin/env python3
"""Ingest Jim Cramer Investing Club morning email into trading intel."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def main() -> int:
    from intel.morning_club_intel import auto_ingest, ingest_morning_email, load_latest

    ap = argparse.ArgumentParser(description="Ingest Cramer Top 10 Morning Thoughts email")
    ap.add_argument("--file", "-f", help="Path to .txt/.eml email body")
    ap.add_argument("--stdin", action="store_true", help="Read email body from stdin")
    ap.add_argument("--auto", action="store_true", help="IMAP + inbox folder auto-ingest")
    ap.add_argument("--show", action="store_true", help="Print latest parsed intel JSON")
    args = ap.parse_args()

    if args.show:
        import json

        print(json.dumps(load_latest(), indent=2))
        return 0

    if args.auto:
        doc = auto_ingest()
        if not doc:
            print("No new morning club email found")
            return 1
        print(f"OK tone={doc.get('market_tone')} tickers={len(doc.get('tickers') or {})}")
        return 0

    text = ""
    if args.stdin:
        text = sys.stdin.read()
    elif args.file:
        text = Path(args.file).read_text(encoding="utf-8", errors="replace")
    else:
        ap.print_help()
        return 2

    doc = ingest_morning_email(text, source=args.file or "stdin")
    if not doc:
        print("Empty input")
        return 1
    print(f"OK tone={doc.get('market_tone')} tickers={len(doc.get('tickers') or {})} parser={doc.get('parser')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
