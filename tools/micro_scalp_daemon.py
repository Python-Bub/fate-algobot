#!/usr/bin/env python3
"""Micro-scalp / noise-harvest daemon — high attempt-rate paper sidecar.

Does NOT replace OBI/tape HFT. Places/cancels Alpaca paper limits:
  buy near mid/bid (sane spread) → sell at entry + tick-aware epsilon.

Respects HFT_DRY_RUN. Caps: open scalps, notional, trades/day, PDT-aware.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=False)
_scale = ROOT / "data" / "deploy_scale.env"
if _scale.is_file():
    # deploy_scale must win over stale .env notional / BP knobs
    load_dotenv(_scale, override=True)

from analytics.micro_scalp import (
    build_scalp_plan,
    can_attempt,
    compute_entry_limit,
    default_universe,
    edge_clears_spread,
    hit_stop,
    hit_target,
    load_caps,
    quote_allows_entry,
    spread_reject_reason,
)
from utils import log

STATE_PATH = ROOT / "data" / "intel" / "micro_scalp_state.json"


def order_filled_qty(order: dict | None) -> float:
    """Shares actually filled. Never invent requested size from status=filled."""
    if not order:
        return 0.0
    try:
        fq = float(order.get("filled_qty") or 0)
    except (TypeError, ValueError):
        return 0.0
    if fq > 1e-8:
        return fq
    return 0.0


def scalp_sell_qty(*, filled_qty: float, live_qty: float, sellable: float) -> float:
    """Exit size: confirmed scalp fill, live long, and other-sleeve protection."""
    q = min(float(filled_qty or 0), float(live_qty or 0), float(sellable or 0))
    if q <= 1e-8:
        return 0.0
    if abs(q - round(q)) < 1e-6:
        q = float(int(round(q)))
    return q if q > 0 else 0.0


@dataclass
class OpenScalp:
    ticker: str
    qty: float
    entry_px: float
    target_px: float
    stop_px: float
    opened_ms: float
    entry_order_id: str = ""
    exit_order_id: str = ""
    filled: bool = False
    notional: float = 0.0


@dataclass
class DayState:
    day: str = ""
    trades: int = 0
    attempts: int = 0
    rejects_wide: int = 0
    fills: int = 0
    dry_fires: int = 0
    last_error: str = ""
    cooldowns: dict[str, float] = field(default_factory=dict)


def _enabled() -> bool:
    return os.getenv("MICRO_SCALP_ENABLED", "false").lower() in ("1", "true", "yes")


def _dry_run() -> bool:
    return os.getenv("HFT_DRY_RUN", "false").lower() in ("1", "true", "yes") or os.getenv(
        "MICRO_SCALP_DRY_RUN", "false"
    ).lower() in ("1", "true", "yes")


def _load_day() -> DayState:
    today = date.today().isoformat()
    if not STATE_PATH.is_file():
        return DayState(day=today)
    try:
        raw = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if str(raw.get("day", "")) != today:
            return DayState(day=today)
        return DayState(
            day=today,
            trades=int(raw.get("trades", 0)),
            attempts=int(raw.get("attempts", 0)),
            rejects_wide=int(raw.get("rejects_wide", 0)),
            fills=int(raw.get("fills", 0)),
            dry_fires=int(raw.get("dry_fires", 0)),
            last_error=str(raw.get("last_error", "")),
            cooldowns={str(k): float(v) for k, v in (raw.get("cooldowns") or {}).items()},
        )
    except Exception:
        return DayState(day=today)


def _save_day(st: DayState) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(
            {
                "day": st.day,
                "trades": st.trades,
                "attempts": st.attempts,
                "rejects_wide": st.rejects_wide,
                "fills": st.fills,
                "dry_fires": st.dry_fires,
                "last_error": st.last_error,
                "cooldowns": st.cooldowns,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _account_snapshot() -> tuple[float, int, float]:
    """equity, daytrade_count, buying_power."""
    try:
        from alpaca_broker import get_account, intraday_buying_power

        acct = get_account() or {}
        eq = float(acct.get("equity") or acct.get("portfolio_value") or 0)
        dt = int(float(acct.get("daytrade_count") or 0))
        bp = float(intraday_buying_power(acct))
        return eq, dt, bp
    except Exception:
        return 0.0, 0, 0.0


def _session_ok(*, extended: bool) -> tuple[bool, str]:
    try:
        from analytics.market_session import Session, current_session, orders_allowed

        ok, reason = orders_allowed("buy", for_hft=True)
        if not ok:
            return False, reason
        sess = current_session()
        if extended:
            if sess not in (Session.PRE_MARKET, Session.REGULAR, Session.POST_MARKET):
                return False, f"closed:{sess}"
        elif sess != Session.REGULAR:
            return False, f"rth_only:{sess}"
        return True, reason
    except Exception as e:
        return False, str(e)


class MicroScalpEngine:
    def __init__(self) -> None:
        self.open: dict[str, OpenScalp] = {}
        self.pending_entry: set[str] = set()
        self.day = _load_day()
        self.caps = load_caps()
        self.universe = default_universe()
        self._rr = 0

    def _cooldown_ok(self, ticker: str) -> bool:
        until = self.day.cooldowns.get(ticker, 0.0)
        return time.time() * 1000.0 >= until

    def _set_cooldown(self, ticker: str) -> None:
        self.day.cooldowns[ticker] = time.time() * 1000.0 + self.caps.cooldown_ms

    def _open_notional(self) -> float:
        return sum(s.notional for s in self.open.values())

    def _gate(self) -> tuple[bool, str]:
        eq, dt, _bp = _account_snapshot()
        return can_attempt(
            open_scalps=len(self.open) + len(self.pending_entry),
            open_notional=self._open_notional(),
            trades_today=self.day.trades,
            equity=eq,
            daytrade_count=dt,
            caps=self.caps,
        )

    def _skip_pressure(self, ticker: str) -> str | None:
        """Read-only downward-pressure / earnings flags — do not scalp weakness."""
        try:
            from intel.downward_pressure import assess_downward_pressure, blocks_new_buy

            blocked, reason = blocks_new_buy(ticker)
            if blocked:
                return f"downpress:{reason[:60]}"
            a = assess_downward_pressure(ticker)
            if a.get("tighten_exit"):
                return f"downpress_tighten:{'; '.join((a.get('reasons') or [])[:1])[:50]}"
        except Exception:
            pass
        try:
            from intel.historical_events import event_features

            ef = event_features(ticker)
            dte = ef.get("days_to_earnings")
            if dte is not None and int(dte) <= 1:
                return f"earnings_dte={dte}"
        except Exception:
            pass
        return None

    def monitor_open(self) -> None:
        if not self.open:
            return
        from alpaca_broker import get_quote_bid_ask, submit_limit_order

        now = time.time() * 1000.0
        for sym, pos in list(self.open.items()):
            q = get_quote_bid_ask(sym)
            if not q:
                continue
            bid, ask = q
            held = now - pos.opened_ms
            force = held >= self.caps.max_hold_ms
            stop = hit_stop("buy", pos.entry_px, bid, ask)
            take = hit_target("buy", pos.entry_px, bid, ask)

            if not pos.filled:
                # Only this ticket's filled_qty — broker longs are fortress/HFT, not a scalp fill.
                try:
                    from alpaca_broker import get_order

                    snap = get_order(pos.entry_order_id) if pos.entry_order_id else None
                    fq = order_filled_qty(snap)
                    if fq > 1e-8:
                        pos.filled = True
                        pos.qty = fq
                        avg = float((snap or {}).get("filled_avg_price") or 0)
                        if avg > 0:
                            pos.entry_px = avg
                        plan = build_scalp_plan(pos.entry_px, side="buy")
                        if plan:
                            pos.target_px = plan.target_px
                            pos.stop_px = plan.stop_px
                        pos.notional = pos.qty * pos.entry_px
                        try:
                            from analytics.portfolio_slots import adjust_sleeve_qty

                            adjust_sleeve_qty(sym, "micro_scalp", fq)
                        except Exception:
                            pass
                except Exception:
                    pass
                if (
                    self.caps.entry_timeout_ms > 0
                    and not pos.filled
                    and held >= self.caps.entry_timeout_ms
                ):
                    try:
                        from alpaca_broker import cancel_order

                        if pos.entry_order_id:
                            cancel_order(pos.entry_order_id)
                    except Exception:
                        pass
                    self.open.pop(sym, None)
                    self._set_cooldown(sym)
                    log.info("[MICRO_SCALP] cancel unfilled entry %s", sym)
                continue

            # Time-stop: only dump if we breached stop OR bid is still near entry.
            # Never force a -80bps paper fill just because the clock hit 20s.
            if force and not take and not stop:
                mid = 0.5 * (bid + ask)
                # Still above stop and more than ~8bps underwater → extend hold.
                max_time_loss_bps = float(os.getenv("MICRO_SCALP_MAX_TIME_EXIT_LOSS_BPS", "8"))
                loss_bps = ((pos.entry_px - bid) / pos.entry_px) * 10_000.0 if pos.entry_px > 0 else 0.0
                if bid > pos.stop_px and loss_bps > max_time_loss_bps:
                    # Soft extend: bump opened clock so we re-check later without thrashing.
                    extend_ms = float(os.getenv("MICRO_SCALP_TIME_EXTEND_MS", "45000"))
                    pos.opened_ms = now - max(0.0, self.caps.max_hold_ms - extend_ms)
                    continue

            if take or stop or force:
                if not quote_allows_entry(bid, ask):
                    continue
                from analytics.limit_pricing import exit_limit_px

                exit_px = None
                if take and not force and not stop:
                    exit_px = pos.target_px
                elif stop:
                    # Hard stop: rest at planned stop_px. Never a fantasy bid
                    # 130bps under a 35bps scalp stop (TSLA 332 vs 336).
                    raw = exit_limit_px("sell", bid, ask, pos.entry_px, forced_loss=True)
                    floor = float(pos.stop_px) if pos.stop_px and pos.stop_px > 0 else pos.entry_px
                    exit_px = max(float(raw or 0), floor)
                else:
                    # Max-hold / time: wait for green — never dump below cost.
                    if bid + 1e-12 < pos.entry_px:
                        continue
                    exit_px = exit_limit_px("sell", bid, ask, pos.entry_px, forced_loss=False)
                    if exit_px is not None:
                        exit_px = max(float(exit_px), float(pos.entry_px))
                    if exit_px is not None and bid > 0:
                        mid = 0.5 * (bid + ask)
                        exit_px = max(exit_px, min(mid, bid), pos.entry_px)
                if exit_px is None or exit_px <= 0:
                    continue
                # Reconcile live qty — never sell fortress shares as a scalp exit.
                try:
                    from alpaca_broker import get_position
                    from analytics.portfolio_slots import sellable_qty_for_head

                    live = get_position(sym) or {}
                    live_qty = abs(float(live.get("qty") or 0))
                    sellable = sellable_qty_for_head(
                        sym,
                        "micro_scalp",
                        broker_qty=live_qty,
                        confirmed_fill_qty=float(pos.qty),
                    )
                except Exception:
                    live_qty = 0.0
                    sellable = 0.0
                if live_qty <= 1e-8:
                    log.info("[MICRO_SCALP] exit skip %s — no live long (already flat)", sym)
                    self.open.pop(sym, None)
                    self._set_cooldown(sym)
                    continue
                sell_qty = scalp_sell_qty(
                    filled_qty=float(pos.qty),
                    live_qty=live_qty,
                    sellable=sellable,
                )
                if sell_qty <= 0:
                    log.info(
                        "[MICRO_SCALP] exit skip %s — no scalp qty (live=%.4f sellable=%.4f filled=%.4f) — retry",
                        sym,
                        live_qty,
                        sellable,
                        pos.qty,
                    )
                    continue
                if _dry_run():
                    log.info(
                        "[MICRO_SCALP] DRY exit %s qty=%.4f @ %.4f reason=%s",
                        sym,
                        sell_qty,
                        exit_px,
                        "target" if take else ("stop" if stop else "time"),
                    )
                    self.open.pop(sym, None)
                    self._set_cooldown(sym)
                    self.day.trades += 1
                    continue
                try:
                    submit_limit_order(
                        sym,
                        sell_qty,
                        "sell",
                        float(exit_px),
                        for_hft=True,
                        time_in_force=os.getenv("MICRO_SCALP_EXIT_TIF", "day"),
                    )
                    log.info(
                        "[MICRO_SCALP] EXIT %s qty=%.4f @ %.4f reason=%s",
                        sym,
                        sell_qty,
                        exit_px,
                        "target" if take else ("stop" if stop else "time"),
                    )
                    try:
                        from analytics.portfolio_slots import adjust_sleeve_qty

                        adjust_sleeve_qty(sym, "micro_scalp", -float(sell_qty))
                    except Exception:
                        pass
                    self.open.pop(sym, None)
                    self._set_cooldown(sym)
                    self.day.trades += 1
                    self.day.fills += 1
                except Exception as e:
                    self.day.last_error = str(e)
                    log.warning("[MICRO_SCALP] exit failed %s: %s", sym, e)
                    # Fallback: broker close (handles residual fractional longs).
                    try:
                        from alpaca_broker import close_position_alpaca

                        if close_position_alpaca(sym, force=True, head="micro_scalp", qty=sell_qty):
                            log.info("[MICRO_SCALP] EXIT %s via close_position fallback", sym)
                            self.open.pop(sym, None)
                            self._set_cooldown(sym)
                            self.day.trades += 1
                            self.day.fills += 1
                    except Exception as e2:
                        log.warning("[MICRO_SCALP] close_position fallback failed %s: %s", sym, e2)

    def try_entries(self) -> None:
        ok, reason = self._gate()
        if not ok:
            return
        sess_ok, sess_reason = _session_ok(extended=self.caps.extended)
        if not sess_ok:
            return

        from alpaca_broker import get_quote_bid_ask, submit_limit_order

        n = len(self.universe)
        if n == 0:
            return
        # Round-robin a few symbols per poll for high attempt rate without hammering REST.
        batch = max(1, min(n, int(os.getenv("MICRO_SCALP_BATCH", "4"))))
        for _ in range(batch):
            ok, reason = self._gate()
            if not ok:
                return
            sym = self.universe[self._rr % n]
            self._rr += 1
            if sym in self.open or sym in self.pending_entry:
                continue
            try:
                from alpaca_broker import pending_buy_order

                if pending_buy_order(sym):
                    continue
            except Exception:
                pass
            if not self._cooldown_ok(sym):
                continue
            try:
                from alpaca_broker import get_position

                held = get_position(sym)
                if held and abs(float(held.get("qty") or 0)) > 1e-8:
                    continue
            except Exception:
                continue
            try:
                from analytics.portfolio_slots import load_registry

                head = str(load_registry().get(sym) or "").lower()
                if head in ("fortress", "weekly", "longterm"):
                    continue
            except Exception:
                pass
            skip = self._skip_pressure(sym)
            if skip:
                log.debug("[MICRO_SCALP] skip %s — %s", sym, skip)
                continue

            q = get_quote_bid_ask(sym)
            if not q:
                continue
            bid, ask = q
            rej = spread_reject_reason(bid, ask)
            if rej:
                self.day.rejects_wide += 1
                continue
            entry = compute_entry_limit(bid, ask)
            if entry is None:
                self.day.rejects_wide += 1
                continue
            ok_edge, edge_why = edge_clears_spread(bid, ask, entry)
            if not ok_edge:
                self.day.rejects_wide += 1
                log.debug("[MICRO_SCALP] skip %s — %s", sym, edge_why)
                continue
            plan = build_scalp_plan(entry, side="buy")
            if plan is None:
                continue

            # Skip if target already unreachable vs current ask (edge < spread cost).
            if ask > 0 and plan.target_px <= ask and os.getenv("MICRO_SCALP_REQUIRE_EDGE_OVER_ASK", "true").lower() in (
                "1",
                "true",
                "yes",
            ):
                self.day.rejects_wide += 1
                continue

            _, _, bp = _account_snapshot()
            notional = min(self.caps.per_trade_notional, max(0.0, bp * float(os.getenv("MICRO_SCALP_BP_USE_FRAC", "0.15"))))
            if notional < float(os.getenv("MICRO_SCALP_MIN_NOTIONAL", "200")):
                return
            qty = max(1.0, notional / entry)
            # Prefer whole shares for liquid names unless fractional allowed
            if os.getenv("MICRO_SCALP_FRACTIONAL", "true").lower() not in ("1", "true", "yes"):
                qty = float(max(1, int(qty)))

            self.day.attempts += 1
            if _dry_run():
                self.day.dry_fires += 1
                self.day.trades += 1
                log.info(
                    "[MICRO_SCALP] DRY entry %s qty=%.4f @ %.4f tgt=%.4f stop=%.4f edge=%.4f (%.1f bps)",
                    sym,
                    qty,
                    plan.entry_px,
                    plan.target_px,
                    plan.stop_px,
                    plan.edge_abs,
                    plan.edge_bps,
                )
                self._set_cooldown(sym)
                continue

            self.pending_entry.add(sym)
            try:
                tif = os.getenv("MICRO_SCALP_ENTRY_TIF", "day").lower()
                order = submit_limit_order(
                    sym,
                    qty,
                    "buy",
                    plan.entry_px,
                    for_hft=True,
                    time_in_force=tif,
                )
                oid = str(order.get("id") or "")
                fq = order_filled_qty(order)
                self.open[sym] = OpenScalp(
                    ticker=sym,
                    qty=fq if fq > 1e-8 else qty,
                    entry_px=plan.entry_px,
                    target_px=plan.target_px,
                    stop_px=plan.stop_px,
                    opened_ms=time.time() * 1000.0,
                    entry_order_id=oid,
                    filled=fq > 1e-8,
                    notional=(fq if fq > 1e-8 else qty) * plan.entry_px,
                )
                if self.open[sym].filled:
                    self.day.fills += 1
                log.info(
                    "[MICRO_SCALP] ENTRY %s qty=%.4f @ %.4f tgt=%.4f (%.1f bps) id=%s",
                    sym,
                    qty,
                    plan.entry_px,
                    plan.target_px,
                    plan.edge_bps,
                    oid[:12],
                )
            except Exception as e:
                self.day.last_error = str(e)
                log.warning("[MICRO_SCALP] entry failed %s: %s", sym, e)
            finally:
                self.pending_entry.discard(sym)

    def force_flatten_all(self, *, reason: str) -> int:
        """Flat only this engine's open scalps — never the fortress overnight book."""
        if not self.open:
            return 0
        from alpaca_broker import close_position_alpaca, submit_limit_order, get_quote_bid_ask

        closed = 0
        for sym, pos in list(self.open.items()):
            try:
                if not pos.filled or not (pos.qty > 1e-8):
                    try:
                        from alpaca_broker import cancel_order

                        if pos.entry_order_id:
                            cancel_order(pos.entry_order_id)
                    except Exception:
                        pass
                    self.open.pop(sym, None)
                    self._set_cooldown(sym)
                    continue
                q = get_quote_bid_ask(sym)
                from alpaca_broker import get_position
                from analytics.portfolio_slots import sellable_qty_for_head

                live = abs(float((get_position(sym) or {}).get("qty") or 0))
                qsell = scalp_sell_qty(
                    filled_qty=float(pos.qty),
                    live_qty=live,
                    sellable=sellable_qty_for_head(
                        sym,
                        "micro_scalp",
                        broker_qty=live,
                        confirmed_fill_qty=float(pos.qty),
                    ),
                )
                if qsell <= 0:
                    self.open.pop(sym, None)
                    self._set_cooldown(sym)
                    continue
                if q and qsell > 0:
                    bid, _ask = q
                    submit_limit_order(
                        sym,
                        qsell,
                        "sell",
                        max(bid, 0.01),
                        for_hft=True,
                        time_in_force=os.getenv("MICRO_SCALP_EXIT_TIF", "day"),
                    )
                    closed += 1
                elif close_position_alpaca(sym, force=True, head="micro_scalp", qty=qsell):
                    closed += 1
            except Exception as e:
                try:
                    if pos.filled and close_position_alpaca(
                        sym, force=True, head="micro_scalp", qty=getattr(pos, "qty", None)
                    ):
                        closed += 1
                except Exception as e2:
                    log.warning("[MICRO_SCALP] EOD flatten failed %s: %s / %s", sym, e, e2)
                    continue
            self.open.pop(sym, None)
            self._set_cooldown(sym)
        if closed:
            log.warning("[MICRO_SCALP] %s — flattened %d scalp(s)", reason, closed)
        return closed

    def cycle(self) -> dict:
        self.caps = load_caps()
        if self.day.day != date.today().isoformat():
            self.day = DayState(day=date.today().isoformat())

        # Scalps must not hold overnight; fortress/swing book is untouched.
        flatten_close = os.getenv("MICRO_SCALP_FLATTEN_AT_CLOSE", "true").lower() in (
            "1",
            "true",
            "yes",
        )
        if flatten_close and self.open:
            try:
                from analytics.market_session import minutes_to_rth_close

                mins = minutes_to_rth_close()
                window = float(os.getenv("MICRO_SCALP_EOD_FLATTEN_MINUTES", "5") or 5)
                if mins is not None and mins <= window:
                    self.force_flatten_all(reason=f"EOD flatten ({mins:.0f}m to close)")
            except Exception as e:
                log.debug("[MICRO_SCALP] eod check: %s", e)
            sess_ok, sess_reason = _session_ok(extended=self.caps.extended)
            if not sess_ok and self.open:
                self.force_flatten_all(reason=f"session flat ({sess_reason})")

        self.monitor_open()
        self.try_entries()
        _save_day(self.day)
        return {
            "open": len(self.open),
            "attempts": self.day.attempts,
            "trades": self.day.trades,
            "rejects_wide": self.day.rejects_wide,
            "dry_fires": self.day.dry_fires,
            "fills": self.day.fills,
        }


def main() -> int:
    if not _enabled():
        log.info("[MICRO_SCALP] MICRO_SCALP_ENABLED off — exit")
        return 0
    if os.getenv("HFT_GLOBAL_KILL", "false").lower() in ("1", "true", "yes"):
        log.info("[MICRO_SCALP] HFT_GLOBAL_KILL — refuse start")
        return 2

    eng = MicroScalpEngine()
    poll = eng.caps.poll_sec
    log.info(
        "[MICRO_SCALP] noise-harvest sidecar — %d symbols, poll=%.2fs dry=%s max_open=%d max_day=%d edge_bps=%s",
        len(eng.universe),
        poll,
        _dry_run(),
        eng.caps.max_open,
        eng.caps.max_trades_day,
        os.getenv("MICRO_SCALP_TARGET_BPS", "1"),
    )
    while True:
        try:
            stats = eng.cycle()
            if stats["attempts"] and stats["attempts"] % 50 == 0:
                log.info("[MICRO_SCALP] stats %s", stats)
        except KeyboardInterrupt:
            break
        except Exception as e:
            log.warning("[MICRO_SCALP] cycle error: %s", e)
        time.sleep(max(0.25, load_caps().poll_sec))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
