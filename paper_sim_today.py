"""
Batch paper simulation: causal next-bar PnL.

For each symbol that has a trained model, we use bar T-1 ("yesterday") as the signal bar
and realize PnL on bar T ("today").

Three selection modes:
- gates:   strict (Fortress) — must pass min_conf + volume + MTF + sentiment + risk
- top_k:   relaxed — rank by a composite score, force-buy the best K names
           (RL tiebreak when |p_up - 0.5| is small)
- all_good: buy all names above confidence + score constraints

Default mode = all_good with min_conf=0.55.

Writes reports/paper_sim_YYYYMMDD.json plus a market-wide leaderboard so we can see what
went up regardless of our picks (oppor­tunity cost).
"""

from __future__ import annotations

import json
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
from dotenv import load_dotenv

load_dotenv()
_deploy = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "deploy_scale.env")
if os.path.isfile(_deploy):
    load_dotenv(_deploy, override=True)

from data_platform.market_prices import configure_process_prices

configure_process_prices()

from feature_engineering import _price_source, build_features, load_price_data
from feature_store import volume_confirmed
from ml_model import predict_row_details, predict_row_horizon
from multi_timeframe import mtf_buy_ok
from regime_detector import simple_regime_from_spy
from risk_manager import RiskManager
from sentiment_pipeline import block_long_on_sentiment, composite_sentiment, get_symbol_news_intel
from universe_provider import load_universe_with_cap
from utils import log


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes")


_FUND_CACHE: dict[str, dict] = {}
_PAIR_CLOSE_CACHE: dict[str, pd.Series] = {}
def _spy_df() -> pd.DataFrame:
    start = (datetime.now(timezone.utc) - pd.Timedelta(days=365)).strftime("%Y-%m-%d")
    spy = load_price_data("SPY", start)
    if spy is None or spy.empty:
        return pd.DataFrame()
    if isinstance(spy.columns, pd.MultiIndex):
        spy.columns = [c[0] if isinstance(c, tuple) else c for c in spy.columns]
    return spy


def _rl_action_hint(ticker: str, df: pd.DataFrame) -> float | None:
    path = os.path.join("models", f"{ticker}_ppo.zip")
    if not os.path.isfile(path):
        return None
    try:
        from stable_baselines3 import PPO
        from rl_trading_env import get_stock_trading_env_class

        env = get_stock_trading_env_class()(df.iloc[-260:].reset_index(drop=True))
        model = PPO.load(path)
        obs, _ = env.reset()
        env.t = max(env.window, len(env.X) - 2)
        obs = env._obs()
        action, _ = model.predict(obs, deterministic=True)
        return float(int(action) - 1)
    except Exception as e:
        log.debug("[PAPER_SIM] RL hint skipped %s: %s", ticker, e)
        return None


def _composite_score(
    p_up: float,
    momentum_5d: float,
    rs_spy: float,
    vol_ratio: float,
    sent: float,
    dip_signal: float = 0.0,
) -> float:
    """Higher score = stronger BUY candidate. Delegates to unified rank pipeline."""
    from analytics.rank_pipeline import core_composite_score

    return core_composite_score(
        p_up, momentum_5d, rs_spy, vol_ratio, sent, dip_signal=dip_signal
    )


def _dip_bonus_uptrend_oversold(row_sig: pd.Series, closes: pd.Series) -> float:
    """Return [0, 1] for oversold inside a still-bullish EMA stack (original logic)."""
    try:
        rsi = float(row_sig.get("rsi", 50.0))
        ema_20 = float(row_sig.get("ema_20", 0.0))
        ema_50 = float(row_sig.get("ema_50", 0.0))
        if ema_20 <= ema_50:
            return 0.0
        if len(closes) < 22:
            return 0.0
        roll_high = float(closes.iloc[-22:-2].max())
        last = float(closes.iloc[-2])
        drawdown = last / roll_high - 1.0 if roll_high > 0 else 0.0
        if rsi > 35.0 or drawdown > -0.03:
            return 0.0
        depth = max(0.0, min(1.0, (35.0 - rsi) / 15.0))  # 35 -> 0, 20 -> 1
        return float(depth)
    except Exception:
        return 0.0


def _dip_bonus_deep_pullback(row_sig: pd.Series, closes: pd.Series) -> float:
    """Oversized drop from recent high → partial mean-reversion tilt (capped, not 'always rebound')."""
    if not _env_bool("DIP_ENABLE_DEEP_PULLBACK", True):
        return 0.0
    try:
        if len(closes) < 25:
            return 0.0
        look = min(len(closes) - 2, int(os.getenv("DIP_DEEP_HIGH_LOOKBACK", "60")))
        look = max(22, look)
        roll_high = float(closes.iloc[-(look + 2) : -2].max())
        last = float(closes.iloc[-2])
        if roll_high <= 0:
            return 0.0
        dd = last / roll_high - 1.0
        start = abs(float(os.getenv("DIP_DEEP_START_FRAC", "0.055")))  # need ~5.5%+ off high
        span = abs(float(os.getenv("DIP_DEEP_SPAN_FRAC", "0.22")))  # extra ~22% maps toward 1.0
        if dd > -start:
            return 0.0
        t = min(1.0, max(0.0, (-dd - start) / max(span, 1e-9)))
        rsi = float(row_sig.get("rsi", 50.0))
        if rsi > 62:
            t *= 0.45
        elif rsi > 55:
            t *= 0.68
        elif rsi > 48:
            t *= 0.88
        ema_20 = float(row_sig.get("ema_20", 0.0))
        ema_50 = float(row_sig.get("ema_50", 0.0))
        if ema_50 > 0 and ema_20 < ema_50:
            t *= float(os.getenv("DIP_DEEP_BEAR_TREND_MULT", "0.70"))
        return float(max(0.0, min(1.0, t)))
    except Exception:
        return 0.0


def _dip_bonus(row_sig: pd.Series, closes: pd.Series) -> float:
    """Blend uptrend dip + deep pullback, gated by momentum (no falling-knife buys)."""
    up = _dip_bonus_uptrend_oversold(row_sig, closes)
    deep = _dip_bonus_deep_pullback(row_sig, closes)
    mix = float(os.getenv("DIP_DEEP_MIX", "0.92"))
    mix = max(0.0, min(1.5, mix))
    raw = float(max(up, min(1.0, deep * mix)))
    try:
        from signals.dip_momentum import apply_dip_momentum_filter

        raw, _ctx = apply_dip_momentum_filter(closes.iloc[:-1] if len(closes) >= 2 else closes, raw)
    except Exception:
        pass
    return raw


def _safe_num(v, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        x = float(v)
        if np.isnan(x) or np.isinf(x):
            return default
        return x
    except Exception:
        return default


def _pair_map() -> dict[str, str]:
    raw = os.getenv(
        "PAPER_SIM_PAIR_MAP",
        "KO:PEP,PEP:KO,V:MA,MA:V,XOM:CVX,CVX:XOM,JPM:BAC,BAC:JPM,MSFT:AAPL,AAPL:MSFT,GOOGL:META,META:GOOGL",
    ).strip()
    out: dict[str, str] = {}
    for token in raw.split(","):
        t = token.strip().upper()
        if ":" not in t:
            continue
        a, b = t.split(":", 1)
        a = a.strip()
        b = b.strip()
        if a and b and a != b:
            out[a] = b
    return out


def _load_pair_closes(symbol: str, start_hist: str) -> pd.Series:
    key = f"{symbol}|{start_hist}"
    if key in _PAIR_CLOSE_CACHE:
        return _PAIR_CLOSE_CACHE[key]
    try:
        df = build_features(symbol, start_hist, None)
        if not df.empty and "Close" in df.columns:
            s = df["Close"].astype(float)
            _PAIR_CLOSE_CACHE[key] = s
            return s
    except Exception:
        pass
    _PAIR_CLOSE_CACHE[key] = pd.Series(dtype=float)
    return _PAIR_CLOSE_CACHE[key]


def _pairs_stat_arb_signal(symbol: str, closes: pd.Series, start_hist: str) -> tuple[float, float | None, str | None]:
    """Thin wrapper — canonical math lives in ``analytics.hedge_fund_stack``."""
    try:
        from analytics.hedge_fund_stack import stat_arb_pair_signal

        return stat_arb_pair_signal(
            symbol,
            closes,
            pair_closes_loader=lambda p: _load_pair_closes(p, start_hist),
        )
    except Exception:
        return 0.0, None, None


def _classic_trend_momentum_signal(row_sig: pd.Series, closes: pd.Series) -> dict:
    """Thin wrapper — MA50/200 + MACD + RSI via ``hedge_fund_stack.trend_following_score``."""
    out = {"ma_cross": 0.0, "macd_mom": 0.0, "rsi_mom": 0.0, "trend_signal": 0.0}
    try:
        from analytics.hedge_fund_stack import trend_following_score

        trend = float(trend_following_score(row_sig, closes))
        out["trend_signal"] = trend
        # Preserve component keys for callers / trade reasons (decomposed approx).
        out["ma_cross"] = trend
        out["macd_mom"] = trend
        rsi = float(row_sig.get("rsi", 50.0))
        out["rsi_mom"] = float(np.tanh((rsi - 50.0) / 15.0))
    except Exception:
        pass
    return out


def _hmm_market_regime_score(spy: pd.DataFrame) -> float:
    try:
        if spy.empty or "Close" not in spy.columns:
            return 0.0
        from regime_detector import hmm_regime

        rets = spy["Close"].astype(float).pct_change().dropna()
        states = hmm_regime(rets, n_states=int(os.getenv("HMM_REGIME_STATES", "4")))
        if states is None or len(states) < 20:
            return 0.0
        arr = rets.to_numpy()[-len(states) :]
        cur = int(states[-1])
        mask = states == cur
        if not mask.any():
            return 0.0
        mean_ret = float(arr[mask].mean())
        # Positive mean state => risk-on, negative => risk-off
        return float(np.tanh(mean_ret * 120.0))
    except Exception:
        return 0.0


def _fundamental_snapshot(ticker: str) -> dict:
    if os.getenv("USE_FUNDAMENTALS", "false").lower() not in ("1", "true", "yes"):
        return {
            "trailing_pe": 0.0,
            "forward_pe": 0.0,
            "pb": 0.0,
            "roe": 0.0,
            "pm": 0.0,
            "de": 0.0,
            "rev_g": 0.0,
            "earn_g": 0.0,
            "value_score": 0.0,
            "quality_score": 0.0,
            "fund_score": 0.0,
        }
    if ticker in _FUND_CACHE:
        return _FUND_CACHE[ticker]
    out = {
        "trailing_pe": 0.0,
        "forward_pe": 0.0,
        "pb": 0.0,
        "roe": 0.0,
        "pm": 0.0,
        "de": 0.0,
        "rev_g": 0.0,
        "earn_g": 0.0,
        "value_score": 0.0,
        "quality_score": 0.0,
        "fund_score": 0.0,
    }
    try:
        tk = yf.Ticker(ticker)
        info = tk.info or {}
        tpe = _safe_num(info.get("trailingPE"), 0.0)
        fpe = _safe_num(info.get("forwardPE"), 0.0)
        pb = _safe_num(info.get("priceToBook"), 0.0)
        roe = _safe_num(info.get("returnOnEquity"), 0.0)
        pm = _safe_num(info.get("profitMargins"), 0.0)
        de = _safe_num(info.get("debtToEquity"), 0.0)
        rev_g = _safe_num(info.get("revenueGrowth"), 0.0)
        earn_g = _safe_num(info.get("earningsQuarterlyGrowth"), 0.0)

        # Low valuation ratios -> positive value score.
        value = (
            float(np.tanh((20.0 - tpe) / 20.0))
            + float(np.tanh((18.0 - fpe) / 18.0))
            + float(np.tanh((3.5 - pb) / 3.5))
        ) / 3.0
        # Profitability/growth up, leverage down -> quality score.
        quality = (
            float(np.tanh(roe * 4.0))
            + float(np.tanh(pm * 5.0))
            + float(np.tanh(rev_g * 4.0))
            + float(np.tanh(earn_g * 4.0))
            + float(np.tanh((200.0 - de) / 200.0))
        ) / 5.0

        out.update(
            {
                "trailing_pe": tpe,
                "forward_pe": fpe,
                "pb": pb,
                "roe": roe,
                "pm": pm,
                "de": de,
                "rev_g": rev_g,
                "earn_g": earn_g,
                "value_score": value,
                "quality_score": quality,
                "fund_score": 0.5 * value + 0.5 * quality,
            }
        )
    except Exception:
        pass
    _FUND_CACHE[ticker] = out
    return out


def _resolve_universe(max_symbols: int | None) -> list[str]:
    from fortress_universe import (
        is_tradeable_equity,
        symbols_paper_active_universe,
        symbols_with_daily_models,
    )

    use_live = os.getenv("PAPER_SIM_USE_LIVE_LIST", "false").lower() in ("1", "true", "yes")
    raw = os.getenv("LIVE_SYMBOL_LIST", "").strip()
    source = "unknown"

    if use_live and raw:
        syms = [s.strip().upper() for s in raw.split(",") if s.strip()]
        source = "live_symbol_list"
    elif os.getenv("PAPER_SIM_CONFIG_TICKERS_ONLY", "false").lower() in ("1", "true", "yes"):
        try:
            from config import TRAIN_TICKERS

            syms = list(dict.fromkeys(TRAIN_TICKERS))
        except Exception:
            syms = load_universe_with_cap(max_symbols=None, refresh=False)
        source = "config_train_tickers"
    elif os.getenv("PAPER_SIM_USE_MODEL_UNIVERSE", "false").lower() in ("1", "true", "yes"):
        syms = symbols_with_daily_models()
        source = "all_daily_models"
    elif os.getenv("PAPER_SIM_ACTIVE_ONLY", "true").lower() in ("1", "true", "yes"):
        syms = symbols_paper_active_universe()
        source = "active_intraday_trained"
    else:
        syms = load_universe_with_cap(max_symbols=None, refresh=False)
        source = "us_universe_cache"

    syms = [s for s in syms if is_tradeable_equity(s)]
    if max_symbols is not None:
        from fortress_universe import apply_scan_order

        syms = apply_scan_order(syms)[: int(max_symbols)]
    else:
        from fortress_universe import apply_scan_order

        syms = apply_scan_order(syms)
    log.info("[PAPER_SIM] universe source=%s  symbols=%d", source, len(syms))
    return syms


def _order_for_scoring(syms: list[str]) -> list[str]:
    """Score liquid top-100 first so partial runs still feed family forecast."""
    if os.getenv("PAPER_SIM_SCORE_TOP100_FIRST", "true").lower() not in ("1", "true", "yes"):
        return syms
    try:
        from fortress_universe import load_top100_symbols

        top_set = frozenset(load_top100_symbols())
    except Exception:
        return syms
    top = [s for s in syms if s in top_set]
    rest = [s for s in syms if s not in top_set]
    if top:
        log.info("[PAPER_SIM] scoring order: top100=%d then rest=%d", len(top), len(rest))
    return top + rest


def _score_symbol(
    t: str,
    regime,
    rm: RiskManager,
    scale: float,
    min_p: float,
    start_hist: str,
    hmm_market_score: float = 0.0,
    macro_bundle: dict | None = None,
    bull_bear: dict | None = None,
) -> dict | None:
    t0 = time.perf_counter()
    path = os.path.join("models", f"{t}_model.pkl")
    if not os.path.isfile(path):
        return {"ticker": t, "action": "SKIP", "reason": "no_model", "skipped": True}

    df = build_features(t, start_hist, None)
    t_after_features = time.perf_counter()
    if df.shape[0] < 30:
        return {"ticker": t, "action": "SKIP", "reason": "insufficient_history", "skipped": True}

    row_sig = df.iloc[-2].copy()
    row_out = df.iloc[-1]
    fwd_ret = float(row_out["returns"])
    sig_date = str(df.index[-2].date()) if len(df.index) > 1 else ""
    out_date = str(df.index[-1].date()) if len(df.index) else ""
    sig_close = float(row_sig["Close"])

    closes_for_fwd = df["Adj Close"].astype(float) if "Adj Close" in df.columns else df["Close"].astype(float)

    def _fwd_return_h(h: int) -> float | None:
        """Forward return from signal bar (iloc[-2]) over h sessions.

        At the live edge only h==1 is knowable (outcome bar = iloc[-1]).
        Longer horizons return None until enough future bars exist — never clamp
        to the last bar (that made fwd_5d/10d/20d identical to 1d).
        """
        if h <= 0:
            return None
        n = len(closes_for_fwd)
        sig_i = n - 2
        fut_i = sig_i + h
        if sig_i < 0 or fut_i >= n:
            return None
        try:
            base = float(closes_for_fwd.iloc[sig_i])
            future = float(closes_for_fwd.iloc[fut_i])
            if base <= 0:
                return None
            return float(future / base - 1.0)
        except Exception:
            return None

    fwd_5d_ret = _fwd_return_h(5)
    fwd_10d_ret = _fwd_return_h(10)
    fwd_20d_ret = _fwd_return_h(20)

    lite_intel = os.getenv("PAPER_SIM_LITE_INTEL", "true").lower() in ("1", "true", "yes")
    news_intel: dict = {}
    news_factor = 0.0
    transcript_factor = 0.0
    if lite_intel:
        sent = 0.0
    else:
        try:
            sent = composite_sentiment(t)
        except Exception:
            sent = 0.0
        try:
            news_intel = get_symbol_news_intel(t)
        except Exception:
            news_intel = {}
        if (
            os.getenv("DISABLE_SENTIMENT", "false").lower() not in ("1", "true", "yes")
            and os.getenv("USE_INTEL_FACTORS", "true").lower() in ("1", "true", "yes")
        ):
            try:
                from intel.news_factor_engine import score_symbol_news_factors
                from intel.transcript_factor_engine import score_symbol_transcripts

                nf = score_symbol_news_factors(t)
                tf = score_symbol_transcripts(t)
                news_factor = float(nf.get("final_factor", 0.0))
                transcript_factor = float(tf.get("final_factor", 0.0))
                if os.getenv("HEAVY_NEWS_INTEL", "false").lower() in ("1", "true", "yes"):
                    sent = 0.45 * float(sent) + 0.35 * news_factor + 0.20 * transcript_factor
                else:
                    sent = 0.70 * float(sent) + 0.20 * news_factor + 0.10 * transcript_factor
            except Exception:
                pass
    for k in ("sentiment", "lag_1_sentiment", "lag_2_sentiment", "lag_3_sentiment"):
        # Keep train/serve prior (models train with 0); live sentiment applied via soft gates.
        row_sig[k] = 0.0
    t_after_intel = time.perf_counter()

    det = predict_row_details(path, row_sig)
    p_up = float(det["p_up"])
    ps = det.get("p_short")
    pl = det.get("p_long")
    p_daily_raw: float | None = None
    p_xlong_raw: float | None = None
    p_daily_head: str | None = None
    p_xlong_head: str | None = None
    try:
        pd_det = predict_row_horizon(path, row_sig, "1d")
        px_det = predict_row_horizon(path, row_sig, "xlong")
        if pd_det.get("p_up") is not None and not pd_det.get("head_missing"):
            p_daily_raw = float(pd_det["p_up"])
            p_daily_head = str(pd_det.get("head_used") or "")
        if px_det.get("p_up") is not None and not px_det.get("head_missing"):
            p_xlong_raw = float(px_det["p_up"])
            p_xlong_head = str(px_det.get("head_used") or "")
        elif pl is not None:
            p_xlong_raw = float(pl)
            p_xlong_head = "model_long_fallback"
    except Exception:
        pass
    if os.getenv("USE_MULTI_ALGO_FUSION", "true").lower() in ("1", "true", "yes"):
        try:
            from multi_algo_fusion import fused_decision

            fd = fused_decision(
                ticker=t,
                model_bundle_path=path,
                row=row_sig,
                p_base=float(p_up),
                min_conf=float(min_p),
            )
            p_up = float(fd["p_final"])
        except Exception:
            pass
    hold_d_sleeve = int(os.getenv("HOLD_DAYS_DEFAULT", "5"))
    p_fused_heads = float(p_up)
    try:
        from analytics.horizon_picks import horizon_independent, sleeve_native_probability

        p_sleeve = sleeve_native_probability(
            hold_d_sleeve,
            p_daily=p_daily_raw,
            p_short=float(ps) if ps is not None else None,
            p_long=float(pl) if pl is not None else None,
            p_xlong=p_xlong_raw,
            fused=p_fused_heads,
        )
        if horizon_independent() and p_sleeve is not None:
            p_up = float(p_sleeve)
    except Exception:
        pass
    t_after_predict = time.perf_counter()

    closes = df["Close"].astype(float)
    # Causal series through signal bar only (outcome bar = last must not leak into rank/LSTM).
    df_sig = df.iloc[:-1]
    closes_sig = closes.iloc[:-1]
    mom_5d = float(closes.iloc[-2] / closes.iloc[-7] - 1.0) if len(closes) >= 7 else 0.0
    rs_spy = float(row_sig.get("rs_spy", 1.0))
    vol_ratio = float(row_sig.get("volume_ratio", 0.0))

    vol_ok = volume_confirmed(row_sig, mult=float(os.getenv("VOLUME_CONFIRM_MULT", "1.5")))
    daily_bull = bool(int(row_sig.get("daily_bull_trend", 0)))

    use_mtf = os.getenv("PAPER_SIM_USE_MTF", "false").lower() in ("1", "true", "yes")
    try:
        from analytics.horizon_picks import horizon_independent as _tf_indep_mtf

        if _tf_indep_mtf():
            use_mtf = False
    except Exception:
        pass
    mtf_ok = mtf_buy_ok(daily_bull, t, rsi_oversold=float(os.getenv("MTF_RSI_MAX", "30"))) if use_mtf else True

    rl_hint = _rl_action_hint(t, df_sig) if abs(p_up - 0.5) < float(os.getenv("RL_UNCERTAIN_BAND", "0.06")) else None
    rl_adj = 0.0
    if rl_hint is not None:
        rl_adj = float(os.getenv("RL_HINT_WEIGHT", "0.10")) * rl_hint
        p_up = max(0.0, min(1.0, p_up + rl_adj * 0.5))

    # --- Optional LSTM meta head ---
    lstm_p_up: float | None = None
    if os.getenv("BLEND_LSTM_INTO_META", "true").lower() in ("1", "true", "yes"):
        try:
            from analytics.lstm_head import lstm_proba_up

            lstm_p_up = lstm_proba_up(t, df_sig)
            if lstm_p_up is not None:
                blend_w = float(os.getenv("LSTM_BLEND_WEIGHT", "0.25"))
                p_up = float((1.0 - blend_w) * p_up + blend_w * lstm_p_up)
        except Exception:
            lstm_p_up = None

    # Additive minutely head — not mixed into 5d/20d when each timeframe stands alone.
    try:
        from analytics.horizon_picks import horizon_independent as _tf_indep_intra

        _blend_intra = not _tf_indep_intra()
    except Exception:
        _blend_intra = True
    if _blend_intra:
        try:
            from intraday.live_infer import blend_intraday_p, live_intraday_p_up

            p_intra = live_intraday_p_up(t)
            p_up, _ = blend_intraday_p(float(p_up), p_intra)
        except Exception:
            pass

    from fortress_universe import is_top100_equity, top100_rank

    top100 = is_top100_equity(t)
    foundation_p_up: float | None = None
    foundation_source: str | None = None
    foundation_blend_w = 0.0
    try:
        from analytics.foundation_forecast import foundation_forecast_p
        from analytics.signal_enhance import blend_foundation_safe

        ff = foundation_forecast_p(t, df=df_sig)
        if ff:
            foundation_p_up = float(ff["p_up"])
            foundation_source = str(ff.get("source", ""))
            p_up, foundation_blend_w, _ = blend_foundation_safe(
                p_up, foundation_p_up, is_top100=top100
            )
    except Exception:
        pass

    from analytics.execution_confidence import execution_confidence

    try:
        from analytics.horizon_picks import horizon_independent as _tf_indep_exec

        _pass_other_heads = not _tf_indep_exec()
    except Exception:
        _pass_other_heads = True
    exec_conf, _exec_diag = execution_confidence(
        p_up,
        float(ps) if (_pass_other_heads and ps is not None) else None,
        float(pl) if (_pass_other_heads and pl is not None) else None,
    )

    dip = _dip_bonus(row_sig, closes)
    rally_signal = 0.0
    rally_continuation = False
    momentum_ret_1d = 0.0
    try:
        from signals.dip_momentum import assess_rally_momentum, rally_score_bonus

        rally_ctx = assess_rally_momentum(closes_sig, mom_5d=mom_5d)
        hold_d = int(os.getenv("HOLD_DAYS_DEFAULT", "5"))
        rally_signal = rally_score_bonus(rally_ctx, hold_days=hold_d)
        rally_continuation = bool(rally_ctx.rally_continuation)
        momentum_ret_1d = float(rally_ctx.ret_1d)
    except Exception:
        rally_ctx = None
    neural_p_up: float | None = None
    neural_breakdown: dict | None = None
    neural_state = {
        "p_up_base": float(p_up),
        "p_short_model": float(ps) if ps is not None else float(1.0 - p_up),
        "p_long_model": float(pl) if pl is not None else float(p_up),
        "execution_confidence": float(exec_conf),
        "sentiment": float(sent),
        "news_factor": float(news_factor),
        "transcript_factor": float(transcript_factor),
        "volume_ratio": float(vol_ratio),
        "momentum_5d": float(mom_5d),
        "rs_spy": float(rs_spy),
        "dip_signal": float(dip),
        "rally_signal": float(rally_signal),
        "rally_continuation": bool(rally_continuation),
        "momentum_ret_1d": float(momentum_ret_1d),
        "atr_14": float(row_sig.get("atr_14", sig_close * 0.02)),
        "alpha_proxy_20": float(rs_spy - 1.0),
    }
    if os.getenv("USE_NEURAL_ENSEMBLE", "true").lower() in ("1", "true", "yes"):
        try:
            from online_learning.neural_ensemble import neural_ensemble_details

            neural_breakdown = neural_ensemble_details(t, neural_state)
            neural_p_up = (
                neural_breakdown.get("ensemble_p_up") if neural_breakdown else None
            )
            if neural_p_up is not None:
                _ule_on = False
                try:
                    from analytics.ultimate_learning_engine import enabled as _ule_en

                    _ule_on = bool(_ule_en())
                except Exception:
                    _ule_on = False
                if not _ule_on:
                    nw = float(os.getenv("NEURAL_BLEND_WEIGHT", "0.35"))
                    p_up = float((1.0 - nw) * p_up + nw * neural_p_up)
                    exec_conf, _exec_diag = execution_confidence(
                        p_up,
                        float(ps) if (_pass_other_heads and ps is not None) else None,
                        float(pl) if (_pass_other_heads and pl is not None) else None,
                    )
                    neural_state["p_up_base"] = float(p_up)
                    neural_state["execution_confidence"] = float(exec_conf)
        except Exception as e:
            log.debug("[NEURAL] %s blend skipped: %s", t, e)

    crowd_meta: dict = {}
    # Defaults for return payload — unified / hedge_fund paths may skip the legacy branch
    # that sets these (otherwise UnboundLocalError → all symbols scored as skip).
    classic: dict = {"ma_cross": 0.0, "macd_mom": 0.0, "rsi_mom": 0.0, "trend_signal": 0.0}
    pair_sig, pair_z, pair_peer = 0.0, None, None

    f = _fundamental_snapshot(t)
    try:
        from fortress_universe import is_top100_equity
    except Exception:
        is_top100_equity = lambda _: False  # noqa: E731

    try:
        from analytics.rank_pipeline import RankInputs, build_buy_rank, use_unified_rank

        _unified_did_bottom_fisher = False
        if use_unified_rank():
            bench = _load_pair_closes("SPY", start_hist)
            rank = build_buy_rank(
                RankInputs(
                    ticker=t,
                    p_up=p_up,
                    exec_conf=exec_conf,
                    sent=sent,
                    news_factor=news_factor,
                    transcript_factor=transcript_factor,
                    mom_5d=mom_5d,
                    rs_spy=rs_spy,
                    vol_ratio=vol_ratio,
                    dip_signal=dip,
                    rally_signal=rally_signal,
                    hmm_market_score=hmm_market_score,
                    row=row_sig,
                    closes=closes_sig,
                    bench_closes=bench,
                    fund=f,
                    neural_p_up=neural_p_up,
                    top100=bool(is_top100_equity(t)),
                    start_hist=start_hist,
                    pair_closes_loader=lambda p: _load_pair_closes(p, start_hist),
                    crowd_meta={**(crowd_meta or {}), "macro_bundle": macro_bundle},
                ),
                runtime="paper",
            )
            score = rank.score
            if rank.meta.get("hedge_fund"):
                crowd_meta["hedge_fund"] = rank.meta["hedge_fund"]
                hf_meta = rank.meta["hedge_fund"]
                try:
                    tr = float(hf_meta.get("trend") or 0.0)
                    classic = {
                        "ma_cross": tr,
                        "macd_mom": tr,
                        "rsi_mom": tr,
                        "trend_signal": tr,
                    }
                    pair_z = hf_meta.get("pair_z")
                    pair_sig = float(hf_meta.get("stat_arb") or 0.0)
                except Exception:
                    pass
            # Unified path already applied structure + bottom_fisher — skip duplicate boosts below.
            _unified_did_bottom_fisher = "bottom_fisher" in (rank.meta.get("strategies") or []) or bool(
                rank.meta.get("bottom_fisher")
            )
            # Always skip post-hoc BF when unified ran (pipeline owns the hook).
            _unified_did_bottom_fisher = True
        else:
            raise ImportError("legacy rank path")
    except Exception:
        _unified_did_bottom_fisher = False
        score = _composite_score(p_up, mom_5d, rs_spy, vol_ratio, sent, dip_signal=dip)
        score += float(os.getenv("RANK_W_RALLY", "0.08")) * float(rally_signal)
        score += float(os.getenv("RANK_W_HMM_REGIME", "0.12")) * float(hmm_market_score)
        if is_top100_equity(t):
            try:
                from analytics.signal_enhance import top100_rank_score_boost, top100_score_multiplier

                score += top100_rank_score_boost(t)
                score *= top100_score_multiplier(True)
            except Exception:
                pass
        score += float(os.getenv("RANK_W_NEWS_FACTOR", "0.05")) * news_factor
        score += float(os.getenv("RANK_W_TRANSCRIPT_FACTOR", "0.0")) * transcript_factor
        score += float(os.getenv("RANK_W_FUND", "0.20")) * float(f.get("fund_score", 0.0))
        score += float(os.getenv("RANK_W_EXEC_CONF", "0.35")) * float(np.tanh((exec_conf - 0.5) * 4.0))
        use_hf = os.getenv("USE_HEDGE_FUND_STACK", "true").lower() in ("1", "true", "yes")
        if use_hf:
            # Single path: trend + pairs + MR + MM live inside hedge_fund_stack (no double-count).
            try:
                from analytics.hedge_fund_stack import hedge_fund_rank_boost

                bench = _load_pair_closes("SPY", start_hist)
                hf = hedge_fund_rank_boost(
                    t,
                    row=row_sig,
                    closes=closes_sig,
                    bench_closes=bench,
                    fund=f,
                    regime_score=float(hmm_market_score),
                    pair_closes_loader=lambda p: _load_pair_closes(p, start_hist),
                )
                score += float(os.getenv("RANK_W_HEDGE_FUND", "1.0")) * float(hf.boost)
                crowd_meta["hedge_fund"] = {
                    "boost": hf.boost,
                    "momentum": hf.momentum,
                    "value": hf.value,
                    "quality": hf.quality,
                    "stat_arb": hf.stat_arb,
                    "etf_dislocation": hf.etf_dislocation,
                    "trend": hf.trend,
                    "pair_z": hf.pair_z,
                }
                classic = {
                    "ma_cross": float(hf.trend),
                    "macd_mom": float(hf.trend),
                    "rsi_mom": float(hf.trend),
                    "trend_signal": float(hf.trend),
                }
                pair_z = hf.pair_z
                pair_sig = float(hf.stat_arb or 0.0)
            except Exception as e:
                log.debug("[PAPER] hedge_fund_stack %s: %s", t, e)
        else:
            classic = _classic_trend_momentum_signal(row_sig, closes_sig)
            pair_sig, pair_z, pair_peer = _pairs_stat_arb_signal(t, closes_sig, start_hist)
            score += float(os.getenv("RANK_W_TREND_CLASSIC", "0.12")) * float(classic["trend_signal"])
            score += float(os.getenv("RANK_W_PAIR_ARB", "0.18")) * float(pair_sig)
            crowd_meta["trend_classic"] = classic
            crowd_meta["pair_arb"] = {"sig": pair_sig, "z": pair_z, "peer": pair_peer}

    # --- Cramer boost (transcripts / Cramer-tagged news) ---
    cramer_factor = 0.0
    cramer_info: dict = {}
    cramer_strong_buy = False
    try:
        from intel.cramer_picks import cramer_boost_for, score_symbol_from_cramer

        cramer_info = score_symbol_from_cramer(t)
        cramer_factor = float(cramer_info.get("final_factor", 0.0))
        cramer_strong_buy = bool(cramer_info.get("high_conviction_buy", False))

        # Horizon-aware weighting: Cramer should not affect ultra-short trades (next-bar /
        # intraday "fluctuation" scalps), should be ~20% of day-to-week holds, and should
        # dominate (~70%) when he's table-pounding ("buy buy buy" / "one week").
        # 1-day trades get a *reduced* weight (he calls intraday on CNBC, but the holding
        # window is short so we don't want him to dominate) — set with RANK_W_CRAMER_1D.
        hold_default = float(os.getenv("HOLD_DAYS_DEFAULT", "5"))
        ultra_short_cutoff = float(os.getenv("CRAMER_ULTRA_SHORT_CUTOFF_DAYS", "1"))
        if hold_default < ultra_short_cutoff:
            cramer_weight = 0.0  # sub-day → HFT territory; Cramer does NOT apply
        elif hold_default < 2:
            cramer_weight = float(os.getenv("RANK_W_CRAMER_1D", "0.10"))
        else:
            cramer_weight = float(os.getenv("RANK_W_CRAMER", "0.05"))
        if cramer_strong_buy:
            cramer_weight = float(os.getenv("RANK_W_CRAMER_STRONG_BUY_SHARE", "0.08"))

        score += cramer_weight * float(cramer_boost_for(t))
        if cramer_strong_buy:
            # Additional explicit bump so the high-conviction pick ranks ahead even of strong p_up names.
            score += float(os.getenv("RANK_W_CRAMER_STRONG_BUY_BUMP", "0.04"))
    except Exception:
        cramer_info = {}

    # --- Power people (Trump / Fed / CEOs) + algorithm memory summary ---
    # Tiny bounded overlay. Dead-money names get a hard memory penalty.
    try:
        from intel.power_people import score_symbol_from_power_people

        pp_info = score_symbol_from_power_people(t)
        pp_w = float(os.getenv("RANK_W_POWER_PEOPLE", "0.04"))
        hold_d = float(os.getenv("HOLD_DAYS_DEFAULT", "5"))
        if hold_d < 1:
            pp_w = 0.0  # HFT / sub-day: no speech overlay
        score += pp_w * float(pp_info.get("final_factor") or 0.0)
        crowd_meta["power_people"] = pp_info
    except Exception:
        pass
    try:
        from intel.algo_memory import memory_boost_for, summary_for

        mem_w = float(os.getenv("RANK_W_ALGO_MEMORY", "0.03"))
        hold_d = float(os.getenv("HOLD_DAYS_DEFAULT", "5"))
        if hold_d < 1:
            mem_w = 0.0
        mem_b = float(memory_boost_for(t))
        score += mem_w * mem_b
        sm = summary_for(t)
        crowd_meta["algo_memory"] = {
            "boost": mem_b,
            "bullets": sm.get("bullets"),
            "dead_money": sm.get("dead_money"),
            "former_tickers": sm.get("former_tickers"),
        }
    except Exception:
        pass

    # Index ETF / passive overlay (allowed under RANK_W_INDEX_ETF + single-name cap / NO_REBUY)
    try:
        _idx_w = float(os.getenv("RANK_W_INDEX_ETF", "0") or 0)
        if _idx_w > 0:
            _ban_list = {
                x.strip().upper()
                for x in os.getenv(
                    "FORTRESS_NO_REBUY_SYMBOLS",
                    "SPY,QQQ,IWM,DIA,VOO,VTI,SOXX,XLK,XLF,XLE",
                ).split(",")
                if x.strip()
            }
            if t.upper() in _ban_list or t.upper().endswith("ETF"):
                # Mild positive when sleeve wants index exposure (regime/passive) — not monopoly
                score += _idx_w * 0.35
    except Exception:
        pass

    # Graham / Buffett book tilt (weekly/LT primarily via RANK_W_GRAHAM)
    try:
        _gw = float(os.getenv("RANK_W_GRAHAM", "0") or 0)
        if _gw > 0 and f:
            score += _gw * float(np.tanh(float(f.get("fund_score", 0.0))))
    except Exception:
        pass

    # --- Social sentiment (StockTwits public stream) ---
    social_factor = 0.0
    social_info: dict = {}
    try:
        from intel.social_sentiment import social_sentiment_score, social_boost_for

        social_info = social_sentiment_score(t)
        social_factor = float(social_info.get("score", 0.0))
        score += float(os.getenv("RANK_W_SOCIAL", "0.15")) * float(social_boost_for(t))
    except Exception:
        social_info = {}

    # --- Crowd + after-hours + counterparty (full algorithm, not family-forecast only) ---
    if os.getenv("USE_CROWD_BEHAVIOR", "true").lower() in ("1", "true", "yes"):
        try:
            from analytics.crowd_behavior import apply_investor_context

            vix_val = macro_bundle.get("vix") if macro_bundle else None
            fetch_ah = os.getenv("PAPER_SIM_AFTER_HOURS", "true").lower() in ("1", "true", "yes")
            crowd_meta = apply_investor_context(
                float(p_up),
                float(exec_conf),
                symbol=t,
                intended_side="buy",
                news_sentiment=float(sent),
                news_factor=float(news_factor),
                social_score=float(social_info.get("score", 0.0)),
                social_bull_share=float(social_info.get("bull_share", 0.5)),
                volume_ratio=float(vol_ratio),
                vix=float(vix_val) if vix_val is not None else None,
                fetch_after_hours=fetch_ah,
            )
            _ule_crowd = False
            try:
                from analytics.ultimate_learning_engine import enabled as _ue

                _ule_crowd = bool(_ue())
            except Exception:
                pass
            if not _ule_crowd:
                p_up = float(crowd_meta["p_up"])
            exec_conf = float(crowd_meta["execution_confidence"])
        except Exception as e:
            log.debug("[CROWD] %s adjustment skipped: %s", t, e)

    bull_bear_delta = 0.0
    if bull_bear:
        try:
            from analytics.market_regime_score import (
                apply_bull_bear_to_exec,
                apply_bull_bear_to_p_up,
                bull_bear_rank_boost,
            )

            p_up, bull_bear_delta = apply_bull_bear_to_p_up(float(p_up), bull_bear)
            exec_conf, _bb_e = apply_bull_bear_to_exec(float(exec_conf), bull_bear)
            score += float(os.getenv("RANK_W_BULL_BEAR", "0.12")) * bull_bear_rank_boost(bull_bear)
        except Exception as e:
            log.debug("[BULL_BEAR] %s skipped: %s", t, e)

    p_up_raw = float(p_up)
    from analytics.probability_calibrate import calibrate_horizon_probs, calibrate_probability

    # When ULE on: fuse first on raw model belief, calibrate after for display/gates
    _ule_here = False
    try:
        from analytics.ultimate_learning_engine import enabled as _ule_en2

        _ule_here = bool(_ule_en2())
    except Exception:
        _ule_here = False

    if not _ule_here:
        cal_main = calibrate_probability(p_up_raw)
        p_up = float(cal_main["calibrated"])
    else:
        p_up = float(p_up_raw)
        cal_main = {"calibrated": p_up, "raw": p_up_raw}

    try:
        from analytics.ultimate_learning_engine import apply_to_p_up as ule_apply, enabled as ule_on

        if ule_on():
            bb_sc = None
            if bull_bear and isinstance(bull_bear, dict):
                bb_sc = bull_bear.get("score", bull_bear.get("bull_bear_score"))
            p_up, _ule = ule_apply(
                t,
                float(p_up),
                context={
                    "rsi_14": float(row_sig.get("rsi_14", 50) or 50),
                    "p_up_base": float(p_up),
                    "news_factor": float(news_factor),
                    "neural_p_up": float(neural_p_up) if neural_p_up is not None else None,
                    "crowd_pressure": float((crowd_meta or {}).get("crowd_pressure") or 0.0),
                    "bull_bear_score": bb_sc,
                    "p_short_model": float(ps) if ps is not None else None,
                    "p_long_model": float(pl) if pl is not None else None,
                },
            )
            cal_main = calibrate_probability(float(p_up))
            p_up = float(cal_main["calibrated"])
        else:
            from analytics.hidden_pattern_anomaly import hidden_pattern_p_blend

            p_up, _hp = hidden_pattern_p_blend(t, float(p_up))
    except Exception:
        try:
            from analytics.hidden_pattern_anomaly import hidden_pattern_p_blend

            p_up, _hp = hidden_pattern_p_blend(t, float(p_up))
        except Exception:
            pass
    chance_pct = int(max(1, min(99, round(100.0 * float(p_up)))))
    horizon_cal = calibrate_horizon_probs(
        p_daily=p_daily_raw,
        p_short=float(ps) if ps is not None else None,
        p_long=float(pl) if pl is not None else None,
        p_xlong=p_xlong_raw,
        p_daily_head=p_daily_head,
        p_short_head="model_short" if ps is not None else None,
        p_long_head="model_long" if pl is not None else None,
        p_xlong_head=p_xlong_head,
    )

    from signals.undercut_rally import detect_undercut_rally
    ur = detect_undercut_rally(df.iloc[:-1])  # signal bar = T-1, no look-ahead
    score += float(os.getenv("RANK_W_UR", "0.25")) * float(ur.score)

    bottom_fisher_boost = 0.0
    bottom_fisher_meta: dict = {}
    if not _unified_did_bottom_fisher:
        try:
            from bottom_fisher.integrate import bottom_fisher_score_boost

            bottom_fisher_boost, bottom_fisher_meta = bottom_fisher_score_boost(t)
            if bottom_fisher_boost > 0:
                score += bottom_fisher_boost
        except Exception:
            pass
    else:
        # Pull meta from last unified rank if available for logging
        try:
            bottom_fisher_meta = dict((rank.meta or {}).get("bottom_fisher") or {})
            bottom_fisher_boost = float((rank.components or {}).get("bottom_fisher") or 0.0)
        except Exception:
            pass

    ai_ipo_proxy = False
    try:
        from tools.ai_ipo_autopilot import autopilot_enabled, is_proxy_ticker, paper_proxy_score_boost

        if autopilot_enabled() and is_proxy_ticker(t):
            ai_ipo_proxy = True
            score += paper_proxy_score_boost()
    except Exception:
        pass

    macro_score = 0.0
    spread_10y2y = None
    if macro_bundle:
        macro_score = float(macro_bundle.get("macro_score") or 0.0)
        spread_10y2y = macro_bundle.get("spread_10y2y")
        score += float(os.getenv("RANK_W_MACRO", "0.12")) * float(np.tanh(macro_score * 1.8))
    # Sleeve curriculum soft boosts (weekly/longterm) — RANK_W_INFLATION / RATE_CYCLE / BUY_HOLD / ALT
    try:
        from analytics.rank_pipeline import curriculum_soft_boosts
        from analytics.sleeve_weights import apply_sleeve_env, resolve_sleeve

        _sleeve = resolve_sleeve()
        apply_sleeve_env(_sleeve)
        for _k, _v in curriculum_soft_boosts(
            sleeve=_sleeve,
            macro_bundle=macro_bundle,
            fund_score=float(f.get("fund_score", 0.0)) if f else 0.0,
        ).items():
            score += float(_v)
    except Exception:
        pass

    ind_headlines: list[str] = []
    if news_intel:
        for key in ("top_bullish", "top_bearish", "key_good", "key_bad"):
            ind_headlines.extend(news_intel.get(key) or [])
        ind_headlines = list(dict.fromkeys(str(h) for h in ind_headlines if h))[:20]

    try:
        from analytics.industry_comovement import industry_rank_adjustment

        ind_adj = industry_rank_adjustment(
            t,
            row_sig,
            macro_bundle=macro_bundle,
            news_headlines=ind_headlines or None,
        )
        score += float(ind_adj.get("score_delta") or 0.0)
    except Exception:
        ind_adj = {}

    try:
        from analytics.industries.project_wiring import wire_score

        row_rf = row_sig.to_dict() if hasattr(row_sig, "to_dict") else dict(row_sig)
        score, p_up, _pipe_meta = wire_score(
            t,
            score,
            p_up,
            row_rf,
            macro_bundle=macro_bundle,
            news_headlines=ind_headlines or None,
            apply_pipeline=False,
        )
    except Exception:
        _pipe_meta = ind_adj if ind_adj else {}

    if crowd_meta:
        score += float(os.getenv("RANK_W_CROWD", "0.10")) * float(crowd_meta.get("rank_boost", 0.0))
        score += float(os.getenv("RANK_W_AFTER_HOURS", "0.15")) * float(crowd_meta.get("ah_rank_boost", 0.0))

    if news_intel:
        try:
            from intel.news_ai_agent import score_adjustments

            p_delta, s_delta = score_adjustments(news_intel)
            if p_delta:
                p_up = max(0.0, min(1.0, float(p_up) + float(p_delta)))
            if s_delta:
                score += float(s_delta)
        except Exception:
            pass

    insider_meta: dict = {}
    try:
        from intel.insider_signals import assess_insider_flow

        insider_meta = assess_insider_flow(t)
        score += float(insider_meta.get("score_delta") or 0.0)
        p_up = max(0.0, min(1.0, float(p_up) + float(insider_meta.get("p_up_delta") or 0.0)))
    except Exception:
        insider_meta = {}

    if os.getenv("USE_UNIQUE_PLAYBOOK", "true").lower() in ("1", "true", "yes"):
        try:
            from intel.unique_style_playbook import unique_rank_boost

            u_boost, _u_meta = unique_rank_boost(t, metrics={"p_up": float(p_up)})
            score += float(u_boost or 0.0)
        except Exception:
            pass

    institutional_meta: dict = {}
    try:
        from intel.institutional_flow_signals import assess_institutional_flow

        inst_docs: list[str] = []
        if news_intel:
            for key in ("top_bullish", "key_good", "headlines", "top_bearish", "key_bad"):
                inst_docs.extend(news_intel.get(key) or [])
        institutional_meta = assess_institutional_flow(t, documents=inst_docs or None)
        score += float(institutional_meta.get("score_delta") or 0.0)
        p_up = max(0.0, min(1.0, float(p_up) + float(institutional_meta.get("p_up_delta") or 0.0)))
        if institutional_meta.get("boost_long") and news_intel is not None:
            news_intel = dict(news_intel)
            news_intel["boost_long"] = True
            news_intel["institutional_flow"] = institutional_meta
    except Exception:
        institutional_meta = {}

    defensive_meta: dict = {}
    try:
        from intel.earnings_defensive_signals import assess_pre_earnings_defensive

        def_docs: list[str] = []
        if news_intel:
            for key in ("top_bearish", "key_bad", "headlines"):
                def_docs.extend(news_intel.get(key) or [])
        defensive_meta = assess_pre_earnings_defensive(t, documents=def_docs or None)
        score += float(defensive_meta.get("score_delta") or 0.0)
        p_up = max(0.0, min(1.0, float(p_up) + float(defensive_meta.get("p_up_delta") or 0.0)))
    except Exception:
        defensive_meta = {}

    from analytics.execution_confidence import (
        min_execution_confidence,
        passes_confidence_gates,
    )
    from analytics.asymmetric_meta_filter import asymmetric_decision

    min_exec = min_execution_confidence()
    if crowd_meta.get("min_exec_effective") is not None:
        min_exec = float(crowd_meta["min_exec_effective"])
    asym = asymmetric_decision(
        float(p_up),
        float(exec_conf),
        float(min_exec),
        p_short_model=float(ps) if ps is not None else None,
        p_long_model=float(pl) if pl is not None else None,
    )
    gate_parts: list[str] = []
    if asym.action == "NO_TRADE":
        gate_parts.append(f"asym:{asym.rationale}")
    if not passes_confidence_gates(float(p_up), float(exec_conf), float(min_p), float(min_exec)):
        gate_parts.append("conf_low")
    if block_long_on_sentiment(sent, symbol=t):
        gate_parts.append("sent_block")
    if news_intel.get("block_long"):
        gate_parts.append("ai_news_block")
    elif news_intel.get("narrative") == "bad_news":
        gate_parts.append("ai_bad_news")
    if crowd_meta.get("crowd_block_fomo"):
        gate_parts.append("crowd_fomo")
    if crowd_meta.get("ah_tilt") is not None and float(crowd_meta.get("ah_tilt", 0)) <= float(
        os.getenv("AH_BLOCK_LONG_TILT", "-0.35")
    ):
        gate_parts.append("ah_against")
    if not vol_ok:
        gate_parts.append("volume")
    if use_mtf and not mtf_ok:
        gate_parts.append("mtf")
    if scale <= 0:
        gate_parts.append("regime_scale")
    if insider_meta.get("block_long"):
        gate_parts.append("insider_sell")
    if defensive_meta.get("block_long"):
        gate_parts.append("earnings_defensive")
    try:
        from intel.near_term_headwinds import assess_near_term_headwind

        hw = assess_near_term_headwind(t, closes=closes_sig, mom_5d=mom_5d)
        if hw["p_penalty"] > 0:
            p_up = max(0.05, float(p_up) - float(hw["p_penalty"]))
            score -= float(hw["score_penalty"])
        if hw["block_playbook"]:
            gate_parts.append("headwind")
    except Exception:
        hw = {}
    try:
        from intel.downward_pressure import assess_downward_pressure

        dp = assess_downward_pressure(t)
        if dp.get("block_new_buy") or (
            dp.get("tighten_exit") and not dp.get("counter_signal")
        ):
            gate_parts.append("downward_pressure")
            score -= 0.5
        elif dp.get("tighten_exit"):
            score -= float(dp.get("pressure_score") or 0) * 0.25
    except Exception:
        dp = {}
    _ef_dte = None
    try:
        from intel.historical_events import event_features

        _ef = event_features(t)
        if _ef.get("days_to_earnings") is not None:
            _ef_dte = _ef.get("days_to_earnings")
    except Exception:
        pass
    risk_meta: dict = {}
    try:
        from intel.algo_risk_filter import screen_buy_risk

        risk_meta = screen_buy_risk(t, hold_days=int(os.getenv("HOLD_DAYS_DEFAULT", "5")))
        if not risk_meta.get("approved"):
            gate_parts.append(f"risk:{risk_meta.get('rule')}")
    except Exception:
        pass
    gate_detail = "+".join(gate_parts) if gate_parts else "all_ok"

    atr = float(row_sig.get("atr_14", sig_close * 0.02))
    stop = sig_close - atr * float(os.getenv("ATR_STOP_MULT", "1.5")) * regime.stop_widen

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    if elapsed_ms >= int(os.getenv("DEBUG_SCORE_SYMBOL_SLOW_MS", "1500")):
        log.debug(
            "[PAPER_SIM] slow score %s %dms features=%d intel=%d predict=%d",
            t,
            elapsed_ms,
            int((t_after_features - t0) * 1000),
            int((t_after_intel - t_after_features) * 1000),
            int((t_after_predict - t_after_intel) * 1000),
        )

    earn_dte = None
    earn_nxt = None
    try:
        from intel.historical_events import earnings_event

        es = earnings_event(t)
        earn_dte = es.get("days_to")
        earn_nxt = es.get("next_date")
    except Exception:
        try:
            from intel.earnings_calendar import earnings_snapshot

            es = earnings_snapshot(t)
            earn_dte = es.get("days_to_earnings")
            earn_nxt = es.get("next_earnings_date")
        except Exception:
            pass
    if earn_dte is None and _ef_dte is not None:
        earn_dte = _ef_dte
    if earn_dte is None:
        raw_dte = row_sig.get("days_to_earnings")
        try:
            if raw_dte is not None and float(raw_dte) != float(os.getenv("EARNINGS_NEUTRAL_DTE", "90")):
                earn_dte = int(float(raw_dte))
        except (TypeError, ValueError):
            pass

    # Catalyst ↔ horizon: near earnings only boosts matching sleeve (weekly≠overnight binary)
    try:
        from analytics.catalyst_horizon import earnings_rank_boost
        from analytics.sleeve_weights import resolve_sleeve

        _sl = resolve_sleeve(hold_days=int(os.getenv("HOLD_DAYS_DEFAULT", "5")))
        if earn_dte is not None and int(earn_dte) <= int(os.getenv("EARNINGS_PRE_HOLD_BUFFER_DAYS", "2")):
            _eb, _em = earnings_rank_boost(
                days_to=earn_dte,
                p_adj=float(p_up),
                sleeve=_sl,
                stick=True,
            )
            score += float(_em.get("applied") or 0.0)
    except Exception:
        pass

    return {
        "ticker": t,
        "skipped": False,
        "signal_date": sig_date,
        "outcome_date": out_date,
        "p_up": float(p_up),
        "p_up_raw": float(p_up_raw),
        "chance_pct": int(chance_pct),
        "p_down": float(1.0 - p_up),
        "conviction": float(abs(float(p_up) - 0.5) * 2.0),
        "p_short_model": float(ps) if ps is not None else None,
        "p_long_model": float(pl) if pl is not None else None,
        **horizon_cal,
        "bull_bear_score": float(bull_bear.get("bull_bear_score", 0.0)) if bull_bear else 0.0,
        "bull_bear_label": str(bull_bear.get("bull_bear_label", "")) if bull_bear else "",
        "bull_bear_delta": float(bull_bear_delta),
        "execution_confidence": float(exec_conf),
        "min_execution_confidence": float(min_exec),
        "asym_action": (
            "NO_TRADE"
            if hw.get("block_playbook") or not risk_meta.get("approved", True)
            else str(asym.action)
        ),
        "asym_rationale": (
            f"headwind: {'; '.join((hw.get('reasons') or [])[:2])}"
            if hw.get("block_playbook")
            else str(risk_meta.get("reason") or asym.rationale)
            if not risk_meta.get("approved", True)
            else str(asym.rationale)
        ),
        "long_threshold": float(asym.long_threshold),
        "short_threshold": float(asym.short_threshold),
        "ur_score": float(ur.score),
        "ur_detected": bool(ur.detected),
        "ur_pivot_low": float(ur.pivot_low) if ur.pivot_low == ur.pivot_low else None,
        "ur_pivot_age_bars": int(ur.pivot_age_bars),
        "ur_undercut_depth_pct": float(ur.undercut_depth_pct),
        "ur_reclaim_pct": float(ur.reclaim_pct),
        "ur_volume_expansion": float(ur.volume_expansion),
        "ur_trend_ok": bool(ur.trend_ok),
        "ur_rationale": str(ur.rationale),
        "macro_score": float(macro_score),
        "fred_spread_10y2y": spread_10y2y,
        "fred_ok": bool(macro_bundle.get("ok")) if macro_bundle else False,
        "score": float(score),
        "bottom_fisher_boost": float(bottom_fisher_boost),
        "bottom_fisher": bool(bottom_fisher_meta.get("bottom_fisher")),
        "bottom_recovery_score": bottom_fisher_meta.get("recovery_score"),
        "bottom_catalyst_score": bottom_fisher_meta.get("catalyst_score"),
        "bottom_ai_grade": bottom_fisher_meta.get("ai_grade"),
        "ai_ipo_proxy": bool(ai_ipo_proxy),
        "dip_signal": float(dip),
        "rally_signal": float(rally_signal),
        "rally_continuation": bool(rally_continuation),
        "momentum_ret_1d": float(momentum_ret_1d),
        "fwd_1d_return": float(fwd_ret),
        "fwd_5d_return": fwd_5d_ret,
        "fwd_10d_return": fwd_10d_ret,
        "fwd_20d_return": fwd_20d_ret,
        "momentum_5d": float(mom_5d),
        "rs_spy": float(rs_spy),
        "volume_ratio": float(vol_ratio),
        "sentiment": float(sent),
        "news_factor": float(news_factor),
        "transcript_factor": float(transcript_factor),
        "cramer_factor": float(cramer_factor),
        "cramer_mentions": int(cramer_info.get("mentions", 0)) if isinstance(cramer_info, dict) else 0,
        "cramer_high_conviction": bool(cramer_strong_buy),
        "cramer_last_strong_date": cramer_info.get("last_strong_date") if isinstance(cramer_info, dict) else None,
        "social_factor": float(social_factor),
        "social_n_msgs": int(social_info.get("n_messages", 0)) if isinstance(social_info, dict) else 0,
        "crowd_pressure": float(crowd_meta.get("crowd_pressure", 0.0)),
        "crowd_behavior": str(crowd_meta.get("crowd_behavior", "")),
        "expected_crowd_action": str(crowd_meta.get("expected_crowd_action", "")),
        "crowd_p_up_delta": float(crowd_meta.get("p_up_delta", 0.0)),
        "crowd_exec_delta": float(crowd_meta.get("execution_confidence_delta", 0.0)),
        "crowd_block_fomo": bool(crowd_meta.get("crowd_block_fomo", False)),
        "ah_return_pct": float(crowd_meta.get("ah_return_pct", 0.0)),
        "ah_tilt": float(crowd_meta.get("ah_tilt", 0.0)),
        "ah_session": str(crowd_meta.get("ah_session", "")),
        "ah_investor_read": str(crowd_meta.get("ah_investor_read", "")),
        "counterparty_read": str(crowd_meta.get("counterparty_read", "")),
        "counterparty_side": str(crowd_meta.get("counterparty_side", "")),
        "trend_classic_signal": float(classic["trend_signal"]),
        "ma_cross_signal": float(classic["ma_cross"]),
        "macd_signal": float(classic["macd_mom"]),
        "rsi_momentum_signal": float(classic["rsi_mom"]),
        "pair_arb_signal": float(pair_sig),
        "pair_arb_z": float(pair_z) if pair_z is not None else None,
        "pair_peer": pair_peer,
        "hmm_market_signal": float(hmm_market_score),
        "sig_close": float(sig_close),
        "atr_14": float(atr),
        "stop": float(stop),
        "gate_detail": gate_detail,
        "vol_ok": bool(vol_ok),
        "mtf_ok": bool(mtf_ok),
        "rl_hint": rl_hint,
        "lstm_p_up": lstm_p_up,
        "foundation_p_up": foundation_p_up,
        "foundation_source": foundation_source,
        "foundation_blend_w": float(foundation_blend_w),
        "top100": bool(top100),
        "top100_rank": top100_rank(t) if top100 else None,
        "neural_p_up": neural_p_up,
        "neural_breakdown": neural_breakdown,
        "online_state": neural_state,
        "near_term_headwind": hw if hw else None,
        "algo_risk": risk_meta if risk_meta else None,
        "trade_constraints": (risk_meta or {}).get("trade_constraints"),
        "algo_risk_warnings": (risk_meta or {}).get("warnings"),
        "hold_days_effective": (risk_meta or {}).get("hold_days"),
        "news_ai": news_intel if news_intel else None,
        "insider_signal": insider_meta if insider_meta else None,
        "institutional_flow": institutional_meta if institutional_meta else None,
        "earnings_defensive": defensive_meta if defensive_meta else None,
        "days_to_earnings": earn_dte,
        "next_earnings_date": earn_nxt or news_intel.get("next_earnings_date"),
        **f,
    }


def _market_leaderboard(scored: list[dict], k: int = 15) -> dict:
    fwd_rows = [r for r in scored if "fwd_1d_return" in r]
    winners = sorted(fwd_rows, key=lambda r: -r["fwd_1d_return"])[:k]
    losers = sorted(fwd_rows, key=lambda r: r["fwd_1d_return"])[:k]
    return {
        "top_winners": [
            {"ticker": r["ticker"], "fwd_1d_return": round(r["fwd_1d_return"], 6), "p_up": round(r.get("p_up", 0), 4)}
            for r in winners
        ],
        "top_losers": [
            {"ticker": r["ticker"], "fwd_1d_return": round(r["fwd_1d_return"], 6), "p_up": round(r.get("p_up", 0), 4)}
            for r in losers
        ],
    }


def _asym_filter_metrics(tradeable: list[dict]) -> dict:
    """Phase 10 yield / precision: how often asym zones align with next-bar direction."""

    def _prec(rows: list[dict], pred) -> float | None:
        if not rows:
            return None
        hits = sum(1 for r in rows if pred(r))
        return float(hits / len(rows))

    long_zone = [r for r in tradeable if r.get("asym_action") == "LONG"]
    short_zone = [r for r in tradeable if r.get("asym_action") == "SHORT"]
    no_trade = [r for r in tradeable if r.get("asym_action") == "NO_TRADE"]

    def _long_hit(r: dict) -> bool:
        return float(r.get("fwd_1d_return") or 0.0) > 0.0

    def _short_hit(r: dict) -> bool:
        return float(r.get("fwd_1d_return") or 0.0) < 0.0

    return {
        "n_scored": len(tradeable),
        "n_asym_long_zone": len(long_zone),
        "n_asym_short_zone": len(short_zone),
        "n_asym_no_trade": len(no_trade),
        "yield_long_zone_frac": len(long_zone) / max(len(tradeable), 1),
        "yield_short_zone_frac": len(short_zone) / max(len(tradeable), 1),
        "yield_no_trade_frac": len(no_trade) / max(len(tradeable), 1),
        "hypothetical_long_zone_precision": _prec(long_zone, _long_hit),
        "hypothetical_short_zone_precision": _prec(short_zone, _short_hit),
    }


def _paper_sim_history_start() -> str:
    """Rolling lookback for scoring — not full re-download from 2018 every loop."""
    raw = os.getenv("PAPER_SIM_LOOKBACK_DAYS", "").strip()
    if raw.isdigit() and int(raw) >= 120:
        from datetime import timedelta

        d = datetime.now(timezone.utc).date() - timedelta(days=int(raw))
        return d.strftime("%Y-%m-%d")
    return os.getenv("PAPER_SIM_START", "2018-01-01")


def _signal_bar_date(spy_df) -> str:
    if spy_df is None or len(spy_df) < 2:
        return ""
    try:
        return str(spy_df.index[-2].date())
    except Exception:
        return ""


def _acquire_paper_sim_lock():
    """Only one full-universe scan at a time (weekly + longterm daemons overlap otherwise)."""
    if os.getenv("PAPER_SIM_SINGLE_FLIGHT", "true").lower() not in ("1", "true", "yes"):
        return object()  # sentinel — no real lock
    import fcntl

    lock_path = Path("data/paper_sim.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except BlockingIOError:
        os.close(fd)
        return None


def _release_paper_sim_lock(lock_fd) -> None:
    if lock_fd is None or not isinstance(lock_fd, int):
        return
    import fcntl

    try:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)
    except OSError:
        pass


def run_paper_simulation_today(max_symbols: int | None = None) -> dict:
    lock_fd = _acquire_paper_sim_lock()
    if lock_fd is None:
        from analytics.paper_report import latest_valid_report

        log.warning("[PAPER_SIM] another scan in progress — skipping duplicate run")
        _path, prev = latest_valid_report(min_rows=1, require_usable=False)
        if prev:
            return prev
        return {"error": "paper_sim_locked", "symbols_scored": 0, "rows": []}
    try:
        return _run_paper_simulation_today_body(max_symbols, lock_fd=lock_fd)
    finally:
        _release_paper_sim_lock(lock_fd)


def _run_paper_simulation_today_body(max_symbols: int | None, *, lock_fd) -> dict:
    hold_days_cfg = int(os.getenv("HOLD_DAYS_DEFAULT", "5"))
    try:
        from analytics.market_session import swing_buy_allowed

        # Off-hours score refresh for family-forecast / overnight ops (no order placement here).
        allow_off = os.getenv("PAPER_SIM_ALLOW_OFFHOURS", "false").lower() in (
            "1",
            "true",
            "yes",
        )
        swing_ok, swing_reason = swing_buy_allowed(hold_days=hold_days_cfg)
        if not swing_ok and not allow_off:
            log.info(
                "[PAPER_SIM] skip run — %dd hold blocked outside open/close window (%s)",
                hold_days_cfg,
                swing_reason,
            )
            return {
                "skipped": True,
                "skip_reason": swing_reason,
                "hold_days": hold_days_cfg,
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "symbols_scored": 0,
                "rows": [],
                "note": "Swing/long hold scans only run at market open or close — not midday.",
            }
        if allow_off and not swing_ok:
            log.info(
                "[PAPER_SIM] off-hours score refresh (PAPER_SIM_ALLOW_OFFHOURS) — would block orders: %s",
                swing_reason,
            )
    except Exception as e:
        log.debug("[PAPER_SIM] swing window check: %s", e)

    if os.getenv("USE_NEURAL_ENSEMBLE", "true").lower() in ("1", "true", "yes"):
        try:
            from online_learning.neural_ensemble import bootstrap_replay_from_reports

            seeded = int(bootstrap_replay_from_reports(max_files=int(os.getenv("NEURAL_BOOTSTRAP_DAYS", "14"))))
            if seeded > 0:
                log.info("[NEURAL] bootstrapped %d replay samples from reports/", seeded)
        except Exception as e:
            log.debug("[NEURAL] bootstrap skipped: %s", e)

    os.environ["PAPER_SIM_ACTIVE_RUN"] = "true"
    if os.getenv("PAPER_SIM_SHARE_MONTHLY_DD", "false").lower() not in (
        "1",
        "true",
        "yes",
    ):
        os.environ["MONTHLY_EQUITY_STATE_FILE"] = str(
            Path(__file__).resolve().parent / "data" / "risk" / "monthly_equity_paper_sim.json"
        )
    if os.getenv("PAPER_SIM_FORCE_YAHOO", "false").lower() in ("1", "true", "yes"):
        os.environ["PRICE_DATA_SOURCE"] = "yfinance"
        os.environ["FORCE_YAHOO_PRICES"] = "true"
    else:
        os.environ["USE_PRICE_CACHE"] = "true"
        os.environ["FORCE_YAHOO_PRICES"] = "false"
        if os.getenv("POLYGON_API_KEY", "").strip() and os.getenv("PAPER_SIM_USE_POLYGON", "true").lower() in (
            "1",
            "true",
            "yes",
        ):
            os.environ["PRICE_DATA_SOURCE"] = "hybrid_polygon"
        elif os.getenv("ALPACA_API_KEY", "").strip():
            os.environ["PRICE_DATA_SOURCE"] = "hybrid_alpaca"

    syms = _resolve_universe(max_symbols)
    syms = _order_for_scoring(syms)
    head = syms[: min(12, len(syms))]
    log.info(
        "[PAPER_SIM] universe n=%d  scan_head=%s  (hash-shuffle order)",
        len(syms),
        ",".join(head),
    )
    if _env_bool("PAPER_SIM_SHUFFLE_UNIVERSE", False):
        seed_s = os.getenv("PAPER_SIM_SHUFFLE_SEED", "").strip()
        seed = seed_s or datetime.now(timezone.utc).strftime("%Y%m%d")
        rnd = random.Random(seed)
        syms = list(syms)
        rnd.shuffle(syms)
        log.info("[PAPER_SIM] symbol order shuffled (seed=%s)", seed)

    spy = _spy_df()
    if isinstance(spy.columns, pd.MultiIndex):
        spy.columns = [c[0] for c in spy.columns]
    regime = simple_regime_from_spy(spy)
    scale = regime.position_scale
    hmm_market_score = _hmm_market_regime_score(spy)
    log.info("[PAPER_SIM] HMM market signal=%.3f", hmm_market_score)

    try:
        from signals.fred_macro import get_macro_bundle

        macro_bundle = get_macro_bundle()
    except Exception:
        macro_bundle = {"macro_score": 0.0, "ok": False, "spread_10y2y": None}

    from analytics.market_regime_score import analyze_bull_bear_market

    bull_bear = analyze_bull_bear_market(regime, macro_bundle, hmm_market_score)
    log.info(
        "[PAPER_SIM] market %s score=%.2f  %s",
        bull_bear.get("bull_bear_label"),
        float(bull_bear.get("bull_bear_score", 0.0)),
        bull_bear.get("bull_bear_read"),
    )

    mode = os.getenv("PAPER_SIM_MODE", "all_good").strip().lower()
    top_k = int(os.getenv("PAPER_SIM_TOP_K", "10"))
    min_p = float(os.getenv("PAPER_SIM_MIN_CONF", os.getenv("MIN_MODEL_CONFIDENCE", "0.55")))
    start_hist = _paper_sim_history_start()
    signal_date = _signal_bar_date(spy)
    use_risk_check = os.getenv("PAPER_SIM_RISK_CHECK", "true").lower() in ("1", "true", "yes")
    allow_shorts = os.getenv("PAPER_SIM_ALLOW_SHORTS", "false").lower() in ("1", "true", "yes")
    short_top_k = int(os.getenv("PAPER_SIM_SHORT_TOP_K", "5"))
    use_notional = os.getenv("PAPER_SIM_USE_NOTIONAL", "true").lower() in ("1", "true", "yes")
    notional = float(os.getenv("ORDER_NOTIONAL", "500"))
    qty = max(1, int(float(os.getenv("ORDER_QUANTITY", "1")) * scale))
    rm = RiskManager(equity=float(os.getenv("PAPER_EQUITY", "100000")))

    from analytics.execution_confidence import (
        confidence_gate_mode,
        min_execution_confidence,
        passes_confidence_gates,
        passes_directional_gates,
    )

    min_exec = float(min_execution_confidence())

    def _passes_pick_conf(r: dict) -> bool:
        return passes_confidence_gates(
            float(r["p_up"]),
            float(r.get("execution_confidence", 0.0)),
            float(min_p),
            float(min_exec),
        )

    def _passes_directional_conf(r: dict) -> bool:
        return passes_directional_gates(
            float(r["p_up"]),
            float(r.get("execution_confidence", 0.0)),
            float(min_p),
            float(min_exec),
            allow_short=bool(allow_shorts),
        )

    workers = max(1, int(os.getenv("PAPER_SIM_WORKERS", "3")))
    src = _price_source()
    if src == "hybrid_polygon":
        workers = min(workers, int(os.getenv("PAPER_SIM_POLYGON_MAX_WORKERS", "1")))
    elif src in ("yfinance", "hybrid_alpaca") and os.getenv(
        "PAPER_SIM_FORCE_YAHOO", "false"
    ).lower() not in (
        "1",
        "true",
        "yes",
    ):
        workers = min(workers, int(os.getenv("PAPER_SIM_YAHOO_MAX_WORKERS", "3")))
    elif src == "yfinance":
        workers = min(workers, int(os.getenv("PAPER_SIM_YAHOO_MAX_WORKERS", "2")))
    log.info("[PAPER_SIM] price_source=%s workers=%d", src, workers)

    scored: list[dict] = []
    n_skipped = 0
    failed_syms: list[str] = []
    score_loop_t0 = time.perf_counter()

    from analytics.paper_incremental import plan_incremental_rescore

    universe_n = len(syms)
    reused_rows, syms, inc_meta = plan_incremental_rescore(syms, signal_date=signal_date)
    if inc_meta.get("enabled"):
        log.info(
            "[PAPER_SIM] incremental reuse=%d rescore=%d signal=%s prev=%s",
            inc_meta.get("reused", 0),
            inc_meta.get("rescored", 0),
            signal_date,
            inc_meta.get("prev_report", ""),
        )
    scored.extend(reused_rows)

    def _run_score(t: str) -> dict | None:
        return _score_symbol(
            t,
            regime,
            rm,
            scale,
            min_p,
            start_hist,
            hmm_market_score=hmm_market_score,
            macro_bundle=macro_bundle,
            bull_bear=bull_bear,
        )

    def _consume_score(t: str, r: dict | None) -> None:
        nonlocal n_skipped
        if r is None:
            failed_syms.append(t)
            n_skipped += 1
            return
        if r.get("skipped"):
            failed_syms.append(t)
            n_skipped += 1
        scored.append(r)

    if workers > 1 and len(syms) > 1:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        log.info("[PAPER_SIM] parallel scoring workers=%d symbols=%d", workers, len(syms))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {pool.submit(_run_score, t): t for t in syms}
            done = 0
            for fut in as_completed(futs):
                done += 1
                if done % 50 == 0:
                    log.info("[PAPER_SIM] scored %d / %d", done, len(syms))
                t = futs[fut]
                try:
                    _consume_score(t, fut.result())
                except Exception as e:
                    log.warning("[PAPER_SIM] %s skipped: %s", t, e)
                    try:
                        from tools.tier2_retrain_queue import enqueue
                        enqueue([t], note="paper_sim score error")
                    except Exception:
                        pass
                    failed_syms.append(t)
                    n_skipped += 1
    else:
        for i, t in enumerate(syms, 1):
            if i % 50 == 0:
                log.info("[PAPER_SIM] scored %d / %d", i, len(syms))
            try:
                _consume_score(t, _run_score(t))
            except Exception:
                log.exception("[PAPER_SIM] %s", t)
                failed_syms.append(t)
                n_skipped += 1

    if failed_syms and os.getenv("PAPER_SIM_RETRY_SKIPPED", "true").lower() in ("1", "true", "yes"):
        try:
            from fortress_universe import load_top100_symbols

            top_set = frozenset(load_top100_symbols())
        except Exception:
            top_set = frozenset()
        retry_cap = int(os.getenv("PAPER_SIM_RETRY_MAX", "80"))
        retry = [s for s in dict.fromkeys(failed_syms) if s in top_set][:retry_cap]
        if not retry and failed_syms:
            retry = list(dict.fromkeys(failed_syms))[: min(retry_cap, 40)]
        if retry:
            log.warning("[PAPER_SIM] retrying %d skipped symbols (top100-first)", len(retry))
            retry_rows: list[dict] = []
            if workers > 1 and len(retry) > 1:
                from concurrent.futures import ThreadPoolExecutor, as_completed

                with ThreadPoolExecutor(max_workers=min(workers, 4)) as pool:
                    futs = {pool.submit(_run_score, t): t for t in retry}
                    for fut in as_completed(futs):
                        t = futs[fut]
                        try:
                            r = fut.result()
                            if r is not None and not r.get("skipped"):
                                retry_rows.append(r)
                        except Exception as e:
                            log.warning("[PAPER_SIM] retry %s failed: %s", t, e)
            else:
                for t in retry:
                    try:
                        r = _run_score(t)
                        if r is not None and not r.get("skipped"):
                            retry_rows.append(r)
                    except Exception:
                        pass
            if retry_rows:
                by_t = {str(r.get("ticker", "")).upper(): r for r in scored if r.get("ticker")}
                for r in retry_rows:
                    t = str(r.get("ticker", "")).upper()
                    if not t:
                        continue
                    prev = by_t.get(t)
                    if prev and prev.get("skipped") and not r.get("skipped"):
                        n_skipped = max(0, n_skipped - 1)
                    elif t not in by_t:
                        n_skipped = max(0, n_skipped - 1)
                    by_t[t] = r
                scored = list(by_t.values())
                log.info("[PAPER_SIM] retry recovered %d symbols", len(retry_rows))

    score_loop_ms = int((time.perf_counter() - score_loop_t0) * 1000)
    log.info(
        "[PAPER_SIM] score loop done symbols=%d ms=%d avg=%dms skipped=%d",
        len(syms),
        score_loop_ms,
        int(score_loop_ms / max(len(syms), 1)),
        n_skipped,
    )

    tradeable = [r for r in scored if not r.get("skipped") and "score" in r]

    # --- Cramer high-conviction force buys (pre-empt before any mode logic) ---
    cramer_force_buys: list[dict] = []
    if os.getenv("CRAMER_FORCE_HIGH_CONVICTION", "false").lower() in ("1", "true", "yes"):
        seen: set[str] = set()
        for r in tradeable:
            if r.get("cramer_high_conviction") and r["ticker"] not in seen:
                cramer_force_buys.append(r)
                seen.add(r["ticker"])
        if cramer_force_buys:
            log.warning(
                "[CRAMER] %d high-conviction force buys: %s",
                len(cramer_force_buys),
                [r["ticker"] for r in cramer_force_buys],
            )

    ai_proxy_force_buys: list[dict] = []
    if os.getenv("AI_IPO_PROXY_FORCE_BUY", "true").lower() in ("1", "true", "yes"):
        try:
            from tools.ai_ipo_autopilot import autopilot_enabled

            if autopilot_enabled():
                proxy_min_p = float(os.getenv("AI_IPO_PROXY_MIN_P_UP", "0.52"))
                seen_proxy: set[str] = set()
                for r in sorted(tradeable, key=lambda x: -float(x.get("p_up", 0))):
                    if not r.get("ai_ipo_proxy"):
                        continue
                    if float(r.get("p_up", 0)) < proxy_min_p:
                        continue
                    if r["ticker"] in seen_proxy:
                        continue
                    ai_proxy_force_buys.append(r)
                    seen_proxy.add(r["ticker"])
                if ai_proxy_force_buys:
                    log.warning(
                        "[AI_IPO_PROXY] force-buy public AI exposure (pre-IPO names have no ticker): %s",
                        [x["ticker"] for x in ai_proxy_force_buys],
                    )
        except Exception:
            pass

    rows: list[dict] = []
    total_pnl = 0.0
    n_buy = 0
    n_short = 0
    picks: list[dict] = []
    shorts: list[dict] = []

    def _buy_notional(r: dict) -> float:
        base = float(notional)
        if r.get("cramer_high_conviction") and use_notional:
            mult = float(os.getenv("CRAMER_HIGH_CONVICTION_NOTIONAL_MULT", "1.5"))
            base = float(notional) * mult
        elif not use_notional:
            return float(qty) * float(r["sig_close"])
        try:
            from analytics.liquidity_impact import cap_notional_for_liquidity

            vol_s = None
            capped, liq = cap_notional_for_liquidity(
                str(r.get("ticker", "")),
                base,
                float(r.get("sig_close") or 0),
                volume_series=vol_s,
            )
            r["liquidity"] = liq
            if liq.get("block_order"):
                r["liquidity_block"] = True
            return float(capped)
        except Exception:
            return base

    def _hold_days_for(r: dict) -> int:
        if r.get("cramer_high_conviction"):
            return int(os.getenv("CRAMER_HOLD_DAYS", "10"))
        eff = r.get("hold_days_effective")
        if eff is not None:
            try:
                return int(eff)
            except Exception:
                pass
        ar = r.get("algo_risk") or {}
        if ar.get("hold_days") is not None:
            try:
                return int(ar["hold_days"])
            except Exception:
                pass
        return int(os.getenv("HOLD_DAYS_DEFAULT", "5"))

    def _passes_algo_risk(r: dict) -> bool:
        ar = r.get("algo_risk") or {}
        if ar and not ar.get("approved", True):
            return False
        try:
            from intel.algo_risk_filter import blocks_buy

            return not blocks_buy(str(r.get("ticker", "")), hold_days=_hold_days_for(r))[0]
        except Exception:
            # Fail closed when risk screen errors (override with PAPER_SIM_FAIL_OPEN=true).
            if os.getenv("PAPER_SIM_FAIL_OPEN", "false").lower() in ("1", "true", "yes"):
                return True
            return False

    def _passes_liquidity(r: dict) -> bool:
        if os.getenv("USE_LIQUIDITY_IMPACT", "true").lower() not in ("1", "true", "yes"):
            return True
        _buy_notional(r)
        if r.get("liquidity_block"):
            return False
        liq = r.get("liquidity") or {}
        return not bool(liq.get("block_order"))

    def _refresh_pre_trade_news(r: dict) -> bool:
        """Fresh Finnhub/NewsAPI pull before confirming a multi-day hold. Returns False if blocked."""
        if os.getenv("PRE_TRADE_NEWS_REFRESH", "true").lower() not in ("1", "true", "yes"):
            return True
        hold = _hold_days_for(r)
        min_hold = int(os.getenv("PRE_TRADE_NEWS_MIN_HOLD_DAYS", "5"))
        if hold < min_hold:
            return True
        try:
            from intel.pre_trade_news import refresh_pre_trade_intel

            intel = refresh_pre_trade_intel(r["ticker"])
            r["sentiment"] = float(intel["sentiment"])
            r["news_factor"] = float(intel.get("news_factor", r.get("news_factor", 0.0)))
            r["pre_trade_news_refreshed"] = True
            r["news_ai"] = intel.get("news_ai")
            if intel.get("block_long") or block_long_on_sentiment(
                r["sentiment"], symbol=str(r.get("ticker", ""))
            ):
                log.info(
                    "[PRE_TRADE_NEWS] skip %s — fresh news bearish (sent=%.3f hold=%dd)",
                    r["ticker"],
                    r["sentiment"],
                    hold,
                )
                return False
        except Exception as e:
            log.warning("[PRE_TRADE_NEWS] refresh failed %s: %s", r.get("ticker"), e)
            if os.getenv("PAPER_SIM_FAIL_OPEN", "false").lower() in ("1", "true", "yes"):
                return True
            return False
        return True

    def _realised_return(r: dict) -> float:
        """Switch from next-bar to days-to-weeks holding. Falls back to fwd_1d_return when no longer return is available."""
        h = _hold_days_for(r)
        v = r.get(f"fwd_{h}d_return")
        if v is None:
            return float(r.get("fwd_1d_return", 0.0))
        try:
            return float(v)
        except Exception:
            return float(r.get("fwd_1d_return", 0.0))

    def _hypo_long(r: dict) -> float:
        return _realised_return(r) * _buy_notional(r)

    def _hypo_short(r: dict) -> float:
        return -_realised_return(r) * _buy_notional(r)

    use_asym = os.getenv("USE_ASYM_META_FILTER", "true").lower() in ("1", "true", "yes")

    def _asym_long_ok(r: dict) -> bool:
        if not use_asym:
            return True
        return r.get("asym_action") == "LONG"

    if mode == "top_k":
        min_score = float(os.getenv("PAPER_SIM_MIN_SCORE", "0.0"))
        try:
            from analytics.trade_rotation import apply_score_penalty, filter_rows_by_cooldown

            tradeable = filter_rows_by_cooldown(tradeable)
            for r in tradeable:
                r["score"] = apply_score_penalty(str(r["ticker"]), float(r.get("score", 0.0)))
        except Exception:
            pass
        horizon_mixed = False
        try:
            from analytics.horizon_picks import horizon_independent, horizon_top_k, pick_top_conviction

            if horizon_independent():
                k = horizon_top_k(top_k)
                short_min = float(os.getenv("PAPER_SIM_SHORT_MIN_CONF", str(min_p)))
                pool = [
                    r
                    for r in tradeable
                    if _passes_directional_conf(r)
                    and float(r.get("score", 0.0)) >= min_score
                    and not (
                        float(r["p_up"]) >= 0.5
                        and block_long_on_sentiment(r["sentiment"], symbol=str(r.get("ticker", "")))
                    )
                ]
                if not pool and os.getenv("PAPER_RELAX_CONF_IF_EMPTY", "true").lower() in (
                    "1",
                    "true",
                    "yes",
                ):
                    pool = list(tradeable)
                chosen = pick_top_conviction(
                    pool,
                    p_key="p_up",
                    k=k,
                    allow_short=allow_shorts,
                    min_p_long=float(min_p),
                    min_p_short=short_min,
                )
                pick_rows = [r for r in chosen if r.get("horizon_side") != "short"]
                short_from_horizon = [r for r in chosen if r.get("horizon_side") == "short"]
                horizon_mixed = True
                for r in pick_rows:
                    if use_risk_check:
                        ok_r, _why = rm.can_open_explain(
                            r["ticker"], _buy_notional(r), r["sig_close"], r["stop"]
                        )
                        if not ok_r:
                            continue
                    if not _passes_algo_risk(r):
                        continue
                    if not _passes_liquidity(r):
                        continue
                    if not _refresh_pre_trade_news(r):
                        continue
                    picks.append(r)
                    if use_risk_check:
                        rm.register_open(r["ticker"], _buy_notional(r), r["sig_close"], r["stop"])
                for r in short_from_horizon:
                    if use_risk_check:
                        ok_r, _why = rm.can_open_explain(
                            r["ticker"] + ":S",
                            _buy_notional(r),
                            r["sig_close"],
                            r["sig_close"] * 1.10,
                        )
                        if not ok_r:
                            continue
                    shorts.append(r)
                    if use_risk_check:
                        rm.register_open(
                            r["ticker"] + ":S",
                            _buy_notional(r),
                            r["sig_close"],
                            r["sig_close"] * 1.10,
                        )
        except Exception:
            horizon_mixed = False
        if not horizon_mixed:
            ranked = sorted(tradeable, key=lambda r: -r["score"])
            picks_pool = [
                r
                for r in ranked
                if _passes_pick_conf(r) and _asym_long_ok(r) and float(r.get("score", 0.0)) >= min_score
            ] or (
                [r for r in ranked if _asym_long_ok(r)]
                if os.getenv("PAPER_RELAX_CONF_IF_EMPTY", "true").lower() in ("1", "true", "yes")
                else []
            )
            picks_pool = [
                r
                for r in picks_pool
                if not block_long_on_sentiment(r["sentiment"], symbol=str(r.get("ticker", "")))
            ]
            # Prepend Cramer high-conviction buys so they're always in the top slots.
            forced_set = {r["ticker"] for r in cramer_force_buys} | {r["ticker"] for r in ai_proxy_force_buys}
            rest = [r for r in picks_pool if r["ticker"] not in forced_set]
            picks_pool = ai_proxy_force_buys + cramer_force_buys + rest
            try:
                from analytics.trade_rotation import select_diversified_buys

                pick_rows = select_diversified_buys(picks_pool, top_k, score_key="score", ticker_key="ticker")
            except Exception:
                pick_rows = picks_pool[:top_k]
            for r in pick_rows:
                if use_risk_check:
                    ok_r, _why = rm.can_open_explain(r["ticker"], _buy_notional(r), r["sig_close"], r["stop"])
                    if not ok_r:
                        continue
                if not _passes_algo_risk(r):
                    continue
                if not _passes_liquidity(r):
                    continue
                if not _refresh_pre_trade_news(r):
                    continue
                picks.append(r)
                if use_risk_check:
                    rm.register_open(r["ticker"], _buy_notional(r), r["sig_close"], r["stop"])
    elif mode == "all_good":
        min_score = float(os.getenv("PAPER_SIM_MIN_SCORE", "0.0"))
        picks_pool = [
            r
            for r in tradeable
            if _passes_pick_conf(r)
            and _asym_long_ok(r)
            and r["score"] >= min_score
            and not block_long_on_sentiment(r["sentiment"], symbol=str(r.get("ticker", "")))
        ]
        if not picks_pool:
            # Keep conf/asym/sentiment gates; only relax the score floor when empty.
            if os.getenv("PAPER_RELAX_SCORE_IF_EMPTY", "true").lower() in ("1", "true", "yes"):
                picks_pool = [
                    r
                    for r in sorted(tradeable, key=lambda x: -float(x.get("score", 0)))
                    if _passes_pick_conf(r)
                    and _asym_long_ok(r)
                    and not block_long_on_sentiment(
                        r["sentiment"], symbol=str(r.get("ticker", ""))
                    )
                ][: max(top_k, 25)]
            else:
                picks_pool = []
        forced_set = {r["ticker"] for r in cramer_force_buys} | {r["ticker"] for r in ai_proxy_force_buys}
        picks_pool = ai_proxy_force_buys + cramer_force_buys + [
            r for r in picks_pool if r["ticker"] not in forced_set
        ]
        for r in picks_pool:
            if use_risk_check:
                ok_r, _why = rm.can_open_explain(r["ticker"], _buy_notional(r), r["sig_close"], r["stop"])
                if not ok_r:
                    continue
            if not _passes_algo_risk(r):
                continue
            if not _passes_liquidity(r):
                continue
            if not _refresh_pre_trade_news(r):
                continue
            picks.append(r)
            if use_risk_check:
                rm.register_open(r["ticker"], _buy_notional(r), r["sig_close"], r["stop"])
    else:  # gates mode
        use_mtf_env = os.getenv("PAPER_SIM_USE_MTF", "false").lower() in ("1", "true", "yes")
        forced_set = {r["ticker"] for r in cramer_force_buys} | {r["ticker"] for r in ai_proxy_force_buys}
        for r in ai_proxy_force_buys + cramer_force_buys:
            if use_risk_check:
                ok_r, _why = rm.can_open_explain(r["ticker"], _buy_notional(r), r["sig_close"], r["stop"])
                if not ok_r:
                    continue
            if not _passes_algo_risk(r):
                continue
            if not _passes_liquidity(r):
                continue
            if not _refresh_pre_trade_news(r):
                continue
            picks.append(r)
            if use_risk_check:
                rm.register_open(r["ticker"], _buy_notional(r), r["sig_close"], r["stop"])
        for r in tradeable:
            if r["ticker"] in forced_set:
                continue
            want_buy = (
                _passes_pick_conf(r)
                and _asym_long_ok(r)
                and _passes_algo_risk(r)
                and _passes_liquidity(r)
                and not block_long_on_sentiment(r["sentiment"], symbol=str(r.get("ticker", "")))
                and r["vol_ok"]
                and (r["mtf_ok"] if use_mtf_env else True)
                and scale > 0
            )
            if want_buy:
                if use_risk_check:
                    ok_r, _why = rm.can_open_explain(r["ticker"], _buy_notional(r), r["sig_close"], r["stop"])
                    if not ok_r:
                        continue
                if not _refresh_pre_trade_news(r):
                    continue
                picks.append(r)
                if use_risk_check:
                    rm.register_open(r["ticker"], _buy_notional(r), r["sig_close"], r["stop"])

    if allow_shorts:
        try:
            from analytics.horizon_picks import horizon_independent as _tf_skip_legacy_shorts

            _legacy_shorts = not _tf_skip_legacy_shorts()
        except Exception:
            _legacy_shorts = True
    else:
        _legacy_shorts = False
    if _legacy_shorts:
        # Conservative shorts: high p_down, not in earnings window, not crypto-like, not already a long pick
        from crypto_universe import is_crypto_symbol
        long_set = {p["ticker"] for p in picks}

        def _asym_short_ok(rr: dict) -> bool:
            if not use_asym:
                return True
            return rr.get("asym_action") == "SHORT"

        cands = [
            r for r in tradeable
            if r["ticker"] not in long_set
            and _asym_short_ok(r)
            and not is_crypto_symbol(r["ticker"])
            and r["p_down"] >= max(min_p, float(os.getenv("PAPER_SIM_SHORT_MIN_CONF", "0.55")))
            and r["score"] <= float(os.getenv("PAPER_SIM_SHORT_MAX_SCORE", "-0.10"))
            and r.get("days_to_earnings", 99) > int(os.getenv("PAPER_SIM_SHORT_AVOID_EARNINGS_DAYS", "5"))
        ]
        cands.sort(key=lambda r: r["score"])  # most negative first
        for r in cands[:short_top_k]:
            if use_risk_check:
                ok_r, _why = rm.can_open_explain(r["ticker"] + ":S", _buy_notional(r), r["sig_close"], r["sig_close"] * 1.10)
                if not ok_r:
                    continue
            shorts.append(r)
            if use_risk_check:
                rm.register_open(r["ticker"] + ":S", _buy_notional(r), r["sig_close"], r["sig_close"] * 1.10)

    ai_pick_meta: dict | None = None
    ai_review_t0 = time.perf_counter()
    if os.getenv("USE_AI_FINAL_PICK_REVIEW", "false").lower() in ("1", "true", "yes"):
        try:
            from intel.ai_final_pick_review import apply_ai_review_to_long_picks

            new_picks, ai_pick_meta = apply_ai_review_to_long_picks(
                picks,
                regime_name=getattr(regime.name, "value", str(regime.name)),
                vix=float(regime.vix) if getattr(regime, "vix", None) is not None else None,
            )
            if new_picks:
                picks = new_picks
            elif ai_pick_meta.get("enabled") and os.getenv("AI_PICK_FALLBACK_IF_ALL_REJECTED", "true").lower() in (
                "1",
                "true",
                "yes",
            ):
                log.warning("[AI-PICK] all longs rejected — keeping pre-AI picks (fallback)")
        except Exception as e:
            log.warning("[AI-PICK] skipped: %s", e)
    ai_review_ms = int((time.perf_counter() - ai_review_t0) * 1000)

    pick_set = {p["ticker"] for p in picks}
    try:
        from analytics.trade_rotation import save_picks

        save_picks([p["ticker"] for p in picks], source="paper_sim")
    except Exception:
        pass
    short_set = {s["ticker"] for s in shorts}
    pick_by_ticker = {p["ticker"]: p for p in picks}
    for r in tradeable:
        if r["ticker"] in pick_set:
            action = "BUY"
            hypo = _hypo_long(r)
            total_pnl += hypo
            n_buy += 1
        elif r["ticker"] in short_set:
            action = "SHORT"
            hypo = _hypo_short(r)
            total_pnl += hypo
            n_short += 1
        elif r["p_up"] <= (1 - min_p):
            action, hypo = "SELL_SIGNAL", 0.0
        else:
            action, hypo = "HOLD", 0.0
        row = {**r, "action": action, "hypo_pnl_usd": round(hypo, 2)}
        if action == "BUY" and r["ticker"] in pick_by_ticker:
            pk = pick_by_ticker[r["ticker"]]
            for k in ("ai_pick_review", "ai_blend_rank", "ai_grade", "ai_profit_focus_score"):
                if k in pk:
                    row[k] = pk[k]
        try:
            from analytics.industries.project_wiring import wire_paper_sim_row

            row = wire_paper_sim_row(row)
        except Exception:
            pass
        rows.append(row)

    # Online single-step learning (Phase 11). Disabled by default (USE_ONLINE_UPDATER).
    online_updates: list[dict] = []
    neural_updates: list[dict] = []
    online_update_t0 = time.perf_counter()
    try:
        from analytics.asymmetric_loss import asymmetric_reward
        from online_learning.weight_updater import online_update_meta_for_trade, use_online_updater
        from online_learning.neural_ensemble import (
            record_neural_experience,
            train_neural_ensemble_for_ticker,
            use_neural_ensemble,
        )

        traded_tickers: set[str] = set()
        if use_online_updater():
            for r in rows:
                if r.get("action") not in ("BUY", "SHORT"):
                    continue
                side = "LONG" if r["action"] == "BUY" else "SHORT"
                rw = asymmetric_reward(side, float(r.get("fwd_1d_return", 0.0)), bars_held=1)
                state = {
                    "p_short": float(r.get("p_down", 1.0 - float(r.get("p_up", 0.5)))),
                    "p_long": float(r.get("p_up", 0.5)),
                    "p_gap": float(r.get("p_down", 0.5)) - float(r.get("p_up", 0.5)),
                    "vol_regime_ratio": 0.0,
                    "sentiment_impulse": float(r.get("news_factor", 0.0)),
                    "regime_transition_flag": 0.0,
                    "alpha_proxy_20": float(r.get("rs_spy", 1.0)) - 1.0,
                }
                rep = online_update_meta_for_trade(r["ticker"], state, side, rw.reward)
                online_updates.append(
                    {
                        "ticker": r["ticker"],
                        "side": side,
                        "reward": rw.reward,
                        "applied": rep.applied,
                        "delta_l2": rep.delta_l2,
                        "pre_p": rep.pre_p,
                        "post_p": rep.post_p,
                        "reason": rep.reason,
                    }
                )
                traded_tickers.add(str(r["ticker"]))

        if use_neural_ensemble():
            for r in rows:
                if r.get("action") not in ("BUY", "SHORT"):
                    continue
                state = r.get("online_state") if isinstance(r.get("online_state"), dict) else {}
                if not state:
                    continue
                side = "LONG" if r["action"] == "BUY" else "SHORT"
                rr = float(r.get("fwd_1d_return", 0.0))
                rw = asymmetric_reward(side, rr, bars_held=1)
                record_neural_experience(
                    ticker=str(r["ticker"]),
                    state=state,
                    action=side,
                    realized_return=rr,
                    reward=float(rw.reward),
                )
                traded_tickers.add(str(r["ticker"]))

            for t in sorted(traded_tickers):
                rep = train_neural_ensemble_for_ticker(t)
                neural_updates.append(
                    {
                        "ticker": rep.ticker,
                        "applied": rep.applied,
                        "reason": rep.reason,
                        "n_samples": rep.n_samples,
                        "lstm_loss": rep.lstm_loss,
                        "cnn_loss": rep.cnn_loss,
                        "ga_lstm_loss": rep.ga_lstm_loss,
                        "cnn_bilstm_loss": rep.cnn_bilstm_loss,
                        "dqn_loss": rep.dqn_loss,
                    }
                )
    except Exception as e:
        log.warning("[ONLINE] paper-sim online update skipped: %s", e)
    online_update_ms = int((time.perf_counter() - online_update_t0) * 1000)

    leaderboard = _market_leaderboard(rows, k=15)
    winner = leaderboard["top_winners"][0] if leaderboard["top_winners"] else None
    asym_phase10 = _asym_filter_metrics(tradeable)

    neural_dashboard: dict | None = None

    out = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "top_k": top_k if mode == "top_k" else None,
        "min_conf": min_p,
        "min_execution_confidence": min_exec,
        "confidence_gate_mode": confidence_gate_mode(),
        "exec_cert_gain": float(os.getenv("EXEC_CERTAINTY_GAIN", "4.2")),
        "regime": regime.name.value,
        "vix": regime.vix,
        "market_bull_bear": bull_bear,
        "universe_size": universe_n,
        "symbols_scored": len(tradeable),
        "skipped_no_model_or_history": n_skipped,
        "incremental": inc_meta,
        "asym_filter_metrics": asym_phase10,
        "fred_macro": {
            "ok": bool(macro_bundle.get("ok")) if macro_bundle else False,
            "macro_score": float(macro_bundle.get("macro_score", 0.0)) if macro_bundle else 0.0,
            "spread_10y2y": macro_bundle.get("spread_10y2y") if macro_bundle else None,
        },
        "hypothetical_buys": n_buy,
        "hypothetical_shorts": n_short,
        "sum_hypothetical_pnl_usd": round(total_pnl, 2),
        "sizing_mode": "notional" if use_notional else "qty",
        "notional_per_position_usd": notional if use_notional else None,
        "qty_per_position": qty if not use_notional else None,
        "definite_winner": winner,
        "note": "PnL: long = +fwd_ret*notional, short = -fwd_ret*notional. Excludes fees/slippage.",
        "leaderboard": leaderboard,
        "online_updates_applied": int(sum(1 for u in online_updates if u.get("applied"))),
        "online_updates_attempted": len(online_updates),
        "online_updates": online_updates[:50],
        "neural_updates_applied": int(sum(1 for u in neural_updates if u.get("applied"))),
        "neural_updates_attempted": len(neural_updates),
        "neural_updates": neural_updates[:50],
        "neural_dashboard": neural_dashboard,
        "ai_pick_review": ai_pick_meta,
        "long_picks": [
            {
                "ticker": p["ticker"],
                "score": float(p.get("score", 0.0)),
                "p_up": float(p.get("p_up", 0.0)),
                "chance_pct": int(p.get("chance_pct") or round(float(p.get("p_up", 0.5)) * 100)),
                "asym_action": p.get("asym_action"),
                "p_daily_chance_pct": p.get("p_daily_chance_pct"),
                "p_short_chance_pct": p.get("p_short_chance_pct"),
                "p_long_chance_pct": p.get("p_long_chance_pct"),
                "p_xlong_chance_pct": p.get("p_xlong_chance_pct"),
            }
            for p in picks
        ],
        "rows": rows,
    }

    rep = Path("reports")
    rep.mkdir(parents=True, exist_ok=True)

    if os.getenv("USE_NEURAL_ENSEMBLE", "true").lower() in ("1", "true", "yes"):
        try:
            from online_learning.neural_ensemble import (
                build_neural_dashboard,
                print_neural_dashboard_summary,
            )

            neural_dashboard = build_neural_dashboard(tradeable)
            out["neural_dashboard"] = neural_dashboard
            print_neural_dashboard_summary(neural_dashboard)
            nd_path = rep / "neural_dashboard_latest.json"
            nd_path.write_text(json.dumps(neural_dashboard, indent=2), encoding="utf-8")
        except Exception as e:
            log.debug("[NEURAL] dashboard skipped: %s", e)

    fn = rep / f"paper_sim_{datetime.now(timezone.utc).strftime('%Y%m%d')}.json"
    from analytics.paper_report import write_report_if_valid

    written = write_report_if_valid(out)
    if written:
        fn = written
        log.info("[PAPER_SIM] Wrote %s", fn)
    else:
        log.warning("[PAPER_SIM] empty run — kept previous valid report")

    sizing_str = (
        f"${notional:,.0f} notional/position" if use_notional
        else f"{qty} sh/position"
    )

    print(f"\n=== Paper sim ({mode}) ===")
    print(f"Report: {fn}")
    print(f"Universe={len(syms)}  Scored={len(tradeable)}  Skipped(no model/history)={n_skipped}")
    print(f"Regime={regime.name.value}  Sizing={sizing_str}  Shorts={'on' if allow_shorts else 'off'}")
    print(f"Buys={n_buy}  Shorts={n_short}  Sum PnL (USD, ex fees) = {total_pnl:,.2f}")
    print(
        f"Asym filter: long_zone={asym_phase10['n_asym_long_zone']} "
        f"short_zone={asym_phase10['n_asym_short_zone']} no_trade={asym_phase10['n_asym_no_trade']} "
        f"long_prec={asym_phase10['hypothetical_long_zone_precision']} "
        f"short_prec={asym_phase10['hypothetical_short_zone_precision']}"
    )

    if ai_pick_meta and ai_pick_meta.get("enabled"):
        print(
            f"\n=== AI final pick review ({ai_pick_meta.get('model', '?')}) "
            f"before→after longs {ai_pick_meta.get('picks_before')}→{ai_pick_meta.get('picks_after')} "
            f"blend={ai_pick_meta.get('blend_weight')} min_grade={ai_pick_meta.get('min_grade')} ==="
        )
        for rv in (ai_pick_meta.get("reviews") or [])[:16]:
            print(
                f"  {str(rv.get('ticker','?')):6} {rv.get('verdict','?'):7} grade={rv.get('grade','?')} "
                f"pfs={float(rv.get('profit_focus_score',0)):.2f} conf={float(rv.get('confidence',0)):.2f} "
                f"{str(rv.get('one_line',''))[:72]}"
            )

    if winner:
        print(
            f"\n*** DEFINITE MARKET WINNER: {winner['ticker']} "
            f"+{winner['fwd_1d_return']*100:.2f}% (p_up={winner['p_up']:.3f}) ***"
        )

    if picks:
        print("\nLong picks (next-bar return):")
        for r in sorted(picks, key=lambda x: -float(x.get("ai_blend_rank", x.get("score", 0))))[:25]:
            ai = ""
            if r.get("ai_grade"):
                ai = f" AI={r.get('ai_grade')} pfs={float(r.get('ai_profit_focus_score', 0)):.2f}"
            line = (
                f"  {r['ticker']:6} score={r['score']:.3f} p_up={r['p_up']:.3f} "
                f"exec={r.get('execution_confidence', 0):.3f}{ai} "
                f"dip={r['dip_signal']:.2f} mom5d={r['momentum_5d']*100:+.2f}% "
                f"rs={r['rs_spy']:.2f} fwd_ret={r['fwd_1d_return']*100:+.2f}% "
                f"gate={r['gate_detail']}"
            )
            print(line)

    if shorts:
        print("\nShort picks (next-bar return; PnL inverted):")
        for r in sorted(shorts, key=lambda x: x.get("score", 0))[:15]:
            print(
                f"  {r['ticker']:6} score={r['score']:.3f} p_down={r['p_down']:.3f} "
                f"mom5d={r['momentum_5d']*100:+.2f}% fwd_ret={r['fwd_1d_return']*100:+.2f}%"
            )

    print("\nMarket top winners (causal):")
    for w in leaderboard["top_winners"][:10]:
        print(f"  {w['ticker']:6} +{w['fwd_1d_return']*100:.2f}% (p_up={w['p_up']:.3f})")

    return out


if __name__ == "__main__":
    mx = int(os.environ["MAX"]) if os.getenv("MAX") else None
    run_paper_simulation_today(max_symbols=mx)
