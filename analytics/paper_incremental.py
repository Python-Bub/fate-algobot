"""Incremental paper sim — reuse prior report rows when signal bar unchanged."""

from __future__ import annotations

import os
from typing import Any


def plan_incremental_rescore(
    symbols: list[str],
    *,
    signal_date: str,
) -> tuple[list[dict], list[str], dict[str, Any]]:
    """Return (rows_to_reuse, symbols_to_rescore, meta).

    When the latest signal bar matches the previous good report, reuse scored rows
    instead of rebuilding 8y of features + news for every ticker.
    """
    meta: dict[str, Any] = {
        "enabled": False,
        "signal_date": signal_date,
        "reused": 0,
        "rescored": len(symbols),
        "prev_report": "",
    }
    if os.getenv("PAPER_SIM_INCREMENTAL", "true").lower() not in ("1", "true", "yes"):
        return [], list(symbols), meta

    if not signal_date:
        return [], list(symbols), meta

    from analytics.paper_report import latest_valid_report

    max_age = float(os.getenv("PAPER_SIM_INCREMENTAL_MAX_AGE_H", "168"))
    prev_path, prev = latest_valid_report(min_rows=50, max_age_hours=max_age)
    if not prev or not prev_path:
        return [], list(symbols), meta

    prev_by_t: dict[str, dict] = {}
    for row in prev.get("rows") or []:
        if row.get("skipped") or "score" not in row:
            continue
        t = str(row.get("ticker", "")).upper()
        if t:
            prev_by_t[t] = row

    force_top = os.getenv("PAPER_SIM_INCREMENTAL_REFRESH_TOP100", "false").lower() in (
        "1",
        "true",
        "yes",
    )
    top_set: set[str] = set()
    if force_top:
        try:
            from fortress_universe import load_top100_symbols

            top_set = set(load_top100_symbols())
        except Exception:
            top_set = set()

    reuse: list[dict] = []
    rescore: list[str] = []
    for t in symbols:
        sym = str(t).upper()
        prev_row = prev_by_t.get(sym)
        if prev_row is None:
            rescore.append(sym)
            continue
        if sym in top_set:
            rescore.append(sym)
            continue
        if str(prev_row.get("signal_date") or "") != signal_date:
            rescore.append(sym)
            continue
        reuse.append(dict(prev_row))

    meta.update(
        {
            "enabled": True,
            "reused": len(reuse),
            "rescored": len(rescore),
            "prev_report": prev_path.name,
        }
    )
    return reuse, rescore, meta
