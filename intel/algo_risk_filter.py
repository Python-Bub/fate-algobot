"""Context-aware pre-trade risk filter — earnings, M&A, sector sympathy, stabilization."""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ROOT / "data" / "algo_risk_config.json"

MA_KEYWORDS = (
    "merger agreement",
    "definitive agreement",
    "to be acquired",
    "acquisition of",
    "all-cash offer",
    "buyout",
    "go-private",
)


@lru_cache(maxsize=1)
def _load_config() -> dict[str, Any]:
    path = Path(os.getenv("ALGO_RISK_CONFIG_PATH", str(DEFAULT_CONFIG_PATH)))
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _today(as_of: date | datetime | None = None) -> date:
    if as_of is None:
        return datetime.now(timezone.utc).date()
    if isinstance(as_of, datetime):
        return as_of.date()
    return as_of


def _enabled() -> bool:
    """Always on unless emergency bypass (same flag as stack-wide panic controls)."""
    return os.getenv("EMERGENCY_BYPASS_ALGO_RISK", "false").lower() not in ("1", "true", "yes")


def earnings_buffer_days() -> int:
    return int(os.getenv("ALGO_RISK_EARNINGS_BUFFER_DAYS", "5"))


def sympathy_buffer_days() -> float:
    return float(os.getenv("ALGO_RISK_SYMPATHY_BUFFER_DAYS", "2"))


def sympathy_warn_days() -> int:
    """Peer earnings window that triggers APPROVED+WARNING (restrict hold), not hard block."""
    return int(os.getenv("ALGO_RISK_SYMPATHY_WARN_DAYS", os.getenv("ALGO_RISK_EARNINGS_BUFFER_DAYS", "5")))


def check_insider_sell_risk(symbol: str) -> tuple[bool, str, dict[str, Any]]:
    """Block or warn when C-suite / material insider selling is recent."""
    if os.getenv("ENABLE_INSIDER_PROXY", "true").lower() not in ("1", "true", "yes"):
        return False, "Insider proxy disabled.", {}
    try:
        from intel.insider_signals import assess_insider_flow

        flow = assess_insider_flow(symbol)
        meta = {
            "factor": flow.get("factor"),
            "c_suite_sell_shares": flow.get("c_suite_sell_shares"),
            "recent_sell_shares": flow.get("recent_sell_shares"),
            "events": (flow.get("events") or [])[:4],
        }
        if flow.get("block_long"):
            return True, str(flow.get("block_reason") or "Recent C-suite insider selling."), meta
        return False, "No blocking insider sell pattern.", meta
    except Exception as e:
        return False, f"Insider check skipped: {e}", {}


def check_earnings_defensive_risk(
    symbol: str,
    *,
    documents: list[str] | None = None,
    as_of: date | None = None,
) -> tuple[bool, str, dict[str, Any]]:
    """Block when management uses defensive language ahead of earnings."""
    if os.getenv("USE_EARNINGS_DEFENSIVE", "true").lower() not in ("1", "true", "yes"):
        return False, "Earnings defensive scan disabled.", {}
    try:
        from intel.earnings_defensive_signals import assess_pre_earnings_defensive

        res = assess_pre_earnings_defensive(symbol, documents=documents, as_of=as_of)
        meta = {
            "active": res.get("active"),
            "intensity": res.get("intensity"),
            "hits": res.get("hits"),
            "days_to_earnings": res.get("days_to_earnings"),
        }
        if res.get("block_long"):
            return True, str(res.get("block_reason") or "Defensive pre-earnings language."), meta
        return False, "No defensive pre-earnings language.", meta
    except Exception as e:
        return False, f"Earnings defensive check skipped: {e}", {}


def check_category_decision(
    symbol: str,
    *,
    macro_bundle: dict[str, Any] | None = None,
    news_headlines: list[str] | None = None,
    row: dict[str, Any] | None = None,
) -> tuple[bool, str, dict[str, Any]]:
    """Hard block when category taxonomy spec rejects a buy (trial failure, rate shock, etc.)."""
    if os.getenv("USE_CATEGORY_DECISION", "true").lower() not in ("1", "true", "yes"):
        return False, "Category decision disabled.", {}
    try:
        from analytics.industries.category_decision import evaluate_category_decision

        cd = evaluate_category_decision(symbol, row, macro_bundle, news_headlines)
        meta = cd.to_dict()
        if cd.block_buy:
            return True, str(cd.block_reason or "Category spec blocked buy."), meta
        return False, "Category decision passed.", meta
    except Exception as e:
        return False, f"Category decision skipped: {e}", {}


def check_industry_pipeline(
    symbol: str,
    *,
    macro_bundle: dict[str, Any] | None = None,
    news_headlines: list[str] | None = None,
) -> tuple[bool, str, dict[str, Any]]:
    """Hard block when specialized industry pipeline rejects a long entry."""
    if os.getenv("USE_INDUSTRY_PIPELINE", "true").lower() not in ("1", "true", "yes"):
        return False, "Industry pipeline disabled.", {}
    try:
        from analytics.industries.pipeline import run_industry_pipeline

        pipe = run_industry_pipeline(
            symbol,
            macro_bundle=macro_bundle,
            news_headlines=news_headlines,
        )
        meta = {
            "industry_id": pipe.get("industry_id"),
            "pipeline_notes": (pipe.get("pipeline_notes") or [])[:6],
            "macro_gates": pipe.get("macro_gates") or [],
        }
        if pipe.get("block_long"):
            reason = str(pipe.get("block_reason") or "Industry pipeline blocked long entry.")
            return True, reason, meta
        return False, "Industry pipeline passed.", meta
    except Exception as e:
        return False, f"Industry pipeline skipped: {e}", {}


def sympathy_trap_take_profit_pct() -> float:
    return float(os.getenv("SYMPATHY_TRAP_TP_PCT", "0.03"))


def stabilization_sessions() -> int:
    return int(os.getenv("ALGO_RISK_STABILIZATION_SESSIONS", "3"))


def stabilization_range_pct() -> float:
    return float(os.getenv("ALGO_RISK_STABILIZATION_RANGE_PCT", "0.02"))


def weekly_drop_trigger_pct() -> float:
    return float(os.getenv("ALGO_RISK_WEEKLY_DROP_TRIGGER_PCT", "0.15"))


def _next_earnings_date(symbol: str, *, as_of: date | None = None) -> tuple[date | None, int | None]:
    """Return (next_earnings_date, days_until) from multi-source earnings calendar."""
    try:
        from intel.earnings_calendar import days_to_next_earnings

        return days_to_next_earnings(symbol, as_of=as_of)
    except Exception:
        pass
    sym = symbol.strip().upper()
    today = _today(as_of)
    try:
        import yfinance as yf

        tk = yf.Ticker(sym)
    except Exception:
        return None, None

    candidates: list[date] = []

    try:
        cal = tk.get_calendar()
        if cal and "Earnings Date" in cal:
            raw = cal["Earnings Date"]
            items = raw if isinstance(raw, (list, tuple)) else [raw]
            for item in items:
                if item is None:
                    continue
                if isinstance(item, datetime):
                    candidates.append(item.date())
                elif isinstance(item, date):
                    candidates.append(item)
                else:
                    candidates.append(datetime.fromisoformat(str(item)[:10]).date())
    except Exception:
        pass

    future = sorted({d for d in candidates if d >= today})
    if not future:
        return None, None
    nxt = future[0]
    return nxt, (nxt - today).days


def pd_date_to_date(val: Any) -> date:
    try:
        import pandas as pd

        return pd.Timestamp(val).date()
    except Exception:
        return datetime.fromisoformat(str(val)[:10]).date()


def check_earnings_conflict(
    symbol: str,
    *,
    buffer_days: int | None = None,
    as_of: date | None = None,
) -> tuple[bool, str, dict[str, Any]]:
    buf = earnings_buffer_days() if buffer_days is None else buffer_days
    nxt, days = _next_earnings_date(symbol, as_of=as_of)
    meta = {"next_earnings": nxt.isoformat() if nxt else None, "days_to_earnings": days}
    if days is None:
        return False, "No earnings calendar found (ETF/fund or data unavailable).", meta
    if 0 <= days <= buf:
        return (
            True,
            f"Earnings in {days} day(s) (buffer={buf}d) — binary event risk.",
            meta,
        )
    return False, f"Earnings clear ({days}d away, buffer={buf}d).", meta


def _registry_ma_locked(symbol: str) -> tuple[bool, str]:
    sym = symbol.strip().upper()
    try:
        from universe_lifecycle.corporate_actions import load_registry

        reg = load_registry()
        for ev in reg.get("events") or []:
            kind = str(ev.get("kind", "")).lower()
            if kind not in ("merge", "merger", "acquisition", "buyout"):
                continue
            target = str(ev.get("old") or ev.get("symbol") or "").upper()
            if target == sym:
                note = str(ev.get("note") or kind)
                return True, f"Corporate registry M&A lock: {note}"
    except Exception:
        pass
    return False, ""


def _config_ma_locked(symbol: str) -> tuple[bool, str]:
    sym = symbol.strip().upper()
    cfg = _load_config()
    pending = (cfg.get("pending_acquisitions") or {}).get(sym)
    if not pending:
        return False, ""
    status = str(pending.get("status", "pending")).lower()
    if status in ("definitive", "pending", "announced", "binding"):
        acq = pending.get("acquirer") or "acquirer"
        price = pending.get("offer_price")
        note = pending.get("note") or "pending acquisition"
        detail = f"{acq} offer"
        if price is not None:
            detail += f" @ ${float(price):.2f}"
        return True, f"M&A dead money ({detail}): {note}"
    return False, ""


def _alpaca_ma_locked(symbol: str) -> tuple[bool, str]:
    if os.getenv("ALGO_RISK_ALPACA_MA", "true").lower() not in ("1", "true", "yes"):
        return False, ""
    k = os.getenv("ALPACA_API_KEY", "").strip()
    s = os.getenv("ALPACA_SECRET_KEY", "").strip()
    if not k or not s:
        return False, ""
    try:
        from alpaca.trading.client import TradingClient
        from alpaca.trading.enums import CorporateActionType
        from alpaca.trading.requests import GetCorporateActionsRequest
    except ImportError:
        return False, ""

    sym = symbol.strip().upper()
    today = _today()
    try:
        paper = os.getenv("ALPACA_PAPER", "true").lower() in ("1", "true", "yes")
        client = TradingClient(k, s, paper=paper)
        req = GetCorporateActionsRequest(
            ca_types=[CorporateActionType.MERGER, CorporateActionType.SPINOFF],
            since=today - timedelta(days=30),
            until=today + timedelta(days=30),
            symbol=sym,
        )
        announcements = client.get_corporate_actions(req)
        if announcements:
            ca_type = getattr(announcements[0], "ca_type", "MERGER")
            return True, f"Alpaca corporate action: {ca_type}"
    except Exception:
        pass
    return False, ""


def check_ma_status(symbol: str) -> tuple[bool, str]:
    """True = blocked (locked in M&A / acquisition cap)."""
    for fn in (_config_ma_locked, _registry_ma_locked, _alpaca_ma_locked):
        locked, reason = fn(symbol)
        if locked:
            return True, reason
    return False, "No active M&A lock."


def _cluster_for(symbol: str) -> tuple[str | None, list[str], list[str]]:
    sym = symbol.strip().upper()
    cfg = _load_config()
    clusters = cfg.get("sector_clusters") or {}
    leaders = cfg.get("cluster_leaders") or {}
    for name, members in clusters.items():
        group = [str(m).upper() for m in members]
        if sym in group:
            lead = [str(m).upper() for m in (leaders.get(name) or []) if str(m).upper() in group]
            peers = [m for m in group if m != sym]
            return str(name), peers, lead or peers[:3]
    return None, [], []


def check_sector_sympathy(
    symbol: str,
    *,
    sympathy_days: float | None = None,
    as_of: date | None = None,
) -> tuple[bool, str, dict[str, Any]]:
    """Block when a cluster leader has earnings within sympathy window."""
    sym = symbol.strip().upper()
    cluster, _peers, leaders = _cluster_for(sym)
    meta: dict[str, Any] = {"cluster": cluster, "leaders_checked": leaders}
    if not cluster or not leaders:
        return False, "No sector cluster / sympathy rule.", meta

    buf = sympathy_buffer_days() if sympathy_days is None else sympathy_days
    for leader in leaders:
        if leader == sym:
            continue
        conflict, reason, em = check_earnings_conflict(leader, buffer_days=int(buf), as_of=as_of)
        meta[f"leader_{leader}"] = em
        if conflict:
            days = em.get("days_to_earnings")
            return (
                True,
                f"Sector sympathy ({cluster}): {leader} earnings in {days}d — delay {sym} entry.",
                meta,
            )
    return False, f"Cluster {cluster} leaders clear of {buf}d earnings window.", meta


def _sympathy_peers(symbol: str) -> list[str]:
    sym = symbol.strip().upper()
    cfg = _load_config()
    explicit = [str(p).upper() for p in (cfg.get("sympathy_map") or {}).get(sym) or []]
    if explicit:
        return [p for p in explicit if p != sym]
    _cluster, peers, leaders = _cluster_for(sym)
    out: list[str] = []
    for p in leaders + peers:
        if p and p != sym and p not in out:
            out.append(p)
    return out


def check_sympathy_peer_warnings(
    symbol: str,
    *,
    warn_days: int | None = None,
    as_of: date | None = None,
) -> tuple[bool, str, dict[str, Any]]:
    """Warn (do not block) when mapped peers are inside the earnings buffer window."""
    sym = symbol.strip().upper()
    peers = _sympathy_peers(sym)
    buf = sympathy_warn_days() if warn_days is None else warn_days
    meta: dict[str, Any] = {"peers_checked": peers, "warn_buffer_days": buf}
    if not peers:
        return False, "No sympathy peers configured.", meta

    worst_peer = None
    worst_days: int | None = None
    worst_date: date | None = None
    for peer in peers:
        conflict, reason, em = check_earnings_conflict(peer, buffer_days=buf, as_of=as_of)
        meta[f"peer_{peer}"] = {"conflict": conflict, "reason": reason, **em}
        days = em.get("days_to_earnings")
        if conflict and days is not None and (worst_days is None or days < worst_days):
            worst_peer = peer
            worst_days = int(days)
            nxt_s = em.get("next_earnings")
            if nxt_s:
                try:
                    worst_date = date.fromisoformat(str(nxt_s)[:10])
                except Exception:
                    worst_date = None

    if worst_peer is None or worst_days is None:
        return False, f"Sympathy peers clear of {buf}d earnings warn window.", meta

    max_hold = max(1, worst_days - 1)
    tp = sympathy_trap_take_profit_pct()
    force_exit = worst_date.isoformat() if worst_date else None
    meta.update(
        {
            "sympathy_peer": worst_peer,
            "peer_days_to_earnings": worst_days,
            "max_hold_days": max_hold,
            "take_profit_pct": tp,
            "force_exit_before_date": force_exit,
            "restrict_trade_length": True,
        }
    )
    return (
        True,
        f"⚠️ WARNING: {sym} APPROVED but peer {worst_peer} earnings in {worst_days}d — "
        f"restrict hold to {max_hold}d / {tp * 100:.1f}% TP / exit before peer reports.",
        meta,
    )


def check_panic_drop_limit_entry(symbol: str) -> tuple[bool, str, dict[str, Any]]:
    """After a sharp weekly drop, prefer limit band entry vs blind market open."""
    sym = symbol.strip().upper()
    cfg = _load_config()
    custom = (cfg.get("panic_limit_entries") or {}).get(sym) or {}
    trigger = float(custom.get("weekly_drop_pct", os.getenv("ALGO_RISK_PANIC_LIMIT_WEEKLY_PCT", "10"))) / 100.0
    daily_trigger = float(custom.get("daily_drop_pct", 0.0)) / 100.0

    hist = _daily_history(sym, sessions=12)
    meta: dict[str, Any] = {"weekly_drop_pct": None, "daily_drop_pct": None, "use_limit_entry": False}
    if hist is None or len(hist) < 7:
        return False, "Insufficient history for panic limit check.", meta

    try:
        closes = hist["Close"].astype(float)
        weekly_ret = float(closes.iloc[-2] / closes.iloc[-7] - 1.0) if len(closes) >= 7 else 0.0
        daily_ret = float(closes.iloc[-2] / closes.iloc[-3] - 1.0) if len(closes) >= 3 else 0.0
        meta["weekly_drop_pct"] = round(weekly_ret * 100.0, 2)
        meta["daily_drop_pct"] = round(daily_ret * 100.0, 2)
        last_close = float(closes.iloc[-2])
        meta["last_close"] = round(last_close, 2)

        panic = weekly_ret <= -trigger
        if daily_trigger > 0 and daily_ret <= -daily_trigger:
            panic = True

        if not panic:
            return (
                False,
                f"Weekly {weekly_ret * 100:.1f}% / daily {daily_ret * 100:.1f}% — no panic limit entry.",
                meta,
            )

        lo = float(custom.get("limit_low") or 0.0)
        hi = float(custom.get("limit_high") or 0.0)
        if lo <= 0 or hi <= 0 or hi < lo:
            recent_low = float(hist["Low"].astype(float).tail(10).min())
            band = float(os.getenv("ALGO_RISK_PANIC_LIMIT_BAND_PCT", "0.04"))
            lo = recent_low * (1.0 - band * 0.25)
            hi = recent_low * (1.0 + band * 0.75)
        mode = (os.getenv("ALGO_RISK_LIMIT_ENTRY_MODE", "mid") or "mid").lower()
        if mode == "low":
            target = lo
        elif mode == "high":
            target = hi
        else:
            target = (lo + hi) / 2.0

        meta.update(
            {
                "use_limit_entry": True,
                "limit_low": round(lo, 2),
                "limit_high": round(hi, 2),
                "limit_price": round(target, 2),
                "entry_order_type": "limit",
                "note": custom.get("note") or "Panic drop — limit band vs market open",
            }
        )
        return (
            True,
            f"Panic drop {weekly_ret * 100:.1f}% — use LIMIT ${lo:.2f}-${hi:.2f} (target ${target:.2f}), not market open.",
            meta,
        )
    except Exception as e:
        return False, f"Panic limit check skipped: {e}", meta


def build_trade_constraints_from_risk(risk: dict[str, Any]) -> dict[str, Any]:
    """Flatten screen_buy_risk warnings into persisted execution constraints."""
    out: dict[str, Any] = {"symbol": risk.get("ticker")}
    warn = risk.get("sympathy_warning") or {}
    if warn.get("restrict_trade_length"):
        out.update(
            {
                "sympathy_peer": warn.get("sympathy_peer"),
                "peer_days_to_earnings": warn.get("peer_days_to_earnings"),
                "max_hold_days": warn.get("max_hold_days"),
                "take_profit_pct": warn.get("take_profit_pct"),
                "force_exit_before_date": warn.get("force_exit_before_date"),
                "sympathy_trap": True,
            }
        )
    entry = risk.get("entry_execution") or {}
    if entry.get("use_limit_entry"):
        out.update(
            {
                "entry_order_type": "limit",
                "limit_low": entry.get("limit_low"),
                "limit_high": entry.get("limit_high"),
                "limit_price": entry.get("limit_price"),
                "panic_drop_pct": entry.get("weekly_drop_pct"),
            }
        )
    else:
        out.setdefault("entry_order_type", "market")
    return out


def _daily_history(symbol: str, sessions: int = 10):
    try:
        from data_platform.market_prices import fetch_period

        df = fetch_period(symbol.strip().upper(), period="1mo", interval="1d")
        if df is None or df.empty:
            return None
        return df.tail(max(sessions + 2, 8))
    except Exception:
        return None


def check_stabilization(
    symbol: str,
    *,
    weekly_drop_pct: float | None = None,
    range_pct: float | None = None,
    sessions: int | None = None,
) -> tuple[bool, str, dict[str, Any]]:
    """After a large weekly drop, require N sessions in a tight range before buying."""
    trigger = weekly_drop_trigger_pct() if weekly_drop_pct is None else weekly_drop_pct
    tight = stabilization_range_pct() if range_pct is None else range_pct
    n_sess = stabilization_sessions() if sessions is None else sessions

    hist = _daily_history(symbol, sessions=n_sess + 5)
    meta: dict[str, Any] = {"weekly_drop_pct": None, "stabilized": False, "sessions_checked": n_sess}
    if hist is None or len(hist) < n_sess + 2:
        return False, "Insufficient price history for stabilization check.", meta

    try:
        closes = hist["Close"].astype(float)
        weekly_ret = float(closes.iloc[-2] / closes.iloc[-7] - 1.0) if len(closes) >= 7 else 0.0
        meta["weekly_drop_pct"] = round(weekly_ret * 100.0, 2)
        if weekly_ret > -trigger:
            return False, f"Weekly move {weekly_ret*100:.1f}% — stabilization rule not triggered.", meta

        recent = hist.iloc[-(n_sess + 1) : -1]
        if len(recent) < n_sess:
            return False, "Not enough recent sessions for stabilization.", meta

        ranges: list[float] = []
        for _, row in recent.iterrows():
            hi = float(row["High"])
            lo = float(row["Low"])
            mid = float(row["Close"]) or (hi + lo) / 2.0
            if mid <= 0:
                continue
            ranges.append((hi - lo) / mid)

        meta["session_ranges_pct"] = [round(r * 100, 3) for r in ranges]
        if len(ranges) < n_sess:
            return False, "Could not compute session ranges.", meta

        stabilized = all(r <= tight for r in ranges[-n_sess:])
        meta["stabilized"] = stabilized
        if not stabilized:
            return (
                True,
                f"Large weekly drop ({weekly_ret*100:.1f}%) — need {n_sess} sessions within "
                f"{tight*100:.1f}% daily range before entry.",
                meta,
            )
        return False, f"Post-drop stabilization confirmed ({n_sess} tight sessions).", meta
    except Exception as e:
        return False, f"Stabilization check skipped: {e}", meta


class AlgoRiskFilter:
    """Pre-trade contextual gatekeeper."""

    def __init__(
        self,
        *,
        buffer_days: int | None = None,
        sympathy_days: float | None = None,
        as_of: date | None = None,
    ):
        self.buffer_days = buffer_days
        self.sympathy_days = sympathy_days
        self.as_of = as_of

    def screen_ticker(self, symbol: str, *, hold_days: int = 5) -> dict[str, Any]:
        sym = symbol.strip().upper()
        if not _enabled():
            return {
                "ticker": sym,
                "approved": True,
                "reason": "Algo risk filter bypassed (EMERGENCY_BYPASS_ALGO_RISK=true).",
                "rule": None,
                "hold_days": hold_days,
            }

        checks: list[tuple[str, bool, str, dict[str, Any]]] = []

        ma_block, ma_reason = check_ma_status(sym)
        checks.append(("ma_lock", ma_block, ma_reason, {}))

        earn_block, earn_reason, earn_meta = check_earnings_conflict(
            sym, buffer_days=self.buffer_days, as_of=self.as_of
        )
        checks.append(("earnings_buffer", earn_block, earn_reason, earn_meta))

        sym_block, sym_reason, sym_meta = check_sector_sympathy(
            sym, sympathy_days=self.sympathy_days, as_of=self.as_of
        )
        checks.append(("sector_sympathy", sym_block, sym_reason, sym_meta))

        ind_block, ind_reason, ind_meta = check_industry_pipeline(sym)
        checks.append(("industry_pipeline", ind_block, ind_reason, ind_meta))

        cat_block, cat_reason, cat_meta = check_category_decision(sym)
        checks.append(("category_decision", cat_block, cat_reason, cat_meta))

        ins_block, ins_reason, ins_meta = check_insider_sell_risk(sym)
        checks.append(("insider_sell", ins_block, ins_reason, ins_meta))

        def_block, def_reason, def_meta = check_earnings_defensive_risk(sym, as_of=self.as_of)
        checks.append(("earnings_defensive", def_block, def_reason, def_meta))

        stab_block, stab_reason, stab_meta = check_stabilization(sym)
        checks.append(("volatility_stabilization", stab_block, stab_reason, stab_meta))

        for rule, blocked, reason, meta in checks:
            if blocked:
                return {
                    "ticker": sym,
                    "approved": False,
                    "reason": reason,
                    "rule": rule,
                    "hold_days": hold_days,
                    "days_to_earnings": earn_meta.get("days_to_earnings"),
                    "details": {rule: meta for _, _, _, meta in checks if meta},
                    "checks": [
                        {"rule": r, "blocked": b, "reason": rs}
                        for r, b, rs, _ in checks
                    ],
                }

        warn_active, warn_reason, warn_meta = check_sympathy_peer_warnings(sym, as_of=self.as_of)
        panic_active, panic_reason, panic_meta = check_panic_drop_limit_entry(sym)
        effective_hold = hold_days
        warnings: list[str] = []
        if warn_active:
            warnings.append(warn_reason)
            effective_hold = min(hold_days, int(warn_meta.get("max_hold_days") or hold_days))
        if panic_active:
            warnings.append(panic_reason)

        try:
            from utils import log

            for w in warnings:
                log.warning("[ALGO_RISK] %s — %s", sym, w.replace("⚠️ WARNING: ", ""))
        except Exception:
            pass

        approved_payload = {
            "ticker": sym,
            "approved": True,
            "reason": warnings[0] if warnings else "Passed contextual risk checks (M&A, earnings, sympathy, stabilization).",
            "rule": "sympathy_warning" if warn_active else None,
            "hold_days": effective_hold,
            "requested_hold_days": hold_days,
            "days_to_earnings": earn_meta.get("days_to_earnings"),
            "warnings": warnings,
            "sympathy_warning": warn_meta if warn_active else None,
            "entry_execution": panic_meta if panic_active else None,
            "trade_constraints": build_trade_constraints_from_risk(
                {
                    "ticker": sym,
                    "sympathy_warning": warn_meta if warn_active else None,
                    "entry_execution": panic_meta if panic_active else None,
                }
            ),
            "details": {r: m for r, _, _, m in checks if m},
            "checks": [{"rule": r, "blocked": b, "reason": rs} for r, b, rs, _ in checks],
        }
        try:
            from analytics.industries.project_wiring import wire_risk_result

            return wire_risk_result(sym, approved_payload)
        except Exception:
            return approved_payload


def screen_buy_risk(symbol: str, *, hold_days: int = 5, as_of: date | None = None) -> dict[str, Any]:
    return AlgoRiskFilter(as_of=as_of).screen_ticker(symbol, hold_days=hold_days)


def blocks_buy(symbol: str, *, hold_days: int = 5, as_of: date | None = None) -> tuple[bool, str]:
    """Return (blocked, reason). blocked=True means do NOT buy."""
    res = screen_buy_risk(symbol, hold_days=hold_days, as_of=as_of)
    blocked = not bool(res.get("approved"))
    reason = str(res.get("reason") or "")
    # Keep parity with gate_buy_order: paper stack should not sit cash-idle on
    # stabilization / sympathy soft-blocks while still logging the risk reason.
    if blocked and os.getenv("PAPER_RELAX_ALGO_RISK", "true").lower() in ("1", "true", "yes"):
        try:
            from utils import log

            log.info("[ALGO_RISK] paper-relax BUY %s — would block: %s", symbol.strip().upper(), reason)
        except Exception:
            pass
        return False, ""
    return blocked, reason


def gate_buy_order(symbol: str, *, hold_days: int = 5, source: str = "") -> bool:
    """Final buy gate for order routing. Returns True when order may proceed."""
    blocked, reason = blocks_buy(symbol, hold_days=hold_days)
    if blocked and os.getenv("FORTRESS_IGNORE_SYMPATHY_RISK", "false").lower() in (
        "1",
        "true",
        "yes",
    ):
        rl = str(reason).lower()
        if "sympathy" in rl or "earnings in" in rl or "near-term" in rl:
            blocked = False
    if blocked and os.getenv("PAPER_RELAX_ALGO_RISK", "true").lower() in ("1", "true", "yes"):
        blocked = False
    if not blocked:
        return True
    try:
        from utils import log

        log.warning(
            "[ALGO_RISK] block BUY %s%s — %s",
            symbol.strip().upper(),
            f" ({source})" if source else "",
            reason,
        )
    except Exception:
        pass
    return False


def apply_risk_gate_to_row(row: dict, *, hold_days: int | None = None) -> dict:
    sym = str(row.get("ticker") or "").upper()
    if not sym:
        return row
    h = hold_days if hold_days is not None else int(os.getenv("HOLD_DAYS_DEFAULT", "5"))
    res = screen_buy_risk(sym, hold_days=h)
    row["algo_risk"] = res
    if res.get("hold_days") is not None:
        row["hold_days_effective"] = int(res["hold_days"])
    if res.get("warnings"):
        row["algo_risk_warnings"] = list(res["warnings"])
    if res.get("trade_constraints"):
        row["trade_constraints"] = dict(res["trade_constraints"])
    if not res.get("approved"):
        gd = str(row.get("gate_detail", "all_ok"))
        tag = f"risk:{res.get('rule')}"
        row["gate_detail"] = tag if gd == "all_ok" else f"{gd}+{tag}"
        row["asym_action"] = "NO_TRADE"
    return row
