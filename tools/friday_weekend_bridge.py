#!/usr/bin/env python3
"""
Friday US close → rank with paper_sim_today → BUY top names on Alpaca (paper by default).

Runs only when America/New_York is Friday after the configured close clock (default 16:05),
unless --force. One successful buy batch per ET calendar day (idempotency file).

Env:
  FRIDAY_BRIDGE_ENABLED     true to allow real submits (default false)
  FRIDAY_BRIDGE_DRY_RUN     true = log orders only (default true when ENABLED is false)
  FRIDAY_BRIDGE_CLOSE_HOUR  default 16
  FRIDAY_BRIDGE_CLOSE_MIN   default 5
  FRIDAY_BRIDGE_MAX_BUYS    default 8
  FRIDAY_BRIDGE_SKIP_HELD   skip tickers with existing long (default true)
  FRIDAY_BRIDGE_MAX_SYMBOLS cap passed to paper_sim (optional, speeds scoring)
  FRIDAY_BRIDGE_FALLBACK_MIN_P_UP  if 0 formal BUYs, buy top scores with p_up ≥ this (default 0.52)
  FRIDAY_BRIDGE_FALLBACK_MAX       max names in fallback pool (default 12)
  FRIDAY_BRIDGE_RESPECT_PAPER_SIM_ENV  if true, do not override PAPER_SIM_* universe flags
  ORDER_NOTIONAL / PAPER_EQUITY — sizing & compliance (see compliance_guard)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()
_ROOT = Path(__file__).resolve().parents[1]
_scale = _ROOT / "data" / "deploy_scale.env"
if _scale.is_file():
    load_dotenv(_scale, override=True)


def _lock_paper_sim_universe_for_bridge() -> None:
    """python-dotenv does not override existing shell exports — stale PAPER_SIM_* can shrink universe."""
    if os.getenv("FRIDAY_BRIDGE_RESPECT_PAPER_SIM_ENV", "").lower() in ("1", "true", "yes"):
        return
    os.environ["PAPER_SIM_CONFIG_TICKERS_ONLY"] = "false"
    os.environ["PAPER_SIM_ACTIVE_ONLY"] = "true"
    os.environ["PAPER_SIM_USE_MODEL_UNIVERSE"] = "false"


ET = ZoneInfo("America/New_York")
ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / ".friday_weekend_bridge_state.json"


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name, str(default)).lower().strip()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return default


def _friday_after_close(now_et: datetime, *, close_h: int, close_m: int) -> bool:
    if now_et.weekday() != 4:
        return False
    return (now_et.hour, now_et.minute) >= (close_h, close_m)


def _already_ran_today(now_et: datetime) -> bool:
    if not STATE.is_file():
        return False
    try:
        d = json.loads(STATE.read_text(encoding="utf-8"))
        return str(d.get("et_date")) == now_et.strftime("%Y-%m-%d")
    except Exception:
        return False


def _mark_ran(now_et: datetime, tickers: list[str]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(
        json.dumps({"et_date": now_et.strftime("%Y-%m-%d"), "tickers": tickers}, indent=0),
        encoding="utf-8",
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Friday close weekend bridge → Alpaca buys from paper_sim picks")
    ap.add_argument("--force", action="store_true", help="Ignore Friday/clock gate (still respects idempotency unless --again)")
    ap.add_argument("--again", action="store_true", help="Ignore idempotency state for this run")
    ap.add_argument("--dry-run", action="store_true", help="Never submit orders (overrides FRIDAY_BRIDGE_DRY_RUN)")
    args = ap.parse_args()

    now_et = datetime.now(ET)
    close_h = int(os.getenv("FRIDAY_BRIDGE_CLOSE_HOUR", "16"))
    close_m = int(os.getenv("FRIDAY_BRIDGE_CLOSE_MIN", "5"))

    if not args.force and not _friday_after_close(now_et, close_h=close_h, close_m=close_m):
        print(
            f"[FRIDAY_BRIDGE] skip: not Friday after {close_h:02d}:{close_m:02d} ET "
            f"(now {now_et.strftime('%A %Y-%m-%d %H:%M %Z')}). Use --force to run anyway.",
            file=sys.stderr,
        )
        return 0

    if not args.again and _already_ran_today(now_et):
        print(f"[FRIDAY_BRIDGE] skip: already ran for ET date {now_et.strftime('%Y-%m-%d')} ({STATE})", file=sys.stderr)
        return 0

    enabled = _env_bool("FRIDAY_BRIDGE_ENABLED", False)
    dry = args.dry_run or _env_bool("FRIDAY_BRIDGE_DRY_RUN", not enabled)
    if not enabled and not dry:
        print("[FRIDAY_BRIDGE] FRIDAY_BRIDGE_ENABLED=false — forcing dry-run", file=sys.stderr)
        dry = True

    max_buys = int(os.getenv("FRIDAY_BRIDGE_MAX_BUYS", "8"))
    mx = os.getenv("FRIDAY_BRIDGE_MAX_SYMBOLS", "").strip()
    max_symbols = int(mx) if mx.isdigit() else None
    notional = float(os.getenv("FRIDAY_BRIDGE_NOTIONAL", os.getenv("ORDER_NOTIONAL", "400")))
    equity = float(os.getenv("PAPER_EQUITY", "100000"))
    skip_held = _env_bool("FRIDAY_BRIDGE_SKIP_HELD", True)

    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    _lock_paper_sim_universe_for_bridge()

    from alpaca_broker import get_account
    from utils import log

    if not dry:
        acc = get_account()
        if acc:
            try:
                from analytics.buying_power import clip_ceiling_usd, plan_from_account

                plan = plan_from_account(acc, persist=False)
                eq = float(acc.get("equity") or equity or 0) or 100_000.0
                cap = float(plan.overnight_clip or 0) or clip_ceiling_usd(eq)
            except Exception:
                eq = float(acc.get("equity") or equity or 0) or 100_000.0
                cap = max(400.0, eq * 0.10 * 0.995)
            if notional <= 0:
                notional = cap
            elif cap > 0:
                notional = min(notional, cap)

    from paper_sim_today import run_paper_simulation_today

    log.info("[FRIDAY_BRIDGE] running paper_sim (max_symbols=%s) dry_run=%s", max_symbols, dry)
    out = run_paper_simulation_today(max_symbols=max_symbols)
    rows = out.get("rows") or []
    buys = [r for r in rows if r.get("action") == "BUY"]
    buys.sort(
        key=lambda r: (
            -float(r.get("ai_blend_rank", r.get("score", 0.0))),
            -float(r.get("score", 0.0)),
        )
    )

    if not buys:
        min_p = float(os.getenv("FRIDAY_BRIDGE_FALLBACK_MIN_P_UP", "0.52"))
        fb_max = int(os.getenv("FRIDAY_BRIDGE_FALLBACK_MAX", "12"))
        pool = [
            r
            for r in rows
            if not r.get("skipped")
            and float(r.get("p_up", 0.0)) >= min_p
            and float(r.get("sig_close") or 0.0) > 0
        ]
        pool.sort(key=lambda r: -float(r.get("score", 0.0)))
        buys = pool[: max(max_buys, fb_max)]
        if buys:
            log.warning(
                "[FRIDAY_BRIDGE] no formal BUY picks — score fallback min_p_up=%.2f n=%d",
                min_p,
                len(buys),
            )
        else:
            log.warning("[FRIDAY_BRIDGE] no BUY rows and no fallback candidates — nothing to route")
            _mark_ran(now_et, [])
            return 0

    from alpaca_broker import get_position, place_notional_alpaca
    from compliance_guard import pretrade_check

    placed: list[str] = []
    for r in buys[:max_buys]:
        sym = str(r["ticker"]).upper()
        if skip_held:
            pos = get_position(sym)
            if pos and float(pos.get("qty") or 0) > 0:
                log.info("[FRIDAY_BRIDGE] skip %s (existing long)", sym)
                continue
        px = float(r.get("sig_close") or 0.0)
        qty = max(1.0, notional / px) if px > 0 else 1.0
        c = pretrade_check(sym, "BUY", qty=float(qty), notional=float(notional), is_short=False, equity=equity)
        if not c.ok:
            log.warning("[FRIDAY_BRIDGE] compliance block %s: %s", sym, c.reason)
            continue
        if dry:
            log.warning("[FRIDAY_BRIDGE] DRY-RUN would BUY %s $%.2f", sym, notional)
            placed.append(sym)
            continue
        try:
            from intel.algo_risk_filter import build_trade_constraints_from_risk, screen_buy_risk
            from alpaca_broker import place_smart_buy_alpaca

            risk = screen_buy_risk(sym, hold_days=int(os.getenv("HOLD_DAYS_DEFAULT", "5")))
            trade_c = build_trade_constraints_from_risk(risk)
            place_smart_buy_alpaca(sym, notional, constraints=trade_c)
            placed.append(sym)
        except Exception as e:
            log.exception("[FRIDAY_BRIDGE] order failed %s: %s", sym, e)

    _mark_ran(now_et, placed)
    log.info("[FRIDAY_BRIDGE] done et_date=%s placed=%s dry_run=%s", now_et.strftime("%Y-%m-%d"), placed, dry)
    print(json.dumps({"et_date": now_et.strftime("%Y-%m-%d"), "dry_run": dry, "placed": placed}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
