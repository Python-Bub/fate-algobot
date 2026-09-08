#!/usr/bin/env python3
"""Ingest Jim Cramer transcript / mention chunks into data/replay/transcripts/CRAMER.jsonl.

Usage examples:

    # From a local transcript file (one episode):
    ./venv/bin/python ingest_cramer.py --file path/to/transcript.txt --date 2025-09-12

    # From stdin (paste Mad Money transcript, then Ctrl-D):
    ./venv/bin/python ingest_cramer.py --date 2025-09-12

    # From a YouTube video URL (uses youtube-transcript-api if installed):
    ./venv/bin/python ingest_cramer.py --youtube https://youtu.be/VIDEOID --date 2025-09-12

After ingesting, `intel/cramer_picks.score_symbol_from_cramer(SYM)` returns a per-ticker
score the live + paper-sim rankers fold into the composite score (`RANK_W_CRAMER`).
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

from dotenv import load_dotenv

load_dotenv()

from intel.cramer_picks import ingest_text_lines, score_symbol_from_cramer  # noqa: E402


def _from_youtube(url: str) -> list[str]:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore
    except ImportError:
        print(
            "youtube-transcript-api not installed. Install with:\n"
            "    ./venv/bin/pip install youtube-transcript-api",
            file=sys.stderr,
        )
        sys.exit(2)
    vid = url.split("v=")[-1].split("&")[0].split("/")[-1].split("?")[0]
    items = YouTubeTranscriptApi.get_transcript(vid)
    return [it["text"].strip() for it in items if it.get("text")]


def _chunk(text: str, max_chars: int = 1200) -> list[str]:
    s = text.strip()
    if not s:
        return []
    out: list[str] = []
    while s:
        out.append(s[:max_chars].strip())
        s = s[max_chars:]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="Path to a plain-text transcript file (one episode).")
    ap.add_argument("--youtube", help="YouTube URL to fetch transcript from.")
    ap.add_argument("--date", default=date.today().isoformat(), help="YYYY-MM-DD for recency weighting.")
    ap.add_argument("--query", help="If set, print the extracted score for this ticker after ingest.")
    args = ap.parse_args()

    lines: list[str]
    if args.youtube:
        lines = _from_youtube(args.youtube)
    elif args.file:
        with open(args.file, encoding="utf-8") as f:
            lines = _chunk(f.read())
    else:
        print("Paste transcript text, then EOF (Ctrl-D on macOS):", file=sys.stderr)
        lines = _chunk(sys.stdin.read())

    if not lines:
        print("No transcript content found.", file=sys.stderr)
        sys.exit(1)

    n = ingest_text_lines(lines, ts=args.date, append=True)
    print(f"Wrote {n} lines for ts={args.date}.")
    if args.query:
        info = score_symbol_from_cramer(args.query)
        print(f"{args.query}: {info}")


if __name__ == "__main__":
    main()
