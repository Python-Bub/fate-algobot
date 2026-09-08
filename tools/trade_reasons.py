#!/usr/bin/env python3
"""Show why recent trades fired — HFT, fortress journal, paper_sim picks."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _hft_events(limit: int, ticker: str | None) -> list[dict]:
    out: list[dict] = []
    logs = sorted((ROOT / "hft" / "logs").glob("hft-*.jsonl"))
    for path in reversed(logs):
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("event") not in ("obi_fire", "earn_fire", "earn_abort"):
                continue
            sym = str(ev.get("ticker", "")).upper()
            if ticker and sym != ticker.upper():
                continue
            ts = ev.get("ts")
            when = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat() if ts else "?"
            if ev["event"] == "obi_fire":
                why = (
                    f"OBI={ev.get('obi')} tape_burst={ev.get('burst')} "
                    f"conf={ev.get('conf')} notional=${ev.get('notional')}"
                )
            elif ev["event"] == "earn_fire":
                why = (
                    f"surprise={ev.get('surprisePct')}% "
                    f"rationale={ev.get('rationale', '?')} "
                    f"limit={ev.get('limitPx')} wire_ms={ev.get('wireMs')}"
                )
            else:
                why = f"aborted: {ev.get('reason', ev)}"
            out.append(
                {
                    "when": when,
                    "engine": "subsecond-hft",
                    "symbol": sym,
                    "side": ev.get("side", "?"),
                    "why": why,
                    "source": path.name,
                }
            )
            if len(out) >= limit:
                return out
    return out


def _journal_rows(limit: int, ticker: str | None) -> list[dict]:
    path = ROOT / "data" / "journal" / "trades.csv"
    if not path.is_file():
        return []
    rows: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for row in reversed(list(csv.DictReader(f))):
            sym = row.get("symbol", "").upper()
            if ticker and sym != ticker.upper():
                continue
            why = (
                f"model_p={row.get('model_p')} sentiment={row.get('sentiment')} "
                f"regime={row.get('regime')} vix={row.get('vix')} notes={row.get('notes')}"
            )
            rows.append(
                {
                    "when": row.get("ts", "?"),
                    "engine": row.get("notes") or "fortress",
                    "symbol": sym,
                    "side": row.get("side", "?"),
                    "why": why,
                    "source": "data/journal/trades.csv",
                }
            )
            if len(rows) >= limit:
                break
    return rows


def _paper_sim_picks(limit: int, ticker: str | None) -> list[dict]:
    rep_dir = ROOT / "reports"
    files = sorted(rep_dir.glob("paper_sim_*.json"))
    if not files:
        return []
    path = files[-1]
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    out: list[dict] = []
    for row in doc.get("rows") or []:
        act = row.get("action")
        if act not in ("BUY", "SHORT"):
            continue
        sym = str(row.get("ticker", "")).upper()
        if ticker and sym != ticker.upper():
            continue
        why = (
            f"action={act} score={row.get('score')} p_up={row.get('p_up')} "
            f"exec={row.get('execution_confidence')} asym={row.get('asym_action')} "
            f"({row.get('asym_rationale')}) gates={row.get('gate_detail')} "
            f"cramer_hc={row.get('cramer_high_conviction')} ur={row.get('ur_rationale', '')[:80]}"
        )
        out.append(
            {
                "when": doc.get("generated_at_utc", "?"),
                "engine": f"paper_sim/{doc.get('mode', '?')}",
                "symbol": sym,
                "side": "buy" if act == "BUY" else "short",
                "why": why,
                "source": path.name,
            }
        )
    out.sort(key=lambda r: r["when"], reverse=True)
    return out[:limit]


def _fortress_log(limit: int, ticker: str | None) -> list[dict]:
    out: list[dict] = []
    logs = sorted((ROOT / "logs").glob("intraday_*.log"))
    for path in reversed(logs):
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for line in reversed(lines):
            if "[FORTRESS]" not in line or " BUY " not in line and " DCA " not in line and " REBUY " not in line:
                if "[FORTRESS]" not in line or "exit" in line:
                    continue
            if " BUY " not in line and " DCA " not in line and " REBUY " not in line:
                continue
            # parse symbol after tag
            parts = line.split("[FORTRESS]", 1)[-1].strip()
            if ticker:
                if f" {ticker.upper()} " not in f" {parts} ":
                    continue
            out.append(
                {
                    "when": line[:19] if len(line) > 19 else "?",
                    "engine": "fortress_live",
                    "symbol": ticker or parts.split()[1] if len(parts.split()) > 1 else "?",
                    "side": "buy",
                    "why": parts,
                    "source": path.name,
                }
            )
            if len(out) >= limit:
                return out
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Why did FATE trade?")
    ap.add_argument("ticker", nargs="?", help="Filter one symbol (e.g. AAPL)")
    ap.add_argument("-n", "--limit", type=int, default=15, help="Max rows per source (default 15)")
    ap.add_argument("--hft", action="store_true", help="Sub-second HFT only")
    ap.add_argument("--paper", action="store_true", help="Paper sim picks only")
    ap.add_argument("--fortress", action="store_true", help="Fortress journal + logs only")
    args = ap.parse_args()

    all_rows: list[dict] = []
    if args.hft:
        all_rows.extend(_hft_events(args.limit, args.ticker))
    elif args.paper:
        all_rows.extend(_paper_sim_picks(args.limit, args.ticker))
    elif args.fortress:
        all_rows.extend(_journal_rows(args.limit, args.ticker))
        all_rows.extend(_fortress_log(args.limit, args.ticker))
    else:
        all_rows.extend(_hft_events(args.limit, args.ticker))
        all_rows.extend(_journal_rows(args.limit, args.ticker))
        all_rows.extend(_paper_sim_picks(min(8, args.limit), args.ticker))
        all_rows.extend(_fortress_log(min(8, args.limit), args.ticker))

    if not all_rows:
        print("No trades found (check hft/logs/, data/journal/trades.csv, reports/paper_sim_*.json)")
        return 1

    all_rows.sort(key=lambda r: r["when"], reverse=True)
    print(f"{'WHEN':<28} {'ENGINE':<18} {'SYM':<8} {'SIDE':<6} WHY")
    print("-" * 100)
    for r in all_rows[: args.limit * 2]:
        print(
            f"{r['when'][:28]:<28} {r['engine']:<18} {r['symbol']:<8} {r['side']:<6} {r['why'][:120]}"
        )
        print(f"  └─ {r['source']}")
    print("\nDecision doc: docs/DECISION_LOGIC.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
