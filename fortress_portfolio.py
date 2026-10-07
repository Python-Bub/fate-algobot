"""Alpaca-aware portfolio sizing: stay mostly invested, DCA dips, re-enter after TP."""

from __future__ import annotations

import os
from pathlib import Path

from risk_manager import OpenLeg, RiskManager
from utils import log


def _f(name: str, default: float) -> float:
    try:
        from self_modify.policy_agent import get_runtime_param

        if name == "ORDER_NOTIONAL":
            return float(get_runtime_param(name, float(os.getenv(name, str(default)))))
    except Exception:
        pass
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default


def _position_gain_frac(pos: dict) -> float | None:
    uplpc = pos.get("unrealized_plpc")
    if uplpc is not None:
        return float(uplpc)
    try:
        entry = float(pos.get("avg_entry_price") or 0)
        cur = float(pos.get("current_price") or 0)
        if entry > 0 and cur > 0:
            return (cur - entry) / entry
    except (TypeError, ValueError):
        pass
    return None


def maybe_trim_index_etfs_for_force(
    *,
    force_count: int = 1,
    equity: float = 0.0,
) -> int:
    """Partial-trim held index ETFs to free cash for FORCE single-name buys.

    Does NOT wipe overnight inventory. Only sells a fraction of SPY/QQQ/IWM/…
    when FORTRESS_INDEX_SOFT_TRIM is on and FORCE candidates need room under
    the single-name 10% equity cap.
    """
    if force_count <= 0:
        return 0
    if os.getenv("FORTRESS_INDEX_SOFT_TRIM", "true").lower() not in ("1", "true", "yes"):
        return 0
    # Overnight hold ON → never full-close indexes here; partial trim only.
    overnight = os.getenv("FORTRESS_OVERNIGHT_HOLD", "true").lower() in ("1", "true", "yes")
    ban_raw = os.getenv(
        "FORTRESS_BAN_INDEX_ETFS",
        "SPY,QQQ,IWM,DIA,VOO,VTI,SOXX,XLK,XLF,XLE",
    )
    indexes = {s.strip().upper() for s in ban_raw.split(",") if s.strip()}
    max_frac = _f("FORTRESS_MAX_SINGLE_FRAC", 0.10)
    # Free up to one single-name clip per FORCE candidate (capped).
    target_free = max_frac * max(equity, 1.0) * min(force_count, 3)
    trim_frac = _f("FORTRESS_INDEX_TRIM_FRAC", 0.35)  # sell ≤35% of each index leg
    if overnight:
        trim_frac = min(trim_frac, _f("FORTRESS_INDEX_TRIM_FRAC_OVERNIGHT", 0.25))
    trimmed = 0
    freed = 0.0
    try:
        from alpaca_broker import close_position_alpaca, list_positions

        for p in list_positions():
            if freed >= target_free:
                break
            sym = str(p.get("symbol", "")).replace("/", "-").upper()
            if sym not in indexes:
                continue
            qty = float(p.get("qty") or 0)
            mv = abs(float(p.get("market_value") or 0))
            if qty <= 0 or mv <= 0:
                continue
            sell_qty = max(0.0, qty * trim_frac)
            # Prefer trimming overweight (> max_frac of equity) first.
            if equity > 0 and mv / equity > max_frac * 1.01:
                sell_qty = max(sell_qty, qty * min(0.5, (mv - equity * max_frac) / mv))
            if sell_qty <= 1e-6:
                continue
            sell_qty = min(sell_qty, qty * 0.5)  # hard: never sell more than half in one soft-trim
            if close_position_alpaca(sym, qty=sell_qty, head="fortress"):
                trimmed += 1
                freed += mv * (sell_qty / qty)
                log.warning(
                    "[PORTFOLIO] soft-trim index %s qty=%.4f (~$%.0f) for FORCE singles (overnight=%s)",
                    sym,
                    sell_qty,
                    mv * (sell_qty / qty),
                    overnight,
                )
    except Exception as e:
        log.warning("[PORTFOLIO] index soft-trim failed: %s", e)
    return trimmed


def liquidate_losing_positions() -> int:
    """Close longs below LIQUIDATE_MIN_LOSS_PCT unrealized (default -0.25%).

    Skips names whose live NBBO is absurdly wide — paper marks on fantasy bids
    must not force instant stop-outs (AGL-style bid/ask gaps).
    """
    closed = 0
    cut = _f("LIQUIDATE_MIN_LOSS_PCT", 0.0025)
    try:
        from alpaca_broker import close_position_alpaca, get_quote_bid_ask, list_positions
        from analytics.limit_pricing import quote_is_sane

        for p in list_positions():
            side = str(p.get("side", "")).lower()
            qty = float(p.get("qty") or 0)
            if qty <= 0 or side == "short":
                continue
            gain = _position_gain_frac(p)
            if gain is None or gain >= -cut:
                continue
            sym = str(p.get("symbol", "")).replace("/", "-").upper()
            if not sym or _hygiene_protected(sym):
                continue
            if _hygiene_close_skip(sym):
                continue
            if not _hygiene_min_hold_ok(p):
                continue
            q = get_quote_bid_ask(sym)
            if q and not quote_is_sane(q[0], q[1]):
                if os.getenv("PAPER_HYGIENE_AGGRESSIVE", "false").lower() not in (
                    "1",
                    "true",
                    "yes",
                ):
                    log.warning(
                        "[PORTFOLIO] skip liquidate %s gain=%.2f%% — wide quote bid=%.2f ask=%.2f",
                        sym,
                        100 * gain,
                        q[0],
                        q[1],
                    )
                    continue
                log.warning(
                    "[PORTFOLIO] liquidate %s gain=%.2f%% despite wide quote bid=%.2f ask=%.2f",
                    sym,
                    100 * gain,
                    q[0],
                    q[1],
                )
            if close_position_alpaca(sym, force=True):
                closed += 1
                log.warning("[PORTFOLIO] liquidated loser %s gain=%.2f%%", sym, 100 * gain)
                try:
                    from online_learning.trade_feedback import learn_from_realized_trade

                    learn_from_realized_trade(sym, "LONG", float(gain), source="hygiene_loser")
                except Exception:
                    pass
    except Exception as e:
        log.debug("[PORTFOLIO] liquidate losers: %s", e)
    return closed


def liquidate_off_quality_positions() -> int:
    """Close longs not on the HFT quality whitelist (speculative names).

    Only cuts losers / flat — never force-sell a green fortress/weekly name just
    because it is absent from the HFT whitelist (that locked in winners as 'junk').
    """
    closed = 0
    try:
        from alpaca_broker import close_position_alpaca, list_positions
        from fortress_universe import is_hft_quality_equity, is_tradeable_equity

        junk_cut = _f("LIQUIDATE_OFF_QUALITY_MAX_GAIN_PCT", 0.0)
        for p in list_positions():
            sym = str(p.get("symbol", "")).replace("/", "-").upper()
            if not sym or not is_tradeable_equity(sym) or _hygiene_protected(sym):
                continue
            if float(p.get("qty") or 0) <= 0:
                continue
            if is_hft_quality_equity(sym):
                continue
            if _hygiene_close_skip(sym):
                continue
            if not _hygiene_min_hold_ok(p):
                continue
            gain = _position_gain_frac(p)
            if gain is not None and gain > junk_cut:
                continue
            if close_position_alpaca(sym):
                closed += 1
                log.warning("[PORTFOLIO] liquidated off-quality %s", sym)
                gain = _position_gain_frac(p)
                if gain is not None:
                    try:
                        from online_learning.trade_feedback import learn_from_realized_trade

                        learn_from_realized_trade(sym, "LONG", float(gain), source="hygiene_junk")
                    except Exception:
                        pass
    except Exception as e:
        log.debug("[PORTFOLIO] liquidate off-quality: %s", e)
    return closed


def _hygiene_skip_tickers() -> set[str]:
    raw = os.getenv("PAPER_HYGIENE_SKIP_TICKERS", "")
    return {s.strip().upper() for s in raw.split(",") if s.strip()}


def _hygiene_protected(sym: str) -> bool:
    return sym.upper() in _hygiene_skip_tickers()


def _hygiene_close_skip(sym: str) -> bool:
    """Skip if any sell is already working (avoids cancel/requeue storms)."""
    try:
        from alpaca_broker import open_sell_orders, pending_close_order

        if pending_close_order(sym):
            return True
        if open_sell_orders(sym):
            return True
    except Exception:
        pass
    return False


def _hygiene_min_hold_ok(pos: dict) -> bool:
    """Don't news/hygiene-cut names held under HYGIENE_MIN_HOLD_MIN (default 45)."""
    try:
        min_m = float(os.getenv("HYGIENE_MIN_HOLD_MIN", "45"))
    except (TypeError, ValueError):
        min_m = 45.0
    if min_m <= 0:
        return True
    raw = pos.get("created_at") or pos.get("opened_at")
    if not raw:
        return True
    try:
        from datetime import datetime, timezone

        ts = str(raw).replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        held_min = (datetime.now(timezone.utc) - dt).total_seconds() / 60.0
        return held_min >= min_m
    except Exception:
        return True



def liquidate_news_blocked_positions() -> int:
    """Close longs where hft_trade_news.json has allow_long=false.

    Default is conservative: require clearly bearish intensity (not a soft allow_long=false
    with positive intensity), and skip green names unless NEWS_CLOSE_WINNERS=true.
    Disable entirely with PAPER_HYGIENE_NEWS_CLOSE=false.
    """
    if os.getenv("PAPER_HYGIENE_NEWS_CLOSE", "true").lower() not in ("1", "true", "yes"):
        return 0
    closed = 0
    path = Path(os.getenv("HFT_TRADE_NEWS_PATH", "data/intel/hft_trade_news.json"))
    if not path.is_file():
        return 0
    try:
        import json
        import time as _time

        from alpaca_broker import close_position_alpaca, list_positions

        data = json.loads(path.read_text(encoding="utf-8"))
        min_bad = _f("HYGIENE_NEWS_MIN_BAD_INTENSITY", -0.35)
        max_age_h = _f("HYGIENE_NEWS_MAX_AGE_HOURS", 18.0)
        updated_ms = float(data.get("updated_ms") or 0)
        if updated_ms > 0 and max_age_h > 0:
            age_h = (_time.time() * 1000.0 - updated_ms) / 3_600_000.0
            # updated_ms may be wall-clock ms; if absurdly in the future, ignore age gate
            if 0 < age_h < 1e6 and age_h > max_age_h:
                log.info("[PORTFOLIO] skip news-close — news file age %.1fh > %.1fh", age_h, max_age_h)
                return 0
        tickers = data.get("tickers") or {}
        blocked: set[str] = set()
        for sym, row in tickers.items():
            if row.get("allow_long") is not False:
                continue
            try:
                intensity = float(row.get("intensity") or 0.0)
            except (TypeError, ValueError):
                intensity = 0.0
            # Soft blocks (allow_long=false but intensity not clearly bad) must not wipe books.
            if intensity > min_bad:
                continue
            blocked.add(str(sym).upper())
        if not blocked:
            return 0
        close_winners = os.getenv("NEWS_CLOSE_WINNERS", "false").lower() in ("1", "true", "yes")
        for p in list_positions():
            sym = str(p.get("symbol", "")).replace("/", "-").upper()
            if sym not in blocked or float(p.get("qty") or 0) <= 0 or _hygiene_protected(sym):
                continue
            if _hygiene_close_skip(sym):
                continue
            if not _hygiene_min_hold_ok(p):
                continue
            gain = _position_gain_frac(p)
            if not close_winners and gain is not None and gain > 0:
                continue
            if close_position_alpaca(sym):
                closed += 1
                log.warning("[PORTFOLIO] closed news-blocked %s", sym)
    except Exception as e:
        log.warning("[PORTFOLIO] news-blocked cleanup: %s", e)
    return closed


def liquidate_outside_obi_scope() -> int:
    """Close longs not on OBI_TICKER_WHITELIST — OFF by default (fortress uses its own universe)."""
    if os.getenv("PAPER_HYGIENE_OBI_SCOPE", "false").lower() not in ("1", "true", "yes"):
        return 0
    closed = 0
    raw = os.getenv(
        "OBI_TICKER_WHITELIST",
        "NVDA,AMD,TSLA,MSFT,NFLX,AMZN,AAPL,META,GOOGL,SBUX,BX,AVGO",
    )
    scope = {s.strip().upper() for s in raw.split(",") if s.strip()}
    try:
        from alpaca_broker import close_position_alpaca, list_positions, pending_close_order

        for p in list_positions():
            sym = str(p.get("symbol", "")).replace("/", "-").upper()
            if not sym or sym in scope or float(p.get("qty") or 0) <= 0 or _hygiene_protected(sym):
                continue
            if _hygiene_close_skip(sym):
                continue
            if close_position_alpaca(sym):
                closed += 1
                log.warning("[PORTFOLIO] closed outside OBI scope %s", sym)
    except Exception as e:
        log.warning("[PORTFOLIO] outside OBI cleanup: %s", e)
    return closed


def paper_portfolio_hygiene() -> dict[str, int]:
    """Shorts + losers + off-scope / news-blocked names."""
    aggressive = os.getenv("PAPER_HYGIENE_AGGRESSIVE", "false").lower() in ("1", "true", "yes")
    return {
        "shorts": close_all_short_positions(),
        "losers": liquidate_losing_positions() if aggressive else 0,
        "off_quality": liquidate_off_quality_positions() if aggressive else 0,
        "news_blocked": liquidate_news_blocked_positions(),
        "outside_obi": liquidate_outside_obi_scope(),
    }


def flatten_all_positions(*, cancel_orders: bool = True, force: bool = False) -> dict[str, int]:
    """
    Close every open Alpaca leg (long + short). Use before sleep / lid-close / pause-all.

    force=True (going-away): cancel HFT rests, re-price stuck sells, marketable exits.
    """
    result = {"orders_cancelled": 0, "closed": 0, "queued": 0, "failed": 0, "still_open": 0}
    try:
        from alpaca_broker import cancel_open_orders, close_position_alpaca, list_positions, pending_close_order

        skip_hft = os.getenv("FLATTEN_SKIP_HFT", "true").lower() in ("1", "true", "yes")
        if force:
            skip_hft = False
        if cancel_orders:
            # going-away: wipe resting buys so shares unlock; keep working sells unless force reprice.
            result["orders_cancelled"] = cancel_open_orders(
                None,
                keep_sells=not force,
                skip_hft=skip_hft,
            )
        for p in list_positions():
            sym = str(p.get("symbol", "")).replace("/", "-").upper()
            if not sym:
                continue
            qty = float(p.get("qty") or 0)
            if qty == 0:
                continue
            if pending_close_order(sym) and not force:
                result["queued"] += 1
                continue
            if close_position_alpaca(sym, force=force):
                result["closed"] += 1
                side = str(p.get("side", "")).lower()
                gain = _position_gain_frac(p)
                log.warning("[PORTFOLIO] flattened %s %s", side or "long", sym)
                if gain is not None:
                    try:
                        from online_learning.trade_feedback import learn_from_realized_trade

                        leg = "SHORT" if side == "short" else "LONG"
                        learn_from_realized_trade(sym, leg, float(gain), source="flatten_all")
                    except Exception:
                        pass
            else:
                result["failed"] += 1
        # Re-count after submits — pending sells count as queued, not failures.
        open_pos = [p for p in list_positions() if abs(float(p.get("qty") or 0)) > 0]
        result["still_open"] = len(open_pos)
        queued_n = 0
        for p in open_pos:
            sym = str(p.get("symbol", "")).replace("/", "-").upper()
            if pending_close_order(sym):
                queued_n += 1
        result["queued"] = max(int(result.get("queued") or 0), queued_n)
        if result["still_open"] and result["queued"] + result["closed"] > 0:
            log.warning(
                "[PORTFOLIO] flatten queued %d close(s); %d position(s) remain until market fill",
                result["queued"],
                result["still_open"],
            )
        if result["still_open"] and result["queued"] >= result["still_open"]:
            log.warning(
                "[PORTFOLIO] all %d position(s) have pending sell orders — do NOT click Liquidate in Alpaca UI "
                "(available qty is 0 until fills at next RTH open)",
                result["still_open"],
            )
    except Exception as e:
        log.warning("[PORTFOLIO] flatten_all failed: %s", e)
    return result


def close_all_short_positions() -> int:
    """Flatten every Alpaca short leg (paper or live). Returns count closed."""
    closed = 0
    try:
        from alpaca_broker import close_position_alpaca, list_positions

        for p in list_positions():
            side = str(p.get("side", "")).lower()
            qty = float(p.get("qty") or 0)
            if side != "short" and qty >= 0:
                continue
            sym = str(p.get("symbol", "")).replace("/", "-").upper()
            if not sym:
                continue
            if close_position_alpaca(sym):
                closed += 1
                log.warning("[FORTRESS] closed SHORT %s", sym)
    except Exception as e:
        log.debug("[FORTRESS] close shorts: %s", e)
    return closed


def sync_risk_manager_from_alpaca(rm: RiskManager) -> dict:
    """
    Refresh equity, buying power, deployed %, and risk legs from live Alpaca book.
    Returns context used for sizing (includes manual positions).
    """
    ctx = {
        "equity": float(rm.equity),
        "buying_power": 0.0,
        "cash": 0.0,
        "deployed_frac": 0.0,
        "position_count": 0,
        "gross_mv": 0.0,
        "multiplier": 0.0,
    }
    try:
        from alpaca_broker import get_account, list_positions
        from alt_assets import is_tradeable_instrument

        acct = get_account()
        if acct:
            ctx["equity"] = float(acct.get("equity") or acct.get("last_equity") or ctx["equity"])
            from alpaca_broker import intraday_buying_power

            ctx["buying_power"] = intraday_buying_power(acct)
            try:
                ctx["cash"] = float(acct.get("cash") or 0.0)
            except (TypeError, ValueError):
                ctx["cash"] = 0.0
            try:
                ctx["multiplier"] = float(acct.get("multiplier") or 0.0)
            except (TypeError, ValueError):
                ctx["multiplier"] = 0.0
            try:
                ctx["daytrading_buying_power"] = float(
                    acct.get("daytrading_buying_power") or acct.get("buying_power") or 0.0
                )
            except (TypeError, ValueError):
                ctx["daytrading_buying_power"] = ctx["buying_power"]
            rm.equity = ctx["equity"]

        rm.legs.clear()
        gross = 0.0
        n = 0
        pos = list_positions() or []
        ctx["positions"] = pos
        for p in pos:
            sym = str(p.get("symbol", "")).replace("/", "-").upper()
            if not sym or not is_tradeable_instrument(sym):
                continue
            qty = float(p.get("qty") or 0)
            if qty <= 0:
                continue
            mv = abs(float(p.get("market_value") or 0))
            entry = float(p.get("avg_entry_price") or 0)
            if mv <= 0 and entry > 0:
                mv = abs(qty) * entry
            gross += mv
            n += 1
            stop = entry * (1.0 - _f("FORTRESS_SYNTHETIC_STOP_PCT", 0.03)) if entry > 0 else entry
            rm.legs[sym] = OpenLeg(symbol=sym, notional=mv, entry=entry or mv, stop=stop)

        ctx["gross_mv"] = gross
        ctx["position_count"] = n
        ctx["deployed_frac"] = gross / max(ctx["equity"], 1e-9)
        try:
            from analytics.buying_power import plan_from_account

            plan = plan_from_account(acct or {}, pos, persist=True)
            ctx["overnight_budget"] = plan.overnight_budget
            ctx["overnight_clip"] = plan.overnight_clip
            ctx["overnight_target"] = plan.overnight_target
            ctx["regt_buying_power"] = plan.regt_buying_power
            log.info(
                "[FORTRESS] portfolio equity=$%.0f cash=$%.0f deployed=%.1f%% gap=$%.0f "
                "clip=$%.0f positions=%d bp=$%.0f dtbp=$%.0f",
                ctx["equity"],
                ctx["cash"],
                100 * ctx["deployed_frac"],
                plan.overnight_gap,
                plan.overnight_clip,
                n,
                ctx["buying_power"],
                ctx.get("daytrading_buying_power") or 0,
            )
        except Exception:
            log.info(
                "[FORTRESS] portfolio equity=$%.0f deployed=%.1f%% positions=%d bp=$%.0f",
                ctx["equity"],
                100 * ctx["deployed_frac"],
                n,
                ctx["buying_power"],
            )
    except Exception as e:
        log.debug("[FORTRESS] portfolio sync: %s", e)
    return ctx


def position_snapshot(ticker: str) -> tuple[float, float | None]:
    """(market_value_usd, unrealized_gain_frac) for ticker; (0, None) if flat."""
    try:
        from alpaca_broker import get_position

        pos = get_position(ticker)
        if not pos or float(pos.get("qty") or 0) <= 0:
            return 0.0, None
        mv = abs(float(pos.get("market_value") or 0))
        px = float(pos.get("current_price") or pos.get("avg_entry_price") or 0)
        uplpc = pos.get("unrealized_plpc")
        if uplpc is not None:
            gain = float(uplpc)
        elif px > 0:
            entry = float(pos.get("avg_entry_price") or 0)
            gain = (px - entry) / entry if entry > 0 else None
        else:
            gain = None
        return mv, gain
    except Exception:
        return 0.0, None


def issuer_position_snapshot(ticker: str) -> tuple[float, float | None]:
    """Same as position_snapshot but sums GOOG+GOOGL (and other dual-class pairs)."""
    try:
        from symbol_aliases import issuer_siblings
    except Exception:
        return position_snapshot(ticker)
    total = 0.0
    gain: float | None = None
    for sib in issuer_siblings(ticker):
        mv, g = position_snapshot(sib)
        if mv > 0:
            total += mv
            if g is not None:
                gain = g if gain is None else max(gain, g)
    return total, gain


def collapse_share_class_duplicates(*, dry_run: bool = False) -> list[dict]:
    """If GOOG and GOOGL (etc.) are both held, sell the smaller listing.

    Keeps the larger market-value class so we do not double the same issuer.
    """
    from alpaca_broker import close_position_alpaca, list_positions
    from symbol_aliases import issuer_group

    by_iss: dict[str, list[dict]] = {}
    for p in list_positions() or []:
        sym = str(p.get("symbol") or "").replace("/", "-").upper()
        qty = float(p.get("qty") or 0)
        if not sym or qty <= 0:
            continue
        by_iss.setdefault(issuer_group(sym), []).append(
            {
                "symbol": sym,
                "qty": qty,
                "mv": abs(float(p.get("market_value") or 0)),
            }
        )
    closed: list[dict] = []
    for iss, legs in by_iss.items():
        if len(legs) < 2:
            continue
        legs.sort(key=lambda r: float(r["mv"]), reverse=True)
        keep = legs[0]
        for drop in legs[1:]:
            row = {**drop, "issuer": iss, "keep": keep["symbol"], "dry_run": dry_run}
            if dry_run:
                closed.append(row)
                continue
            ok = bool(close_position_alpaca(str(drop["symbol"]), force=True))
            row["closed"] = ok
            closed.append(row)
            log.warning(
                "[PORTFOLIO] share-class collapse sell %s keep %s (issuer=%s mv=$%.0f)",
                drop["symbol"],
                keep["symbol"],
                iss,
                float(drop["mv"]),
            )
    return closed


def _truthy(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() in ("1", "true", "yes")


def use_buying_power_sizing() -> bool:
    """Master switch: size available capital off BP / margin capacity (default on)."""
    if not _truthy("USE_BUYING_POWER", "true"):
        return False
    return _truthy("FORTRESS_EXPOSURE_USE_BP", "true")


def gross_capacity_usd(portfolio: dict) -> float:
    """
    Full gross book capacity (not remaining BP).

    Alpaca `buying_power` shrinks as we deploy — never use it as the *total*
    capacity denominator. Risk ceiling is MAX_GROSS_LEVERAGE × equity; account
    multiplier may be higher (e.g. 4×) but we never target past the risk cap.
    """
    equity = max(float(portfolio.get("equity") or 0.0), 1e-9)
    multiplier = float(portfolio.get("multiplier") or 0.0)
    max_lev = max(1.0, _f("MAX_GROSS_LEVERAGE", 4.0))
    if not use_buying_power_sizing():
        return equity
    # Prefer configured risk leverage; clamp account multiplier down to it.
    if multiplier > 1.0:
        mult = min(multiplier, max_lev)
    else:
        mult = max_lev
    return max(equity, equity * mult)


def gross_mv_of(portfolio: dict) -> float:
    equity = max(float(portfolio.get("equity") or 0.0), 1e-9)
    gross_mv = float(portfolio.get("gross_mv") or 0.0)
    if gross_mv <= 0.0:
        positions = portfolio.get("positions") or []
        if isinstance(positions, list) and positions:
            try:
                gross_mv = sum(abs(float(p.get("market_value") or 0)) for p in positions)
            except (TypeError, ValueError):
                gross_mv = 0.0
    if gross_mv <= 0.0:
        gross_mv = float(portfolio.get("deployed_frac") or 0.0) * equity
    return max(0.0, gross_mv)


def equity_single_cap_usd(equity: float) -> float:
    """Hard per-name notional cap — fraction of equity (not 4x BP)."""
    frac = min(
        _f("FORTRESS_MAX_SINGLE_FRAC", 0.10),
        _f("MAX_SINGLE_ASSET_FRAC", 0.12),
    )
    return max(0.0, float(equity) * frac * 0.995)


def idle_cash_fill_active(portfolio: dict | None = None) -> bool:
    """True when equity cash is still sitting idle under the 100% deploy target.

    This is *cash*, not leftover 4× buying power. Fail-open if the snapshot is missing.
    """
    if not _truthy("FORTRESS_FILL_IDLE_CASH", "true"):
        return False
    target = min(_f("FORTRESS_TARGET_DEPLOY_FRAC", 1.0), _f("FORTRESS_MAX_GROSS_FRAC", 1.0))
    slack = _f("FORTRESS_IDLE_FILL_SLACK", 0.03)
    eq = 0.0
    mv = 0.0
    if portfolio:
        try:
            eq = float(portfolio.get("equity") or 0)
            mv = float(portfolio.get("gross_mv") or 0)
            dep = float(portfolio.get("deployed_frac") or 0)
        except (TypeError, ValueError):
            eq, mv, dep = 0.0, 0.0, 0.0
        if eq >= 100.0:
            return (mv / eq) < (target - slack)
        if dep > 0.0:
            return dep < (target - slack)
    return True


def allocate_idle_cash_to_holds(
    leftover: float,
    *,
    positions: list[dict],
    max_single_usd: float,
    min_n: float,
    hard_max: float = 0.0,
    already: dict[str, float] | None = None,
    banned: set[str] | None = None,
    equity: float = 0.0,
) -> dict[str, float]:
    """Put leftover equity-cash into existing longs that still have single-cap room."""
    add: dict[str, float] = {}
    left = max(0.0, float(leftover))
    if left < float(min_n) or max_single_usd <= 0:
        return add
    have = {str(k).upper(): float(v) for k, v in (already or {}).items()}
    ban = {str(s).upper() for s in (banned or set())}
    ranked_pos: list[tuple[str, float]] = []
    for p in positions or []:
        try:
            qty = float(p.get("qty") or 0)
        except (TypeError, ValueError):
            qty = 0.0
        if qty <= 0:
            continue
        # Idle cash goes into winners / flat — never average into a loser.
        try:
            gain = p.get("unrealized_plpc")
            if gain is not None and float(gain) < -1e-9:
                continue
        except (TypeError, ValueError):
            pass
        sym = str(p.get("symbol", "")).replace("/", "-").upper()
        if not sym or sym in ban:
            continue
        try:
            mv = abs(float(p.get("market_value") or 0))
        except (TypeError, ValueError):
            continue
        ranked_pos.append((sym, mv))
    def _crypto_rank(sym: str) -> int:
        try:
            from crypto_universe import is_crypto_symbol

            return 0 if is_crypto_symbol(sym) else 1
        except Exception:
            return 1

    def _cap_for(sym: str) -> float:
        try:
            from crypto_universe import is_crypto_symbol
            from analytics.crypto_alloc import crypto_single_cap_usd

            if is_crypto_symbol(sym) and float(equity or 0) > 0:
                return crypto_single_cap_usd(float(equity))
        except Exception:
            pass
        return float(max_single_usd)

    # Already-sized names first, then crypto (50/50 idle split), then the rest.
    ranked_pos.sort(key=lambda kv: (0 if kv[0] in have else 1, _crypto_rank(kv[0]), -kv[1]))
    for sym, mv in ranked_pos:
        if left < min_n:
            break
        cur = have.get(sym, 0.0) + add.get(sym, 0.0)
        room = max(0.0, _cap_for(sym) - mv - cur)
        if hard_max > 0:
            room = min(room, max(0.0, hard_max - cur))
        if room < min_n:
            continue
        chunk = min(left, room)
        add[sym] = add.get(sym, 0.0) + chunk
        left -= chunk
    return add


def allocate_idle_cash_split(
    leftover: float,
    *,
    positions: list[dict],
    equity: float,
    max_single_usd: float,
    min_n: float,
    hard_max: float = 0.0,
    already: dict[str, float] | None = None,
    banned: set[str] | None = None,
) -> dict[str, float]:
    """50/50 idle split: crypto gap first (holds + new coins), leftover to stock winners."""
    from analytics.crypto_alloc import (
        idle_new_crypto_notionals,
        new_cash_split,
        position_crypto_mv,
    )
    from crypto_universe import is_crypto_symbol

    leftover = max(0.0, float(leftover))
    have = {str(k).upper(): float(v) for k, v in (already or {}).items()}
    crypto_b, stock_b = new_cash_split(
        leftover,
        equity=float(equity or 0.0),
        crypto_mv=position_crypto_mv(positions),
    )
    crypto_pos = [
        p
        for p in (positions or [])
        if is_crypto_symbol(str(p.get("symbol") or ""))
    ]
    extra_c = allocate_idle_cash_to_holds(
        crypto_b,
        positions=crypto_pos,
        max_single_usd=max_single_usd,
        min_n=min_n,
        hard_max=hard_max,
        already=have,
        banned=banned,
        equity=equity,
    )
    have2 = {**have, **extra_c}
    fresh = idle_new_crypto_notionals(
        max(0.0, crypto_b - sum(extra_c.values())),
        equity=float(equity or 0.0),
        positions=positions,
        min_n=min_n,
        hard_max=hard_max,
        already=have2,
    )
    unused_crypto = max(0.0, crypto_b - sum(extra_c.values()) - sum(fresh.values()))
    extra_s = allocate_idle_cash_to_holds(
        stock_b + unused_crypto,
        positions=positions,
        max_single_usd=max_single_usd,
        min_n=min_n,
        hard_max=hard_max,
        already={**have2, **fresh},
        banned=banned,
        equity=equity,
    )
    out: dict[str, float] = {}
    for part in (extra_c, fresh, extra_s):
        for k, v in part.items():
            ku = str(k).upper()
            out[ku] = out.get(ku, 0.0) + float(v)
    return out


def trim_overweight_singles() -> int:
    """Sell down any name above the equity single-name cap (ask-side / sell-high).

    This is the WMT-style bomb: leftover vector sweep + 4× margin budget treated
    10% of buying-power as a legal clip. Does not flatten the book — only excess.
    """
    if os.getenv("FORTRESS_TRIM_OVERWEIGHT", "true").lower() not in ("1", "true", "yes"):
        return 0
    try:
        from analytics.market_session import Session, current_session

        if current_session() != Session.REGULAR:
            return 0
    except Exception:
        pass
    trimmed = 0
    try:
        from alpaca_broker import close_position_alpaca, get_account, list_positions

        acct = get_account() or {}
        equity = float(acct.get("equity") or acct.get("last_equity") or 0.0)
        if equity <= 0:
            return 0
        cap = equity_single_cap_usd(equity)
        pos = list_positions() or []
        # Don't sell-down concentration while 40%+ cash is idle — that is the bleed.
        target = _f("FORTRESS_TARGET_DEPLOY_FRAC", 1.0)
        mv_book = sum(abs(float(p.get("market_value") or 0)) for p in pos)
        deployed = mv_book / equity if equity > 0 else 0.0
        if deployed < target - 0.08:
            log.info(
                "[PORTFOLIO] skip overweight trim — deployed=%.1f%% < target=%.0f%%",
                100 * deployed,
                100 * target,
            )
            return 0
        max_trim_frac = _f("FORTRESS_OVERWEIGHT_TRIM_FRAC", 0.60)  # never dump the whole name at once
        for p in pos:
            qty = float(p.get("qty") or 0)
            if qty <= 0:
                continue
            mv = abs(float(p.get("market_value") or 0))
            if mv <= cap * 1.08:
                continue
            excess = mv - cap
            sell_mv = min(excess, mv * max_trim_frac)
            sell_qty = qty * (sell_mv / mv)
            if sell_qty < 1e-4:
                continue
            sym = str(p.get("symbol", "")).replace("/", "-").upper()
            if close_position_alpaca(sym, qty=sell_qty, head="fortress"):
                trimmed += 1
                log.warning(
                    "[PORTFOLIO] overweight trim %s qty=%.4f (~$%.0f) cap=$%.0f held=$%.0f",
                    sym,
                    sell_qty,
                    sell_mv,
                    cap,
                    mv,
                )
    except Exception as e:
        log.warning("[PORTFOLIO] overweight trim failed: %s", e)
    return trimmed


def deploy_budget_usd(portfolio: dict) -> dict:
    """
    Capital still available for new/add buys under risk caps.

    Overnight: cash/equity gap at 1.0× (see analytics.buying_power). Never the
    leftover 4× PDT number. Per-name cap is a fraction of equity.
    """
    from analytics.buying_power import (
        clip_ceiling_usd,
        equity_single_cap,
        overnight_target_frac,
        plan_from_account,
        sizing_slots,
    )

    equity = float(portfolio.get("equity") or 100_000.0)
    buying_power = float(portfolio.get("buying_power") or equity)
    multiplier = float(portfolio.get("multiplier") or 0.0)
    gross_mv = gross_mv_of(portfolio)
    cash = float(portfolio.get("cash") or 0.0)
    use_bp = use_buying_power_sizing()
    total_capacity = gross_capacity_usd(portfolio)
    use_eq_target = _truthy("FORTRESS_TARGET_DEPLOY_USE_EQUITY", "true")
    target_frac = overnight_target_frac()
    target_base = equity if use_eq_target else (total_capacity if use_bp else equity)
    _acct_plan = {
        "equity": equity,
        "cash": cash if cash > 0 else max(0.0, equity - gross_mv),
        "buying_power": buying_power,
        "daytrading_buying_power": float(portfolio.get("daytrading_buying_power") or buying_power),
        "long_market_value": gross_mv,
    }
    try:
        _regt = float(portfolio.get("regt_buying_power") or 0.0)
    except (TypeError, ValueError):
        _regt = 0.0
    if _regt > 0:
        _acct_plan["regt_buying_power"] = _regt
    plan = plan_from_account(
        _acct_plan,
        portfolio.get("positions") or [],
        persist=False,
    )
    budget = float(plan.overnight_budget)
    max_single = equity_single_cap(equity)
    return {
        "equity": equity,
        "buying_power": buying_power,
        "gross_mv": gross_mv,
        "multiplier": multiplier,
        "total_capacity": total_capacity,
        "target_base": target_base,
        "target_frac": target_frac,
        "target_usd": target_base * target_frac,
        "budget": budget,
        "overnight_target": float(plan.overnight_target),
        "max_single_usd": max_single,
        "overnight_clip": float(plan.overnight_clip),
        "sizing_slots": sizing_slots(),
        "clip_ceiling": clip_ceiling_usd(equity),
        "deployed_frac_equity": gross_mv / max(equity, 1e-9),
        "deployed_frac_capacity": gross_mv / max(total_capacity, 1e-9),
        "use_eq_target": use_eq_target,
        "use_bp": use_bp,
    }


def fortress_order_notional(
    *,
    ticker: str,
    p_adj: float,
    scale: float,
    portfolio: dict,
    existing_mv: float,
    existing_gain: float | None,
) -> float:
    """
    Size orders to keep most of the book in stocks:
    - slot budget from target deploy % / max names
    - boost when under-invested
    - add on dips (DCA)
  """
    equity = float(portfolio.get("equity") or 100_000.0)
    buying_power = float(portfolio.get("buying_power") or equity)
    use_bp = use_buying_power_sizing()
    # Total intraday deployable capital = equity × margin (~4×). Remaining BP only
    # bounds each order — never the whole-book target (see gross_capacity_usd).
    total_capacity = gross_capacity_usd(portfolio)
    gross_mv = gross_mv_of(portfolio)
    use_eq_target = _truthy("FORTRESS_TARGET_DEPLOY_USE_EQUITY", "true")
    max_gross_frac = min(
        1.0,
        _f("FORTRESS_MAX_GROSS_FRAC", _f("HF_MAX_GROSS_FRAC", 1.0)),
    )
    target_base = equity if use_eq_target else (total_capacity if use_bp else equity)
    # Reg T can hold up to 2× equity. The 4× intraday figure stays with same-day HFT.
    try:
        _ovn_target = float(portfolio.get("overnight_target") or 0.0)
    except (TypeError, ValueError):
        _ovn_target = 0.0
    if _ovn_target > equity * 1.01:
        target_base = min(_ovn_target, equity * 2.0)
    cap_base = total_capacity if use_bp else equity
    deployed = gross_mv / max(target_base, 1e-9)

    from analytics.buying_power import (
        clip_ceiling_usd,
        fortress_ticket_usd,
        order_hard_max_usd,
        sizing_slots,
    )

    target_deploy = min(_f("FORTRESS_TARGET_DEPLOY_FRAC", 1.0), max_gross_frac)
    max_names = sizing_slots()
    floor = _f("MIN_ORDER_NOTIONAL", 100.0)
    ceil = clip_ceiling_usd(equity)
    # HARD_MAX=0 / ORDER_NOTIONAL=0 → equity single-cap, never a $2,500 crumb.
    # Skip policy_agent ORDER_NOTIONAL here so AGI cannot re-spray leftover cash.
    try:
        base = float(os.getenv("ORDER_NOTIONAL") or 0)
    except (TypeError, ValueError):
        base = 0.0
    if order_hard_max_usd() <= 0 or base <= 0:
        base = ceil if ceil > 0 else max(floor, equity * 0.08)

    slot = target_base * target_deploy / max_names
    # Conviction curve: high confidence → near single-name cap; weak/risky → small probe.
    risk_p = 0.0
    try:
        from intel.downward_pressure import exit_adjustments

        risk_p = float(exit_adjustments(ticker).get("pressure_score") or 0.0)
    except Exception:
        pass
    try:
        from analytics.conviction_exit import conviction_size_mult

        conf_mult = conviction_size_mult(
            float(p_adj),
            exec_conf=float(portfolio.get("last_exec_conf") or 0.55),
            risk_pressure=risk_p,
            force_priority=bool(portfolio.get("force_priority")),
        )
    except Exception:
        lo = _f("FORTRESS_NOTIONAL_MIN_MULT", 0.9)
        hi = _f("FORTRESS_NOTIONAL_MAX_MULT", 1.5)
        conf_mult = lo + (hi - lo) * max(0.0, min(1.0, (float(p_adj) - 0.5) / 0.5))

    # Max-equity overlay — high conviction + calm risk → push toward caps
    try:
        from analytics.catalyst_horizon import max_equity_size_mult

        conf_mult *= max_equity_size_mult(
            p_adj=float(p_adj),
            exec_conf=float(portfolio.get("last_exec_conf") or 0.55),
            risk_pressure=risk_p,
            force_priority=bool(portfolio.get("force_priority")),
            catalyst_fit=float(portfolio.get("catalyst_horizon_fit") or 1.0),
        )
    except Exception:
        pass

    # Slot-first for new names — when under-deployed, fill slots up to target (not ORDER_NOTIONAL floor).
    if existing_mv <= 0:
        n = slot * conf_mult * max(scale, 0.0)
        if deployed >= target_deploy - 0.03:
            n = min(n, base)
        else:
            n = min(n, max(base, slot))
    else:
        n = max(base, slot) * conf_mult * max(scale, 0.0)
    go_live_cap = ceil
    if go_live_cap > 0:
        n = min(n, go_live_cap)

    try:
        from fortress_universe import is_top100_equity

        if is_top100_equity(ticker):
            n *= float(os.getenv("TOP100_NOTIONAL_MULT", "1.35"))
    except Exception:
        pass

    if deployed < target_deploy - 0.03:
        gap = target_deploy - deployed
        n *= 1.0 + min(_f("FORTRESS_UNDERDEPLOY_BOOST_CAP", 2.5), gap * _f("FORTRESS_UNDERDEPLOY_BOOST", 5.0))

    # Single-name hard cap always vs equity when configured (matches execute path).
    max_single = (
        equity_single_cap_usd(equity)
        if _truthy("FORTRESS_SINGLE_CAP_USE_EQUITY", "true")
        else cap_base * _f("FORTRESS_MAX_SINGLE_FRAC", 0.09)
    )

    allow_dca = _truthy("FORTRESS_ALLOW_DCA", "false")
    min_dip = _f("FORTRESS_DCA_MIN_DIP", 0.002)
    if allow_dca and existing_mv > 0 and existing_gain is not None and existing_gain < -min_dip:
        dip = abs(existing_gain)
        dca_mult = min(_f("FORTRESS_DCA_MAX_MULT", 2.2), 1.0 + dip * _f("FORTRESS_DCA_DIP_SENS", 80.0))
        room = max(0.0, max_single - existing_mv)
        n = min(room, n * dca_mult) if room > floor else 0.0
        log.info(
            "[FORTRESS] DCA %s dip=%.2f%% add $%.0f (held $%.0f)",
            ticker,
            100 * dip,
            n,
            existing_mv,
        )
    elif existing_mv > 0:
        room = max(0.0, max_single - existing_mv)
        n = min(n, room)

    n = min(n, max_single if existing_mv <= 0 else max(0.0, max_single - existing_mv))
    cash_room = float(portfolio.get("cash") or 0.0)
    if cash_room <= 1.0:
        cash_room = max(0.0, equity - gross_mv)
    try:
        _regt_room = float(portfolio.get("regt_buying_power") or 0.0)
    except (TypeError, ValueError):
        _regt_room = 0.0
    # Cash alone left Reg T idle. Still never spend the 4× intraday number here.
    if _regt_room > cash_room:
        cash_room = _regt_room
    n = min(n, cash_room * _f("FORTRESS_BP_USE_FRAC", 1.0))
    # Strong JP candle + under-deploy → use more of the book
    jp_mult = float(os.getenv("FORTRESS_JP_NOTIONAL_MULT", "1.0"))
    if jp_mult > 1.0 and deployed < target_deploy - 0.05:
        n *= jp_mult

    # Gross room vs capacity target (or equity when equity-target on).
    room_total = max(0.0, target_base * target_deploy - gross_mv)
    if use_bp and not use_eq_target:
        room_total = max(0.0, cap_base * max_gross_frac - gross_mv)
    if existing_mv <= 0:
        # Fill idle overnight cash — calculator ticket is a FLOOR, not min() with a
        # $144 slot crumb. `or n` used to keep the tiny n when ticket was 0.
        ticket = fortress_ticket_usd(
            equity=equity,
            existing_mv=0.0,
            leftover_budget=room_total,
        )
        if ticket > 0:
            n = min(max(n, ticket), room_total, ceil if ceil > 0 else ticket)
        else:
            n = min(n, room_total)
    else:
        n = min(n, room_total, max(0.0, max_single - existing_mv))

    return max(floor, n) if n >= floor else 0.0


def can_add_position(
    rm: RiskManager,
    symbol: str,
    notional: float,
    entry: float,
    stop: float,
    existing_mv: float,
) -> bool:
    """New leg vs add-on to an existing holding."""
    if notional <= 0:
        return False
    if existing_mv <= 0:
        return rm.can_open(symbol, notional, entry, stop)
    gain = None
    try:
        from alpaca_broker import get_position

        pos = get_position(symbol)
        if pos:
            gain = _position_gain_frac(pos)
    except Exception:
        gain = None
    try:
        from analytics.buying_power import hold_is_green

        if not hold_is_green(gain):
            return False
    except Exception:
        if gain is not None and gain < -1e-9:
            return False
    if not _truthy("FORTRESS_ALLOW_ADD_ON", "true"):
        # Idle cash may add to winners / crypto. Never average into a red name.
        port = {
            "equity": max(float(getattr(rm, "equity", 0) or 0), 1e-9),
            "gross_mv": 0.0,
        }
        try:
            port["gross_mv"] = float(rm.total_gross_exposure())
        except Exception:
            port["gross_mv"] = float(existing_mv)
        if not idle_cash_fill_active(port):
            return False
    try:
        from intel.downward_pressure import blocks_new_buy

        blocked, _why = blocks_new_buy(symbol)
        if blocked:
            return False
    except Exception:
        pass
    equity = max(rm.equity, 1e-9)
    max_single = equity_single_cap_usd(equity)
    crypto_cap = False
    try:
        from crypto_universe import is_crypto_symbol
        from analytics.crypto_alloc import crypto_single_cap_usd

        if is_crypto_symbol(symbol):
            max_single = crypto_single_cap_usd(equity)
            crypto_cap = True
    except Exception:
        pass
    if (
        not crypto_cap
        and not _truthy("FORTRESS_SINGLE_CAP_USE_EQUITY", "true")
        and use_buying_power_sizing()
    ):
        try:
            cap_base = gross_capacity_usd(
                {
                    "equity": equity,
                    "buying_power": equity,
                    "multiplier": _f("MAX_GROSS_LEVERAGE", 4.0),
                    "gross_mv": rm.total_gross_exposure(),
                }
            )
            max_single = cap_base * _f("FORTRESS_MAX_SINGLE_FRAC", 0.09)
        except Exception:
            pass
    if existing_mv + notional > max_single * 1.001:
        return False
    # Total deploy gate vs capacity target (4×) + remaining BP budget.
    bud = deploy_budget_usd(
        {
            "equity": equity,
            "buying_power": equity,
            "gross_mv": rm.total_gross_exposure(),
            "deployed_frac": rm.total_gross_exposure() / max(equity, 1e-9),
            "multiplier": _f("MAX_GROSS_LEVERAGE", 4.0),
        }
    )
    try:
        from alpaca_broker import get_account, intraday_buying_power

        acct = get_account() or {}
        bud = deploy_budget_usd(
            {
                "equity": float(acct.get("equity") or equity),
                "buying_power": float(intraday_buying_power(acct)),
                "gross_mv": rm.total_gross_exposure(),
                "multiplier": float(acct.get("multiplier") or 0.0),
            }
        )
    except Exception:
        pass
    # Refuse only when over capacity target *and* no BP room (not equity-only idle cash).
    deployed_vs_target = bud["gross_mv"] / max(bud["target_usd"], 1e-9)
    if notional > bud["budget"] + 1.0 and deployed_vs_target >= 0.99:
        return False
    return True
