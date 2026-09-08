"""
Kelly-based sizing sketch, portfolio heat cap, ATR stops,
Phase 14: per-asset exposure cap, total gross exposure cap, monthly drawdown halt,
optional sector concentration filter.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from utils import log

MAX_HEAT = float(os.getenv("MAX_PORTFOLIO_HEAT", "0.06"))
_SECTOR_CACHE: dict[str, str] = {}
_SECTOR_CACHE_PATH = Path(os.getenv("SECTOR_CACHE_FILE", "data/risk/sector_cache.json"))


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default


def _b(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes")


def base_symbol(symbol: str) -> str:
    s = symbol.upper().strip()
    if s.endswith(":S"):
        return s[:-2]
    return s


def _load_sector_disk() -> None:
    global _SECTOR_CACHE
    if not _SECTOR_CACHE_PATH.is_file():
        return
    try:
        raw = json.loads(_SECTOR_CACHE_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            _SECTOR_CACHE.update({str(k).upper(): str(v) for k, v in raw.items()})
    except Exception:
        pass


def _save_sector_disk() -> None:
    try:
        _SECTOR_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _SECTOR_CACHE_PATH.write_text(json.dumps(_SECTOR_CACHE, indent=0), encoding="utf-8")
    except Exception:
        pass


def get_sector(symbol: str) -> str:
    """Best-effort sector label for concentration checks (cached, disk-backed)."""
    sym = base_symbol(symbol)
    if sym in _SECTOR_CACHE:
        return _SECTOR_CACHE[sym]
    if not _b("USE_SECTOR_RISK", False):
        _SECTOR_CACHE[sym] = "Unknown"
        return "Unknown"
    try:
        import yfinance as yf

        info = yf.Ticker(sym).info or {}
        sec = str(info.get("sector") or "Unknown")
    except Exception:
        sec = "Unknown"
    if not isinstance(sec, str) or not sec:
        sec = "Unknown"
    _SECTOR_CACHE[sym] = sec
    if len(_SECTOR_CACHE) % 25 == 0:
        _save_sector_disk()
    return sec


_load_sector_disk()


@dataclass
class MonthlyEquityState:
    month_key: str
    start_equity: float
    peak_equity: float

    @staticmethod
    def path() -> Path:
        return Path(os.getenv("MONTHLY_EQUITY_STATE_FILE", "data/risk/monthly_equity.json"))

    @classmethod
    def load(cls) -> "MonthlyEquityState | None":
        p = cls.path()
        if not p.is_file():
            return None
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            return cls(
                month_key=str(d.get("month_key", "")),
                start_equity=float(d.get("start_equity", 0.0)),
                peak_equity=float(d.get("peak_equity", 0.0)),
            )
        except Exception:
            return None

    def save(self) -> None:
        p = self.path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(
                {
                    "month_key": self.month_key,
                    "start_equity": self.start_equity,
                    "peak_equity": self.peak_equity,
                    "updated_utc": datetime.now(timezone.utc).isoformat(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )


def _paper_equity_default() -> float:
    return _f("PAPER_EQUITY", 100000.0)


def _is_dummy_paper_equity(eq: float) -> bool:
    """True when `eq` is the env dummy (exactly PAPER_EQUITY), not a live broker mark."""
    return abs(float(eq) - _paper_equity_default()) < 0.005


def monthly_drawdown_ok(current_equity: float) -> tuple[bool, str]:
    """Halt new risk if drawdown from intra-month peak exceeds MONTHLY_DRAWDOWN_HALT_PCT."""
    if not _b("USE_MONTHLY_DRAWDOWN_HALT", True):
        return True, "monthly_dd_disabled"
    # Idle cash is already the risk-off. Parking 50% cash because the paper
    # peak is ~$100k vs ~$72k now is the bleed — fill first, re-arm at target.
    if _b("FORTRESS_FILL_SKIP_MONTHLY_DD", False):
        return True, "monthly_dd_fill_idle"
    halt_pct = _f("MONTHLY_DRAWDOWN_HALT_PCT", 0.10)
    now = datetime.now(timezone.utc)
    mk = f"{now.year:04d}-{now.month:02d}"
    dummy = _is_dummy_paper_equity(current_equity)
    sim = _b("PAPER_SIM_ACTIVE_RUN", False)
    st = MonthlyEquityState.load()
    if st is None or st.month_key != mk:
        if dummy:
            # Do not seed the live peak with PAPER_EQUITY=100000 from paper_sim / unsynced fortress.
            return True, "monthly_dd_skip_dummy_seed"
        st = MonthlyEquityState(month_key=mk, start_equity=float(current_equity), peak_equity=float(current_equity))
        st.save()
    # Heal a poisoned peak: PAPER_EQUITY default stamped over a real ~$75k book.
    if (
        _is_dummy_paper_equity(st.peak_equity)
        and st.start_equity > 1.0
        and abs(st.start_equity - st.peak_equity) / max(st.peak_equity, 1e-9) > 0.08
    ):
        healed = max(st.start_equity, float(current_equity) if not dummy else st.start_equity)
        log.warning(
            "[RISK] Rebase monthly peak $%.0f → $%.0f (paper-default stamp vs start $%.0f)",
            st.peak_equity,
            healed,
            st.start_equity,
        )
        st.peak_equity = healed
        st.save()
    if not dummy:
        old_peak = st.peak_equity
        st.peak_equity = max(st.peak_equity, float(current_equity))
        if st.peak_equity != old_peak:
            st.save()
    elif sim:
        # Hypothetical 100k book must not raise the live Alpaca peak.
        return True, "monthly_dd_paper_sim_isolated"
    eq = float(current_equity)
    dd = (st.peak_equity - eq) / max(st.peak_equity, 1e-9)
    if dd >= halt_pct:
        return False, f"monthly_dd_{dd:.4f}_ge_{halt_pct:.4f}"
    return True, "monthly_dd_ok"


@dataclass
class OpenLeg:
    symbol: str
    notional: float
    entry: float
    stop: float
    mfe: float = 0.0


@dataclass
class RiskManager:
    equity: float
    win_rate: float = 0.52
    avg_win: float = 0.02
    avg_loss: float = 0.015
    legs: dict[str, OpenLeg] = field(default_factory=dict)

    def kelly_fraction(self) -> float:
        b = self.avg_win / max(self.avg_loss, 1e-9)
        p = self.win_rate
        q = 1 - p
        f = (b * p - q) / max(b, 1e-9)
        half_kelly = max(0.0, min(0.25, f / 2))
        cap = float(os.getenv("KELLY_CAP", "0.10"))
        return min(half_kelly, cap)

    def current_heat(self) -> float:
        risk = 0.0
        for leg in self.legs.values():
            risk += abs(leg.entry - leg.stop) / max(leg.entry, 1e-9) * leg.notional
        return risk / max(self.equity, 1e-9)

    def total_gross_exposure(self) -> float:
        return sum(abs(leg.notional) for leg in self.legs.values())

    def symbol_gross_exposure(self, symbol: str) -> float:
        b = base_symbol(symbol)
        return sum(abs(leg.notional) for sym, leg in self.legs.items() if base_symbol(sym) == b)

    def sector_gross_exposure(self, sector: str) -> float:
        tot = 0.0
        for sym, leg in self.legs.items():
            if get_sector(sym) == sector:
                tot += abs(leg.notional)
        return tot

    def register_open(self, symbol: str, notional: float, entry: float, stop: float) -> None:
        self.legs[symbol] = OpenLeg(symbol=symbol, notional=abs(notional), entry=entry, stop=stop)

    def can_open(self, symbol: str, notional: float, entry: float, stop: float) -> bool:
        ok, _ = self.can_open_explain(symbol, notional, entry, stop)
        return ok

    def can_open_explain(self, symbol: str, notional: float, entry: float, stop: float) -> tuple[bool, str]:
        notional = abs(float(notional))
        ok_m, reason_m = monthly_drawdown_ok(float(self.equity))
        if not ok_m:
            log.warning("[RISK] Monthly drawdown halt — reject %s (%s)", symbol, reason_m)
            return False, reason_m

        heat = self.current_heat()
        proposed = abs(entry - stop) / max(entry, 1e-9) * notional / max(self.equity, 1e-9)
        if heat + proposed > MAX_HEAT:
            log.warning("[RISK] Heat cap %.1f%% — reject %s", 100 * MAX_HEAT, symbol)
            return False, "heat_cap"

        max_total = (
            _f("FORTRESS_MAX_GROSS_FRAC", _f("FORTRESS_BP_USE_FRAC", 0.92))
            if os.getenv("FORTRESS_EXPOSURE_USE_BP", "true").lower() in ("1", "true", "yes")
            and os.getenv("USE_BUYING_POWER", "true").lower() in ("1", "true", "yes")
            else _f("MAX_TOTAL_EXPOSURE_FRAC", 0.70)
        )
        # Full capacity = equity × leverage — NOT remaining buying_power (shrinks as we deploy).
        cap_base = max(self.equity, 1e-9)
        use_bp = (
            os.getenv("USE_BUYING_POWER", "true").lower() in ("1", "true", "yes")
            and os.getenv("FORTRESS_EXPOSURE_USE_BP", "true").lower() in ("1", "true", "yes")
        )
        if use_bp:
            max_lev = _f("MAX_GROSS_LEVERAGE", 4.0)
            mult = max_lev
            try:
                from alpaca_broker import get_account

                acct = get_account() or {}
                m = float(acct.get("multiplier") or 0.0)
                if m > 1.0:
                    mult = m
            except Exception:
                pass
            cap_base = max(self.equity * mult, self.equity)
        if (self.total_gross_exposure() + notional) / cap_base > max_total:
            log.warning("[RISK] Total exposure cap %.0f%% — reject %s", 100 * max_total, symbol)
            return False, "total_exposure_cap"

        max_one = _f("MAX_SINGLE_ASSET_FRAC", 0.05)
        try:
            from crypto_universe import is_crypto_symbol

            if is_crypto_symbol(symbol):
                max_one = _f("FORTRESS_CRYPTO_MAX_SINGLE_FRAC", 0.18)
        except Exception:
            pass
        # Per-name risk vs equity by default (1% of equity), even when book uses 4× BP.
        if os.getenv("FORTRESS_SINGLE_CAP_USE_EQUITY", "true").lower() in ("1", "true", "yes"):
            single_cap_base = max(self.equity, 1e-9)
        else:
            single_cap_base = cap_base if use_bp else max(self.equity, 1e-9)
        if (self.symbol_gross_exposure(symbol) + notional) / max(single_cap_base, 1e-9) > max_one:
            log.warning("[RISK] Single-asset cap %.0f%% — reject %s", 100 * max_one, symbol)
            return False, "single_asset_cap"

        if _b("USE_SECTOR_RISK", False):
            sec = get_sector(symbol)
            max_sec = _f("SECTOR_MAX_EXPOSURE_FRAC", 0.30)
            if (self.sector_gross_exposure(sec) + notional) / max(self.equity, 1e-9) > max_sec:
                log.warning("[RISK] Sector %s cap %.0f%% — reject %s", sec, 100 * max_sec, symbol)
                return False, "sector_cap"

        if not self._corr_ok(symbol):
            return False, "correlation_block"

        return True, "ok"

    def _corr_ok(self, symbol: str) -> bool:
        thr = float(os.getenv("CORRELATION_BLOCK", "0.85"))
        _ = thr  # reserved for live covariance matrix
        return True

    def atr_stop(self, price: float, atr: float, mult: float | None = None) -> float:
        m = mult if mult is not None else float(os.getenv("ATR_STOP_MULT", "1.5"))
        return price - atr * m

    def target_notional(
        self,
        confidence: float,
        volatility: float,
        max_single_pos_frac: float | None = None,
    ) -> float:
        """Portfolio-level sizing kernel used by concurrent runtime."""
        max_frac = max_single_pos_frac if max_single_pos_frac is not None else float(
            os.getenv("MAX_SINGLE_POSITION_FRAC", "0.03")
        )
        conf_edge = max(0.0, min(1.0, (confidence - 0.5) * 2.0))
        vol_penalty = 1.0 / max(1.0 + volatility * 12.0, 1e-6)
        frac = max_frac * conf_edge * vol_penalty
        frac = min(frac, max_frac)
        return self.equity * frac


def rolling_correlation_block(
    rets: pd.DataFrame,
    sym_a: str,
    sym_b: str,
    thr: float = 0.85,
) -> bool:
    if sym_a not in rets.columns or sym_b not in rets.columns:
        return False
    c = rets[sym_a].rolling(60).corr(rets[sym_b]).iloc[-1]
    if np.isnan(c):
        return False
    return abs(c) > thr
