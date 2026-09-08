"""
Hedge-fund-style signal stack — factor, stat-arb, trend, ETF dislocation, market-neutral tilt.

Renaissance-style idea: combine many weak edges (each ~0.5–2% rank boost), not one indicator.
Used by fortress_live, paper_sim_today, and optional HFT pair tilt.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

# ETFs vs liquid benchmark for premium/discount proxy (no live NAV feed required).
_ETF_BENCH: dict[str, str] = {
    "SPY": "SPY",
    "QQQ": "SPY",
    "IWM": "SPY",
    "DIA": "SPY",
    "VTI": "SPY",
    "VOO": "SPY",
    "XLF": "SPY",
    "XLK": "SPY",
    "XLE": "SPY",
    "XLV": "SPY",
    "ARKK": "QQQ",
    "SMH": "QQQ",
}


def _enabled() -> bool:
    return os.getenv("USE_HEDGE_FUND_STACK", "true").lower() in ("1", "true", "yes")


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _pair_map() -> dict[str, str]:
    raw = os.getenv(
        "PAPER_SIM_PAIR_MAP",
        "KO:PEP,PEP:KO,V:MA,MA:V,XOM:CVX,CVX:XOM,JPM:BAC,BAC:JPM,MSFT:AAPL,AAPL:MSFT,GOOGL:META,META:GOOGL",
    )
    out: dict[str, str] = {}
    for token in raw.split(","):
        if ":" not in token:
            continue
        a, b = token.strip().upper().split(":", 1)
        if a and b and a != b:
            out[a] = b
    return out


@dataclass
class HedgeFundSignals:
    momentum: float = 0.0
    value: float = 0.0
    quality: float = 0.0
    size: float = 0.0
    trend: float = 0.0
    stat_arb: float = 0.0
    pair_z: float | None = None
    pair_peer: str | None = None
    etf_dislocation: float = 0.0
    market_neutral_tilt: float = 0.0
    mean_reversion: float = 0.0
    liquidity_mm: float = 0.0
    boost: float = 0.0
    short_tilt: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)


def factor_scores_from_row(row: pd.Series | dict, fund: dict | None = None) -> dict[str, float]:
    """Fama-French style factors from features + optional fundamentals."""
    if isinstance(row, pd.Series):
        r = {k: float(row[k]) for k in row.index if isinstance(row.get(k), (int, float, np.floating))}
    else:
        r = {k: float(v) for k, v in row.items() if isinstance(v, (int, float, np.floating))}

    mom_5 = float(r.get("momentum_5d", r.get("ret_lag_5", r.get("price_roc_5", 0.0))))
    rs = float(r.get("rs_spy", 1.0))
    vol_mom = float(r.get("vol_confirmed_mom", 0.0))
    vol_ratio = float(r.get("volume_ratio", r.get("volume_ratio_20", 0.0)))
    # Price momentum + RS, with optional volume confirmation (classic volume+price momentum).
    momentum = float(
        np.tanh(mom_5 * 12.0) * 0.45
        + np.tanh((rs - 1.0) * 4.0) * 0.35
        + np.tanh(vol_mom * 20.0) * 0.12
        + np.tanh(max(0.0, vol_ratio - 1.0)) * 0.08
    )

    fund = fund or {}
    if fund.get("value_score") or fund.get("quality_score"):
        value = float(np.clip(fund.get("value_score", 0.0), -1.0, 1.0))
        quality = float(np.clip(fund.get("quality_score", 0.0), -1.0, 1.0))
    else:
        pe = float(r.get("trailing_pe", 0.0) or 0.0)
        value = float(np.tanh((22.0 - pe) / 22.0)) if pe > 0 else 0.0
        roe = float(r.get("roe", 0.0) or 0.0)
        quality = float(np.tanh(roe * 3.0)) if roe else 0.0

    mcap = float(r.get("market_cap", 0.0) or fund.get("market_cap", 0.0) or 0.0)
    if mcap > 0:
        size = float(np.clip(-np.log10(max(mcap, 1e6)) / 12.0 + 0.85, -1.0, 1.0))
    else:
        size = 0.0

    return {"momentum": momentum, "value": value, "quality": quality, "size": size}


def trend_following_score(row: pd.Series | dict, closes: pd.Series) -> float:
    """Classic trend: MA cross + MACD + RSI momentum."""
    if closes is None or len(closes) < 30:
        return 0.0
    sig = closes.iloc[:-1].astype(float) if len(closes) > 2 else closes.astype(float)
    out = 0.0
    try:
        if len(sig) >= 210:
            ma50 = float(sig.rolling(50).mean().iloc[-1])
            ma200 = float(sig.rolling(200).mean().iloc[-1])
            if ma200 > 0:
                out += 0.50 * float(np.tanh((ma50 / ma200 - 1.0) * 25.0))
        ema12 = float(sig.ewm(span=12, adjust=False).mean().iloc[-1])
        ema26 = float(sig.ewm(span=26, adjust=False).mean().iloc[-1])
        macd = ema12 - ema26
        macd_sig = float(
            (sig.ewm(span=12, adjust=False).mean() - sig.ewm(span=26, adjust=False).mean())
            .ewm(span=9, adjust=False)
            .mean()
            .iloc[-1]
        )
        out += 0.35 * float(np.tanh((macd - macd_sig) * 20.0))
        rsi = float(row.get("rsi", 50.0) if isinstance(row, dict) else row.get("rsi", 50.0))
        out += 0.15 * float(np.tanh((rsi - 50.0) / 15.0))
    except Exception:
        pass
    return float(np.clip(out, -1.0, 1.0))


def stat_arb_pair_signal(
    symbol: str,
    closes: pd.Series,
    *,
    pair_closes_loader=None,
) -> tuple[float, float | None, str | None]:
    """Log-spread z-score vs paired peer — mean-reversion long when cheap."""
    pair = _pair_map().get(symbol.upper())
    if not pair or closes is None or len(closes) < 40:
        return 0.0, None, pair
    if pair_closes_loader is None:
        return 0.0, None, pair
    p_closes = pair_closes_loader(pair)
    if p_closes is None or len(p_closes) < 40:
        return 0.0, None, pair
    try:
        look = int(os.getenv("PAIR_Z_LOOKBACK", "60"))
        self_sig = closes.iloc[:-1]
        pair_sig = p_closes.reindex(self_sig.index).dropna()
        self_sig = self_sig.reindex(pair_sig.index).dropna()
        if len(self_sig) < max(30, look):
            return 0.0, None, pair
        spread = np.log(self_sig.clip(lower=1e-9)) - np.log(pair_sig.clip(lower=1e-9))
        hist = spread.iloc[-look:]
        mu, sd = float(hist.mean()), float(hist.std(ddof=0))
        if sd <= 1e-9:
            return 0.0, 0.0, pair
        z = float((spread.iloc[-1] - mu) / sd)
        sig = float(np.clip(-z / 2.0, -1.0, 1.0))
        return sig, z, pair
    except Exception:
        return 0.0, None, pair


def etf_dislocation_score(symbol: str, closes: pd.Series, bench_closes: pd.Series | None) -> float:
    """
    ETF vs benchmark: short-term relative return below long-term → discount (buy tilt).
    Jane Street–style creation/redemption arb proxy without live NAV.
    """
    sym = symbol.upper()
    if sym not in _ETF_BENCH or closes is None or bench_closes is None:
        return 0.0
    if len(closes) < 65 or len(bench_closes) < 65:
        return 0.0
    try:
        c = closes.iloc[:-1].astype(float)
        b = bench_closes.reindex(c.index).ffill().astype(float)
        rel = (c / b).replace([np.inf, -np.inf], np.nan).dropna()
        if len(rel) < 60:
            return 0.0
        r5 = float(rel.iloc[-1] / rel.iloc[-6] - 1.0) if len(rel) >= 6 else 0.0
        r60 = float(rel.iloc[-1] / rel.iloc[-61] - 1.0) if len(rel) >= 61 else 0.0
        gap = r5 - r60
        return float(np.clip(-gap * 8.0, -1.0, 1.0))
    except Exception:
        return 0.0


def mean_reversion_score(row: pd.Series | dict, closes: pd.Series) -> float:
    """Overreaction fade: stretched vs 20d VWAP / Bollinger proxy."""
    if closes is None or len(closes) < 25:
        return 0.0
    try:
        sig = closes.iloc[:-1].astype(float)
        last = float(sig.iloc[-1])
        ma = float(sig.rolling(20).mean().iloc[-1])
        sd = float(sig.rolling(20).std(ddof=0).iloc[-1])
        if sd <= 1e-9 or ma <= 0:
            return 0.0
        z = (last - ma) / sd
        return float(np.clip(-z / 2.5, -1.0, 1.0))
    except Exception:
        return 0.0


def market_neutral_tilt(row: pd.Series | dict, regime_score: float = 0.0) -> float:
    """Balance long beta: in bear regimes favor defensive; in bull favor momentum."""
    rs = float(row.get("rs_spy", 1.0) if isinstance(row, dict) else row.get("rs_spy", 1.0))
    beta_proxy = float(np.tanh((rs - 1.0) * 3.0))
    if regime_score < -0.15:
        return float(np.clip(-beta_proxy * 0.6, -1.0, 1.0))
    if regime_score > 0.15:
        return float(np.clip(beta_proxy * 0.5, -1.0, 1.0))
    return 0.0


def liquidity_market_making_score(row: pd.Series | dict) -> float:
    """Tight spread + volume = market-making friendly (liquidity provision edge)."""
    vol_ratio = float(row.get("volume_ratio", 0.0) if isinstance(row, dict) else row.get("volume_ratio", 0.0))
    vol = float(row.get("volatility", row.get("vol_roll_20", 0.02)) if isinstance(row, dict) else row.get("volatility", 0.02))
    liq = float(np.tanh(max(0.0, vol_ratio - 1.0)))
    tight = float(np.tanh((0.04 - min(vol, 0.15)) * 20.0))
    return float(np.clip(0.6 * liq + 0.4 * tight, -1.0, 1.0))


def hedge_fund_rank_boost(
    symbol: str,
    *,
    row: pd.Series | dict,
    closes: pd.Series | None = None,
    bench_closes: pd.Series | None = None,
    fund: dict | None = None,
    regime_score: float = 0.0,
    pair_closes_loader=None,
) -> HedgeFundSignals:
    """Composite rank boost from multi-strategy hedge-fund playbook."""
    out = HedgeFundSignals()
    if not _enabled():
        return out

    factors = factor_scores_from_row(row, fund)
    out.momentum = factors["momentum"]
    out.value = factors["value"]
    out.quality = factors["quality"]
    out.size = factors["size"]

    if closes is not None and len(closes) > 0:
        out.trend = trend_following_score(row, closes)
        out.mean_reversion = mean_reversion_score(row, closes)
        arb, z, peer = stat_arb_pair_signal(symbol, closes, pair_closes_loader=pair_closes_loader)
        out.stat_arb = arb
        out.pair_z = z
        out.pair_peer = peer
        out.etf_dislocation = etf_dislocation_score(symbol, closes, bench_closes)

    out.market_neutral_tilt = market_neutral_tilt(row, regime_score)
    out.liquidity_mm = liquidity_market_making_score(row)

    w_mom = _f("HF_W_MOMENTUM", 0.11)
    w_val = _f("HF_W_VALUE", 0.07)
    w_qual = _f("HF_W_QUALITY", 0.07)
    w_size = _f("HF_W_SIZE", 0.04)
    w_trend = _f("HF_W_TREND", 0.10)
    w_arb = _f("HF_W_STAT_ARB", 0.11)
    w_etf = _f("HF_W_ETF_DISLOC", 0.0)  # lockdown: never favor index ETFs via dislocation
    w_mr = _f("HF_W_MEAN_REV", 0.07)
    w_mn = _f("HF_W_MARKET_NEUTRAL", 0.04)
    w_mm = _f("HF_W_LIQUIDITY_MM", 0.0)  # lockdown: gate-only / no rank boost
    try:
        from self_modify.strategy_overlay import hf_weight_deltas

        for k, dv in hf_weight_deltas().items():
            if k == "HF_W_MOMENTUM":
                w_mom += dv
            elif k == "HF_W_VALUE":
                w_val += dv
            elif k == "HF_W_QUALITY":
                w_qual += dv
            elif k == "HF_W_SIZE":
                w_size += dv
            elif k == "HF_W_TREND":
                w_trend += dv
            elif k == "HF_W_STAT_ARB":
                w_arb += dv
            elif k == "HF_W_ETF_DISLOC":
                w_etf += dv
            elif k == "HF_W_MEAN_REV":
                w_mr += dv
            elif k == "HF_W_MARKET_NEUTRAL":
                w_mn += dv
            elif k == "HF_W_LIQUIDITY_MM":
                w_mm += dv
    except Exception:
        pass
    # Hard lock: liquidity_mm never ranks off HFT. ETF disloc allowed when unlock + sleeve weight.
    if os.getenv("HF_LOCK_ETF_DISLOC_ZERO", "false").lower() in ("1", "true", "yes"):
        w_etf = 0.0
    if os.getenv("HF_LOCK_LIQUIDITY_MM_ZERO", "true").lower() in ("1", "true", "yes"):
        w_mm = 0.0
    # Non-HFT: always kill liquidity_mm rank boost (lives on HFT spread)
    _sleeve = (os.getenv("FATE_SLEEVE") or os.getenv("PAPER_SIM_SLEEVE") or "").strip().lower()
    if _sleeve and _sleeve != "hft":
        w_mm = 0.0

    weights = [w_mom, w_val, w_qual, w_size, w_trend, w_arb, w_etf, w_mr, w_mn, w_mm]
    if os.getenv("HF_NORMALIZE_WEIGHTS", "true").lower() in ("1", "true", "yes"):
        try:
            from analytics.vector_math import normalize_weights

            weights = [float(x) for x in normalize_weights(weights, clip_negative=True)]
            w_mom, w_val, w_qual, w_size, w_trend, w_arb, w_etf, w_mr, w_mn, w_mm = weights
        except Exception:
            pass

    out.boost = (
        w_mom * out.momentum
        + w_val * out.value
        + w_qual * out.quality
        + w_size * out.size
        + w_trend * out.trend
        + w_arb * out.stat_arb
        + w_etf * out.etf_dislocation
        + w_mr * out.mean_reversion
        + w_mn * out.market_neutral_tilt
        + w_mm * out.liquidity_mm
    )

    if os.getenv("HF_LONG_SHORT_EQUITY", "false").lower() in ("1", "true", "yes"):
        bearish = (
            out.momentum < -0.35
            and out.trend < -0.25
            and out.mean_reversion < 0.1
        )
        if bearish:
            out.short_tilt = float(min(1.0, abs(out.momentum) + abs(out.trend)) * 0.5)

    out.meta = {
        "strategy": "hedge_fund_stack",
        "factors": factors,
        "weights_sum": w_mom + w_val + w_qual + w_size + w_trend + w_arb + w_etf + w_mr + w_mn + w_mm,
    }
    return out


def portfolio_risk_overlay(
    positions: list[dict],
    equity: float,
    *,
    sector_map: dict[str, str] | None = None,
    multiplier: float | None = None,
    capacity: float | None = None,
) -> dict[str, Any]:
    """
    Risk management layer: sector concentration, single-name cap, gross exposure.
    Returns warnings and scale factor for new buys [0, 1].

    When FORTRESS_EXPOSURE_USE_BP is on (default), gross/single caps are vs
    buying-power capacity (equity × multiplier), not raw equity — otherwise a
    4× margin book at ~150% of equity falsely zeros all new buys.
    """
    if equity <= 0:
        return {"ok": True, "scale": 1.0, "warnings": []}

    use_bp = (
        os.getenv("USE_BUYING_POWER", "true").lower() in ("1", "true", "yes")
        and os.getenv("FORTRESS_EXPOSURE_USE_BP", "true").lower() in ("1", "true", "yes")
    )
    mult = float(multiplier or 0.0)
    if capacity is not None and float(capacity) > 0:
        cap_base = float(capacity)
    elif use_bp:
        if mult <= 1.0:
            try:
                mult = float(os.getenv("MAX_GROSS_LEVERAGE", "4") or 4)
            except Exception:
                mult = 4.0
        cap_base = equity * max(mult, 1.0)
    else:
        cap_base = equity
    cap_base = max(cap_base, equity, 1e-9)

    max_gross = _f("FORTRESS_MAX_GROSS_FRAC", _f("HF_MAX_GROSS_FRAC", 0.95))
    # Single-name overlay: equity basis when configured (matches fortress).
    single_base = equity
    if os.getenv("FORTRESS_SINGLE_CAP_USE_EQUITY", "true").lower() not in ("1", "true", "yes"):
        single_base = cap_base
    max_single = _f("HF_MAX_SINGLE_FRAC", _f("MAX_SINGLE_ASSET_FRAC", 0.12))
    max_sector = _f("HF_MAX_SECTOR_FRAC", 0.35)

    warnings: list[str] = []
    gross = 0.0
    by_sector: dict[str, float] = {}
    by_sym: dict[str, float] = {}

    for p in positions:
        sym = str(p.get("symbol", "")).replace("/", "-").upper()
        mv = abs(float(p.get("market_value") or p.get("mv") or 0))
        gross += mv
        by_sym[sym] = by_sym.get(sym, 0.0) + mv
        sec = (sector_map or {}).get(sym, "unknown")
        by_sector[sec] = by_sector.get(sec, 0.0) + mv

    gross_frac = gross / cap_base
    # Keep equity-relative gross for logs/compat.
    gross_frac_equity = gross / max(equity, 1e-9)
    if gross_frac >= max_gross:
        warnings.append(
            f"gross_exposure={gross_frac:.1%}>={max_gross:.0%} (cap_base=${cap_base:,.0f}, vs_equity={gross_frac_equity:.1%})"
        )
        return {
            "ok": False,
            "scale": 0.0,
            "warnings": warnings,
            "gross_frac": gross_frac,
            "gross_frac_equity": gross_frac_equity,
            "cap_base": cap_base,
        }

    worst_single = max((v / max(single_base, 1e-9) for v in by_sym.values()), default=0.0)
    worst_sector = max((v / equity for v in by_sector.values()), default=0.0)

    scale = 1.0
    if worst_single >= max_single:
        scale = min(scale, 0.5)
        warnings.append(f"single_name={worst_single:.1%}")
    if worst_sector >= max_sector:
        scale = min(scale, 0.6)
        warnings.append(f"sector={worst_sector:.1%}")

    return {
        "ok": scale > 0.1,
        "scale": scale,
        "warnings": warnings,
        "gross_frac": gross_frac,
        "gross_frac_equity": gross_frac_equity,
        "worst_single_frac": worst_single,
        "worst_sector_frac": worst_sector,
        "cap_base": cap_base,
    }
