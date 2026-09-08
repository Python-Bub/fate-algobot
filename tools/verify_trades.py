#!/usr/bin/env python3
"""Verify Alpaca fills vs journal, positions, risk constraints, and pending orders."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
AUDIT_LOG = ROOT / "data" / "trade_verify_log.jsonl"
STATE_PATH = ROOT / "data" / "last_trade_verification.json"

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def _audit(action: str, detail: str, *, ok: bool = True) -> None:
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "detail": detail,
        "ok": ok,
    }
    with AUDIT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def auto_remediate(report: dict) -> list[str]:
    """Close positions when sympathy/time constraints require force exit."""
    if os.getenv("AUTO_VERIFY_REMEDIATE", "true").lower() not in ("1", "true", "yes"):
        return []
    actions: list[str] = []
    for issue in report.get("issues") or []:
        if "FORCE EXIT" not in str(issue):
            continue
        sym = str(issue).split(":", 1)[0].strip().upper()
        if not sym:
            continue
        try:
            from alpaca_broker import close_position_alpaca, get_position, pending_close_order

            if pending_close_order(sym):
                actions.append(f"{sym}: close already queued")
                continue
            pos = get_position(sym)
            if not pos or float(pos.get("qty") or 0) <= 0:
                continue
            if close_position_alpaca(sym):
                actions.append(f"{sym}: auto-closed ({issue})")
                _audit("auto_close", sym)
            else:
                actions.append(f"{sym}: close failed")
                _audit("auto_close_fail", sym, ok=False)
        except Exception as e:
            actions.append(f"{sym}: remediate error: {e}")
            _audit("auto_close_error", f"{sym}: {e}", ok=False)
    return actions


def run_verify_pipeline(
    *,
    days: int = 7,
    quiet: bool = False,
    remediate: bool = True,
    json_out: bool = False,
) -> tuple[dict, int]:
    os.chdir(ROOT)
    rep = verify(days=days, json_out=json_out)
    if remediate:
        actions = auto_remediate(rep)
        if actions:
            rep["remediated"] = actions
            rep = verify(days=days, json_out=json_out)
            rep["remediated"] = actions
    STATE_PATH.write_text(json.dumps(rep, indent=2), encoding="utf-8")
    passed = bool(rep.get("passed"))
    detail = (
        f"positions={rep.get('open_positions')} fills={rep.get('fills')} "
        f"issues={len(rep.get('issues') or [])} warnings={len(rep.get('warnings') or [])}"
    )
    _audit("verify_trades", detail, ok=passed)
    if not quiet:
        if json_out:
            print(json.dumps(rep, indent=2))
        else:
            print("=== TRADE VERIFICATION ===")
            for line in rep.get("ok") or []:
                print(f"  OK   {line}")
            for line in rep.get("warnings") or []:
                print(f"  WARN {line}")
            for line in rep.get("issues") or []:
                print(f"  FAIL {line}")
            for line in rep.get("remediated") or []:
                print(f"  FIX  {line}")
            print(
                f"\n  positions={rep['open_positions']} fills={rep['fills']} "
                f"journal={rep['journal_rows']} passed={rep['passed']}"
            )
            if rep.get("held_symbols"):
                print(f"  held: {', '.join(rep['held_symbols'])}")
            if sys.stdout.isatty():
                print("\n  (automatic — watchdog/autotune re-runs this; no manual action needed)")
    elif not passed:
        print(
            f"[verify-trades] WARN {detail} — see {STATE_PATH.name}",
            flush=True,
        )
    return rep, 0 if passed else 1


def _alpaca_fills(days: int = 7) -> list[dict]:
    k = os.getenv("ALPACA_API_KEY", "").strip()
    s = os.getenv("ALPACA_SECRET_KEY", os.getenv("ALPACA_API_SECRET", "")).strip()
    if not k or not s:
        return []
    import requests

    base = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets").rstrip("/")
    if base.endswith("/v2"):
        base = base[:-3]
    after = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        r = requests.get(
            f"{base}/v2/account/activities/FILL",
            params={"after": after, "direction": "desc"},
            headers={"APCA-API-KEY-ID": k, "APCA-API-SECRET-KEY": s},
            timeout=20,
        )
        r.raise_for_status()
        body = r.json()
        return body if isinstance(body, list) else []
    except Exception:
        return []


def _journal_rows(days: int = 7) -> list[dict]:
    path = ROOT / "data" / "journal" / "trades.csv"
    if not path.is_file():
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    out: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ts = row.get("ts", "")
            try:
                when = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                if when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
            except Exception:
                continue
            if when >= cutoff:
                out.append(row)
    return out


def verify(*, days: int = 7, json_out: bool = False) -> dict:
    from analytics.trade_rotation import RECENT_FILE, _load_json

    issues: list[str] = []
    warnings: list[str] = []
    ok: list[str] = []

    # Sync cooldown file from Alpaca
    try:
        import subprocess

        subprocess.run(
            [sys.executable, "-u", str(ROOT / "tools/sync_recent_trades.py")],
            cwd=ROOT,
            check=False,
            timeout=30,
        )
        ok.append("Synced recent_trades from Alpaca fills")
    except Exception as e:
        warnings.append(f"sync_recent_trades skipped: {e}")

    fills = _alpaca_fills(days=days)
    journal = _journal_rows(days=days)
    recent_doc = _load_json(RECENT_FILE)
    recent_n = len(recent_doc.get("trades") or [])

    positions: list[dict] = []
    open_sells = 0
    try:
        from alpaca_broker import list_open_orders, list_positions, pending_close_order

        positions = list_positions()
        sells = [o for o in list_open_orders() if str(o.get("side", "")).lower() == "sell"]
        open_sells = len(sells)
        for p in positions:
            sym = str(p.get("symbol", "")).replace("/", "-").upper()
            if pending_close_order(sym):
                warnings.append(f"{sym}: pending close sell queued (do not re-liquidate in UI)")
    except Exception as e:
        warnings.append(f"Alpaca position check: {e}")

    held = [
        str(p.get("symbol", "")).replace("/", "-").upper()
        for p in positions
        if abs(float(p.get("qty") or 0)) > 0
    ]

    risk_rows: list[dict] = []
    try:
        from intel.algo_risk_filter import screen_buy_risk

        for sym in held:
            risk = screen_buy_risk(sym)
            risk_rows.append(
                {
                    "symbol": sym,
                    "approved": risk.get("approved"),
                    "warnings": risk.get("warnings") or [],
                    "trade_constraints": risk.get("trade_constraints") or {},
                }
            )
            for w in risk.get("warnings") or []:
                warnings.append(f"{sym}: {w}")
            tc = risk.get("trade_constraints") or {}
            if tc.get("sympathy_trap"):
                warnings.append(
                    f"{sym}: sympathy trap — max_hold={tc.get('max_hold_days')}d "
                    f"TP={float(tc.get('take_profit_pct', 0))*100:.1f}% "
                    f"exit_before={tc.get('force_exit_before_date')}"
                )
    except Exception as e:
        warnings.append(f"Risk screen on holdings: {e}")

    constraints: dict[str, dict] = {}
    try:
        from intel.trade_constraints import get_constraints, should_force_exit

        for sym in held:
            c = get_constraints(sym)
            if c:
                constraints[sym] = c
            force, reason = should_force_exit(sym)
            if force:
                issues.append(f"{sym}: FORCE EXIT — {reason}")
    except Exception:
        pass

    if fills and not journal:
        warnings.append(
            f"Alpaca has {len(fills)} fills in {days}d but journal/trades.csv has 0 — "
            "fortress may not be logging (check log_trade path)"
        )
    elif fills:
        ok.append(f"Alpaca fills ({days}d): {len(fills)} | journal rows: {len(journal)} | cooldown sync: {recent_n}")

    if open_sells and not held:
        warnings.append(f"{open_sells} open sell orders but no positions — stale orders?")

    report = {
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "days": days,
        "fills": len(fills),
        "journal_rows": len(journal),
        "recent_trades_synced": recent_n,
        "open_positions": len(held),
        "held_symbols": held,
        "open_sell_orders": open_sells,
        "issues": issues,
        "warnings": warnings,
        "ok": ok,
        "risk_on_holdings": risk_rows,
        "active_constraints": constraints,
        "passed": len(issues) == 0,
    }
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify trades, positions, and risk constraints")
    ap.add_argument("--days", type=int, default=int(os.getenv("VERIFY_TRADES_DAYS", "7")))
    ap.add_argument("--json", action="store_true")
    ap.add_argument(
        "--quiet",
        action="store_true",
        help="Daemon mode — minimal stdout (used by watchdog/autotune)",
    )
    ap.add_argument(
        "--no-remediate",
        action="store_true",
        help="Audit only — do not auto-close force-exit positions",
    )
    args = ap.parse_args()
    quiet = args.quiet or os.getenv("VERIFY_TRADES_QUIET", "").lower() in ("1", "true", "yes")
    _, code = run_verify_pipeline(
        days=args.days,
        quiet=quiet,
        remediate=not args.no_remediate,
        json_out=args.json,
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
