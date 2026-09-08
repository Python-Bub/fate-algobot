#!/usr/bin/env python3
"""Export human-readable ALL_EARNINGS_DATES.md (+ .json) from shared calendar + overrides."""

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

OUT_MD = ROOT / "data" / "ops" / "ALL_EARNINGS_DATES.md"
OUT_JSON = ROOT / "data" / "ops" / "ALL_EARNINGS_DATES.json"

MEGA = [
    "AAPL", "MSFT", "AMZN", "GOOGL", "GOOG", "META", "NVDA", "AMD", "AVGO", "TSLA",
    "NFLX", "ORCL", "CRM", "NOW", "ADBE", "INTC", "QCOM", "COST", "WMT", "JNJ",
    "JPM", "V", "MA", "UNH", "XOM", "PG", "HD", "BAC", "KO", "PEP", "SBUX", "BX",
]


def _force_list() -> list[str]:
    raw = os.getenv("FORTRESS_FORCE_BUY_SYMBOLS", "")
    out = [x.strip().upper() for x in raw.split(",") if x.strip()]
    try:
        doc = json.loads((ROOT / "data" / "ops" / "force_buy_watch.json").read_text())
        out.extend(str(s).upper() for s in (doc.get("symbols") or []))
    except Exception:
        pass
    return sorted(set(out))


def _holdings() -> list[str]:
    try:
        from alpaca_broker import list_positions

        return sorted({str(p.get("symbol") or "").upper() for p in list_positions() if p.get("symbol")})
    except Exception:
        return []


def main() -> int:
    # Load deploy/.env so Alpaca holdings resolve for the export.
    for p in (ROOT / ".env", ROOT / "data" / "deploy_scale.env"):
        if not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

    from intel.earnings_calendar import (
        build_shared_earnings_calendar,
        earnings_snapshot,
        load_shared_earnings_calendar,
        _load_calendar_overrides,
    )

    force = "--force" in sys.argv or "--refresh" in sys.argv
    if force or not (ROOT / "data" / "intel" / "earnings_calendar.json").is_file():
        build_shared_earnings_calendar(force_refresh=force)

    cal = load_shared_earnings_calendar()
    symbols_doc = cal.get("symbols") if isinstance(cal.get("symbols"), dict) else {}
    overrides = _load_calendar_overrides()
    force_syms = _force_list()
    held = _holdings()
    priority = sorted(set(MEGA) | set(force_syms) | set(held) | set(overrides.keys()))

    rows: list[dict] = []
    for sym in priority:
        snap = earnings_snapshot(sym, force_refresh=False)
        shared = symbols_doc.get(sym) if isinstance(symbols_doc.get(sym), dict) else {}
        ov = overrides.get(sym) if isinstance(overrides.get(sym), dict) else {}
        row = {
            "symbol": sym,
            "group": (
                "holding" if sym in held else
                "force" if sym in force_syms else
                "mega" if sym in MEGA else
                "override"
            ),
            "next_earnings_date": snap.get("next_earnings_date") or shared.get("next_earnings_date"),
            "hour": snap.get("hour") or shared.get("hour"),
            "session": snap.get("session") or shared.get("session"),
            "next_datetime_et": snap.get("next_datetime_et") or shared.get("next_datetime_et"),
            "next_datetime_pt": snap.get("next_datetime_pt") or shared.get("next_datetime_pt"),
            "call_time_pt": snap.get("call_time_pt") or shared.get("call_time_pt") or ov.get("last_call_time_pt"),
            "call_time_et": snap.get("call_time_et") or shared.get("call_time_et"),
            "prev_earnings_date": snap.get("prev_earnings_date"),
            "last_earnings_date": snap.get("last_earnings_date") or ov.get("last_earnings_date") or shared.get("last_earnings_date"),
            "last_results_release": snap.get("last_results_release") or ov.get("last_results_release") or shared.get("last_results_release"),
            "days_to_earnings": snap.get("days_to_earnings"),
            "days_since_earnings": snap.get("days_since_earnings"),
            "is_holding": sym in held,
            "is_force": sym in force_syms,
            "note": ov.get("note") or shared.get("calendar_override_note"),
        }
        rows.append(row)

    # Also dump near_7d from shared calendar for breadth.
    near = list(cal.get("near_7d") or [])

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "updated_at": now,
        "as_of": cal.get("as_of") or date.today().isoformat(),
        "shared_calendar": "data/intel/earnings_calendar.json",
        "overrides": "data/intel/earnings_calendar_overrides.json",
        "coverage": {
            "universe_n": cal.get("universe_n"),
            "with_next_date": cal.get("with_next_date"),
            "with_session_hour": cal.get("with_session_hour"),
        },
        "priority_rows": rows,
        "near_7d": near,
        "holdings": held,
        "force_symbols": force_syms,
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [
        "# ALL EARNINGS DATES",
        "",
        f"Updated: `{now}` (UTC)",
        f"Shared calendar: `data/intel/earnings_calendar.json` (as_of={cal.get('as_of')})",
        f"Overrides: `data/intel/earnings_calendar_overrides.json`",
        f"Coverage: {cal.get('with_next_date')}/{cal.get('universe_n')} with next date; "
        f"{cal.get('with_session_hour')} with session hour",
        "",
        "## Priority (mega-caps + FORCE + holdings)",
        "",
        "| Symbol | Group | Next | Session | Call PT | Last print | Days since | Days to | Holding |",
        "|--------|-------|------|---------|---------|------------|------------|---------|---------|",
    ]
    for r in sorted(rows, key=lambda x: (x.get("days_to_earnings") is None, x.get("days_to_earnings") or 999, x["symbol"])):
        lines.append(
            f"| {r['symbol']} | {r['group']} | {r.get('next_earnings_date') or '—'} | "
            f"{r.get('hour') or r.get('session') or '—'} | {r.get('call_time_pt') or '—'} | "
            f"{r.get('last_earnings_date') or r.get('prev_earnings_date') or '—'} | "
            f"{r.get('days_since_earnings') if r.get('days_since_earnings') is not None else '—'} | "
            f"{r.get('days_to_earnings') if r.get('days_to_earnings') is not None else '—'} | "
            f"{'Y' if r.get('is_holding') else ''} |"
        )

    lines.extend(["", "## Near 7 days (shared calendar sample)", ""])
    if near:
        lines.append("| Symbol | Date | Hour | Call PT | Days to |")
        lines.append("|--------|------|------|---------|---------|")
        for n in near[:60]:
            lines.append(
                f"| {n.get('symbol')} | {n.get('date')} | {n.get('hour') or '—'} | "
                f"{n.get('call_time_pt') or '—'} | {n.get('days_to')} |"
            )
    else:
        lines.append("_none_")

    lines.extend(
        [
            "",
            "## Notes",
            "- Index ETF buys remain banned (SPY/QQQ/IWM).",
            "- `last_earnings_date` from overrides feeds radar `days_since` after Finnhub rolls next quarter.",
            f"- Full machine dump: `{OUT_JSON.relative_to(ROOT)}`",
            "",
        ]
    )
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT_MD}")
    print(f"Wrote {OUT_JSON}")
    print(f"priority_rows={len(rows)} near_7d={len(near)} holdings={held}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
