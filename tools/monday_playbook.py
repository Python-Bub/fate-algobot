#!/usr/bin/env python3
"""Build Monday preorder playbook: fresh paper_sim rank + family forecast + holdings snapshot."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
ET = ZoneInfo("America/New_York")
DEFAULT_OUT = ROOT / "data" / "monday_playbook.json"
PY = ROOT / "venv" / "bin" / "python"


def _run_paper_sim() -> int:
    env = os.environ.copy()
    env.setdefault("PAPER_SIM_ACTIVE_ONLY", "true")
    env.setdefault("PAPER_SIM_ACTIVE_MODE", "top100_rotate")
    env.setdefault("PAPER_SIM_ALLOW_SHORTS", "false")
    # Monday prep / weekend ranking must still score (no order placement in sim).
    env["PAPER_SIM_ALLOW_OFFHOURS"] = env.get("PAPER_SIM_ALLOW_OFFHOURS", "true")
    print("[monday-prep] running fresh paper_sim_today rank…", flush=True)
    r = subprocess.run(
        [str(PY), "-u", "paper_sim_today.py"],
        cwd=ROOT,
        env=env,
        timeout=int(os.getenv("MONDAY_PREP_PAPER_TIMEOUT_SEC", "3600")),
    )
    return r.returncode


def _family_json() -> dict:
    timeout = int(os.getenv("MONDAY_FAMILY_TIMEOUT_SEC", "420"))
    r = subprocess.run(
        [str(PY), "-u", "tools/family_forecast.py", "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if r.returncode != 0:
        return {"error": (r.stderr or r.stdout or "")[:400]}
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return {"error": "family_forecast json parse failed"}


def _latest_report_rows() -> list[dict]:
    from analytics.paper_report import latest_valid_report

    _path, doc = latest_valid_report(min_rows=1)
    if not doc:
        return []
    rows = doc.get("rows") or doc.get("results") or []
    out: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        sym = str(row.get("ticker") or row.get("symbol") or "").upper()
        if not sym:
            continue
        p = float(row.get("p_adj") or row.get("p_up") or row.get("score") or 0.0)
        sig = str(row.get("signal") or row.get("decision") or "").upper()
        if sig and sig not in ("BUY", "UP", "LONG"):
            if p < float(os.getenv("MONDAY_PREP_MIN_P_UP", "0.58")):
                continue
        out.append(
            {
                "ticker": sym,
                "p_adj": p,
                "score": float(row.get("score") or p),
                "signal": sig or "BUY",
                "source": "paper_sim",
            }
        )
    out.sort(key=lambda x: x["score"], reverse=True)
    return out


def _holdings() -> list[str]:
    try:
        from alpaca_broker import list_positions

        held = []
        for p in list_positions():
            if float(p.get("qty") or 0) <= 0:
                continue
            sym = str(p.get("symbol", "")).replace("/", "-").upper()
            if sym:
                held.append(sym)
        return held
    except Exception:
        return []


def build_playbook(*, run_sim: bool = True) -> dict:
    if run_sim:
        rc = _run_paper_sim()
        if rc != 0:
            print(f"[monday-prep] paper_sim exit={rc} — using latest report if any", flush=True)

    paper_rows = _latest_report_rows()
    try:
        family = _family_json()
    except Exception as e:
        print(f"[monday-prep] family_forecast skipped: {e}", flush=True)
        family = {"error": str(e)[:200]}
    held = _holdings()

    seen: set[str] = set()
    preorders: list[dict] = []
    max_n = int(os.getenv("MONDAY_PREP_MAX_PREORDERS", "12"))

    pool: list[dict] = []
    pool_max = int(os.getenv("MONDAY_PREP_POOL_MAX", "80"))
    for row in paper_rows[:pool_max]:
        t = row["ticker"]
        if t in seen or t in held:
            continue
        try:
            from intel.near_term_headwinds import assess_near_term_headwind

            hw = assess_near_term_headwind(t)
            if hw.get("block_playbook"):
                continue
            if hw.get("score_penalty"):
                row = {**row, "score": float(row.get("score", 0)) - float(hw["score_penalty"])}
        except Exception:
            pass
        pool.append({**row, "source": row.get("source", "paper_sim")})
    try:
        from analytics.industries.project_wiring import wire_monday_pick

        pool = [wire_monday_pick(r) for r in pool]
    except Exception:
        pass
    try:
        from analytics.trade_rotation import select_diversified_buys

        picked = select_diversified_buys(pool, max_n, score_key="score", ticker_key="ticker", held=held)
        for p in picked:
            seen.add(p["ticker"])
            preorders.append({**p, "rank": len(preorders) + 1})
    except Exception:
        for row in paper_rows:
            t = row["ticker"]
            if t in seen or t in held:
                continue
            seen.add(t)
            preorders.append({**row, "rank": len(preorders) + 1})
            if len(preorders) >= max_n:
                break

    for pick in (family.get("best_per_horizon") or []):
        t = str(pick.get("ticker") or "").upper()
        if not t or t in seen or t in held:
            continue
        if str(pick.get("signal", "")).upper() == "DOWN":
            continue
        try:
            from intel.near_term_headwinds import blocks_horizon_pick, blocks_playbook_buy

            hz = str(pick.get("label") or "this_week")
            if blocks_playbook_buy(t)[0] or blocks_horizon_pick(t, hz)[0]:
                continue
        except Exception:
            pass
        L = t[0] if t else "?"
        if sum(1 for p in preorders if str(p.get("ticker", "")).upper().startswith(L)) >= int(
            os.getenv("TRADE_MAX_BUYS_PER_LETTER", "1")
        ):
            continue
        seen.add(t)
        preorders.append(
            {
                "ticker": t,
                "p_adj": float(pick.get("p_up") or pick.get("chance_pct", 0) / 100.0),
                "score": float(pick.get("chance_pct") or 0) / 100.0,
                "signal": str(pick.get("signal") or "UP"),
                "source": "family_forecast",
                "horizon": pick.get("label"),
                "rank": len(preorders) + 1,
            }
        )
        if len(preorders) >= max_n:
            break

    now_et = datetime.now(ET)
    # If paper report is empty/stale, keep prior playbook names so Monday isn't blank.
    if len(preorders) < max(3, max_n // 3):
        try:
            prev_path = Path(os.getenv("MONDAY_PLAYBOOK_PATH", str(DEFAULT_OUT)))
            if prev_path.is_file():
                prev = json.loads(prev_path.read_text(encoding="utf-8"))
                for row in prev.get("preorders") or []:
                    t = str(row.get("ticker") or "").upper()
                    if not t or t in seen or t in held:
                        continue
                    seen.add(t)
                    preorders.append({**row, "rank": len(preorders) + 1, "source": row.get("source", "prior_playbook")})
                    if len(preorders) >= max_n:
                        break
        except Exception:
            pass

    doc = {
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "built_at_et": now_et.isoformat(),
        "target_session": "Monday RTH",
        "trade_start_et": os.getenv("TRADE_START_ET", "12:30"),
        "trade_end_et": os.getenv("TRADE_END_ET", "16:00"),
        "trade_session_mode": os.getenv("TRADE_SESSION_MODE", "rth"),
        "holdings_skip": held,
        "preorders": preorders,
        "family_forecast": family,
        "paper_sim_top": paper_rows[:20],
        "notes": [
            "Fortress prioritizes playbook tickers when TRADE_START_ET window opens.",
            "Remove or clear TRADE_START_ET after Monday if you want 9:30 open again.",
            "Near-term headwinds: META/MSFT blocked from playbook; AVGO dip-watch only (see data/near_term_headwinds.json).",
        ],
    }
    return doc


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Monday preorder playbook")
    ap.add_argument("--skip-sim", action="store_true", help="Use latest paper_sim report only")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))

    doc = build_playbook(run_sim=not args.skip_sim)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2), encoding="utf-8")

    n = len(doc.get("preorders") or [])
    print(f"[monday-prep] wrote {out} — {n} preorders (start {doc.get('trade_start_et')} ET)", flush=True)
    for p in (doc.get("preorders") or [])[:8]:
        print(
            f"  #{p.get('rank')} {p.get('ticker')} score={p.get('score', 0):.3f} "
            f"via {p.get('source')}",
            flush=True,
        )
    return 0 if n > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
