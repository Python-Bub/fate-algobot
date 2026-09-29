"""
Unified buy-ranking pipeline — one scoring path for paper-sim and fortress.

Replaces scattered duplicate formulas. Strategy families are registered in
`analytics/strategy_registry.py`; this module applies them in a fixed order
without double-counting (e.g. trend + pair inside hedge_fund_stack only once).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np
import pandas as pd

from utils import log


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _b(name: str, default: bool = True) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes")


def _finite(v: Any, default: float = 0.0) -> float:
    """Drop NaN/Inf from a learner component so one bad boost cannot poison rank."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    if x != x or x == float("inf") or x == float("-inf"):
        return default
    return x


@dataclass
class RankInputs:
    ticker: str
    p_up: float
    exec_conf: float
    sent: float = 0.0
    news_factor: float = 0.0
    transcript_factor: float = 0.0
    mom_5d: float = 0.0
    rs_spy: float = 1.0
    vol_ratio: float = 1.0
    dip_signal: float = 0.0
    rally_signal: float = 0.0
    hmm_market_score: float = 0.0
    row: pd.Series | dict | None = None
    closes: pd.Series | None = None
    bench_closes: pd.Series | None = None
    fund: dict | None = None
    neural_p_up: float | None = None
    top100: bool = False
    start_hist: str = "2018-01-01"
    pair_closes_loader: Callable[[str], pd.Series] | None = None
    crowd_meta: dict | None = None


@dataclass
class RankResult:
    score: float
    components: dict[str, float] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)


def core_composite_score(
    p_up: float,
    mom_5d: float,
    rs_spy: float,
    vol_ratio: float,
    sent: float,
    *,
    dip_signal: float = 0.0,
) -> float:
    """Base rank from probability + momentum + liquidity + sentiment + dip."""
    w_p = _f("RANK_W_PUP", 1.0)
    w_m = _f("RANK_W_MOM", 0.15)
    w_r = _f("RANK_W_RS", 0.20)
    w_v = _f("RANK_W_VOL", 0.10)
    try:
        from analytics.math_pivot import sent_weight

        w_s = sent_weight()
    except Exception:
        w_s = _f("RANK_W_SENT", 0.15)
    w_d = _f("RANK_W_DIP", 0.30)
    return float(
        w_p * (p_up - 0.5) * 2.0
        + w_m * float(np.tanh(mom_5d * 10.0))
        + w_r * float(np.tanh((rs_spy - 1.0) * 3.0))
        + w_v * float(np.tanh(max(vol_ratio - 1.0, 0.0)))
        + w_s * float(np.tanh(sent))
        + w_d * float(dip_signal)
    )


def fortress_buy_score(
    *,
    p_adj: float,
    exec_c: float,
    sent: float,
    nf_f: float,
    top100: bool,
    hf_boost: float = 0.0,
    ticker: str | None = None,
    row: pd.Series | dict | None = None,
    mom_5d: float = 0.0,
    rs_spy: float = 1.0,
    hmm_market_score: float = 0.0,
    closes: pd.Series | None = None,
    bench_closes: pd.Series | None = None,
) -> float:
    """Fortress ranking — single-name conviction weighted (see data/ops/PICK_WEIGHTAGE_BY_SLEEVE.md)."""
    edge = max(0.0, float(p_adj) - 0.5) * 2.0
    try:
        from analytics.math_pivot import fortress_news_rank_w, weight_multiplier

        rank_w = fortress_news_rank_w()
        hf_m = weight_multiplier("hedge_fund")
    except Exception:
        rank_w = _f("FORTRESS_NEWS_RANK_W", 0.12)
        hf_m = 1.0
    sent_imp = max(-0.10, min(0.10, float(sent) * 0.08))
    news_imp = max(-0.10, min(0.10, float(nf_f) * 0.10))
    # Sleeve table is source of truth; deploy_scale.env may still override.
    try:
        from analytics.sleeve_weights import fortress_weight

        w_edge = fortress_weight("model_edge", 0.75)
        w_exec = fortress_weight("exec_conf", 0.27)
        w_sent = _f("FORTRESS_W_SENT", 0.10)
        top100_bonus = fortress_weight("top100", 0.03)
    except Exception:
        w_edge = _f("FORTRESS_W_EDGE", 0.75)
        w_exec = _f("FORTRESS_W_EXEC", 0.27)
        w_sent = _f("FORTRESS_W_SENT", 0.10)
        top100_bonus = _f("FORTRESS_TOP100_RANK_BONUS", 0.03)
    score = w_edge * edge + w_exec * float(exec_c) + w_sent * sent_imp + rank_w * news_imp
    score += _f("RANK_W_HEDGE_FUND", 1.0) * hf_m * float(hf_boost)
    if top100:
        score += top100_bonus
    try:
        from analytics.vector_math import normalize_weights

        nw = normalize_weights([w_edge, w_exec, abs(w_sent), abs(rank_w)])
        if nw.size == 4 and float(np.sum(nw)) > 0:
            score = (
                float(nw[0]) * edge
                + float(nw[1]) * float(exec_c)
                + float(np.sign(w_sent) or 1.0) * float(nw[2]) * sent_imp
                + float(np.sign(rank_w) or 1.0) * float(nw[3]) * news_imp
            )
            score += _f("RANK_W_HEDGE_FUND", 1.0) * hf_m * float(hf_boost)
            if top100:
                score += top100_bonus
    except Exception:
        pass
    if ticker:
        score += fortress_learner_delta(
            ticker=str(ticker),
            p_up=float(p_adj),
            exec_c=float(exec_c),
            mom_5d=float(mom_5d),
            rs_spy=float(rs_spy),
            hmm=float(hmm_market_score),
            row=row,
            closes=closes,
            bench_closes=bench_closes,
        )
    return float(score)


def fortress_learner_delta(
    *,
    ticker: str,
    p_up: float,
    exec_c: float,
    mom_5d: float = 0.0,
    rs_spy: float = 1.0,
    hmm: float = 0.0,
    row: pd.Series | dict | None = None,
    closes: pd.Series | None = None,
    bench_closes: pd.Series | None = None,
) -> float:
    """Proven / event / industry rank — fortress already has HF/water/structure elsewhere."""
    extra = 0.0
    if _b("USE_PROVEN_ONLINE", True):
        try:
            from analytics.proven_online import proven_online_rank_boost
            from analytics.residual_mom import attach_resid_mom

            r = attach_resid_mom(row, closes, bench_closes)
            po_b, _ = proven_online_rank_boost(
                ticker,
                p_up=float(p_up),
                exec_c=float(exec_c),
                mom_5d=float(mom_5d),
                rs_spy=float(rs_spy),
                hmm=float(hmm),
                row=r,
                sleeve="fortress",
            )
            extra += _f("RANK_W_PROVEN_ONLINE", 0.28) * _finite(po_b)
        except Exception:
            pass
    if _b("USE_EVENT_LEARN", True):
        try:
            from analytics.event_learn import event_learn_rank_boost

            ret_1d = None
            vol_el = 0.0
            if row is not None:
                rowd = row if isinstance(row, dict) else dict(row)
                for k in ("ret_1d", "return_1d", "pct_change"):
                    if rowd.get(k) is not None:
                        try:
                            ret_1d = float(rowd[k])
                            break
                        except (TypeError, ValueError):
                            pass
                try:
                    vol_el = float(rowd.get("vol_20") or rowd.get("volatility") or 0.0)
                except (TypeError, ValueError):
                    vol_el = 0.0
            el_b, _ = event_learn_rank_boost(
                ticker,
                mom_5d=float(mom_5d),
                ret_1d=ret_1d,
                vol_20=vol_el,
                sleeve="fortress",
            )
            extra += _f("RANK_W_EVENT_LEARN", 0.10) * _finite(el_b)
        except Exception:
            pass
    if _b("USE_INDUSTRY_PIPELINE", True):
        try:
            from analytics.industries.pipeline import run_industry_pipeline

            pipe = run_industry_pipeline(ticker, row)
            delta = _finite(pipe.get("score_delta") or 0.0)
            if pipe.get("block_long"):
                delta = min(delta, -0.15)
            extra += _f("RANK_W_INDUSTRY_PIPELINE", 0.06) * delta
        except Exception:
            pass
    return _finite(extra)


def curriculum_soft_boosts(
    *,
    sleeve: str,
    macro_bundle: dict | None = None,
    fund_score: float = 0.0,
) -> dict[str, float]:
    """
    Macro / passive curriculum soft additives for weekly + longterm only.
    Never applied on hft / day_trade. Index ETF buy weight stays 0.
    """
    s = (sleeve or "").strip().lower()
    if s not in ("weekly", "longterm"):
        return {}
    out: dict[str, float] = {}
    mb = macro_bundle or {}
    try:
        from investing.formulas.macro import cycle_score, inflation_hedge_tilt

        infl = mb.get("inflation_yoy")
        if infl is None:
            infl = mb.get("cpi_yoy")
        if infl is not None:
            out["inflation_deflation"] = _f("RANK_W_INFLATION", 0.0) * float(
                inflation_hedge_tilt(float(infl) if abs(float(infl)) > 1 else float(infl))
            )
        else:
            # Proxy: positive macro_score → mild real-asset tilt when RANK_W_INFLATION set
            ms = float(mb.get("macro_score") or 0.0)
            out["inflation_deflation"] = _f("RANK_W_INFLATION", 0.0) * float(np.tanh(ms * 0.5))
        spread = mb.get("spread_10y2y")
        pmi = mb.get("pmi") or mb.get("pmi_score")
        vix = mb.get("vix")
        cyc = cycle_score(
            pmi=float(pmi) if pmi is not None else None,
            vix=float(vix) if vix is not None else None,
            yield_curve_slope=float(spread) if spread is not None else None,
        )
        out["interest_rate_cycle"] = _f("RANK_W_RATE_CYCLE", 0.0) * float(cyc)
    except Exception:
        spread = mb.get("spread_10y2y")
        if spread is not None:
            out["interest_rate_cycle"] = _f("RANK_W_RATE_CYCLE", 0.0) * float(
                np.tanh(float(spread) * 50.0)
            )
    # Buy-hold / DCA quality: fund strength as hold-discipline proxy (not index buy)
    out["dca_buy_hold"] = _f("RANK_W_BUY_HOLD", 0.0) * float(np.tanh(float(fund_score)))
    if s == "longterm":
        out["alt_context"] = _f("RANK_W_ALT_CONTEXT", 0.0) * float(np.tanh(float(fund_score) * 0.5))
    return {k: v for k, v in out.items() if abs(v) > 1e-9}


def build_buy_rank(inp: RankInputs, *, runtime: str = "paper", sleeve: str | None = None) -> RankResult:
    """
    Single entry point for buy ranking extensions after p_up / exec_conf are set.

    runtime: 'paper' | 'fortress' | 'day_trade'
    sleeve: optional override; else resolved from FATE_SLEEVE / HOLD_DAYS_DEFAULT
    """
    try:
        from analytics.sleeve_weights import apply_sleeve_env, resolve_sleeve

        if runtime == "fortress":
            resolved = resolve_sleeve(sleeve or "fortress")
        elif runtime == "day_trade":
            resolved = resolve_sleeve(sleeve or "day_trade")
        else:
            resolved = resolve_sleeve(sleeve)
        apply_sleeve_env(resolved)
    except Exception:
        resolved = sleeve or runtime

    comps: dict[str, float] = {}
    meta: dict[str, Any] = {"runtime": runtime, "sleeve": resolved, "strategies": []}

    score = core_composite_score(
        inp.p_up,
        inp.mom_5d,
        inp.rs_spy,
        inp.vol_ratio,
        inp.sent,
        dip_signal=inp.dip_signal,
    )
    comps["core"] = score

    if inp.rally_signal:
        w = _f("RANK_W_RALLY", 0.08)
        comps["rally"] = w * float(inp.rally_signal)
        score += comps["rally"]
        meta["strategies"].append("momentum_trend")

    # HMM regime — not inside hedge_fund_stack
    w_hmm = _f("RANK_W_HMM_REGIME", 0.12)
    comps["hmm"] = w_hmm * float(inp.hmm_market_score)
    score += comps["hmm"]
    if abs(inp.hmm_market_score) > 0.01:
        meta["strategies"].append("regime_macro")

    hf_boost = 0.0
    hf_meta: dict[str, Any] = {}
    use_hf = _b("USE_HEDGE_FUND_STACK", True)
    if use_hf and inp.row is not None and inp.closes is not None:
        try:
            from analytics.hedge_fund_stack import hedge_fund_rank_boost

            hf = hedge_fund_rank_boost(
                inp.ticker,
                row=inp.row,
                closes=inp.closes,
                bench_closes=inp.bench_closes,
                fund=inp.fund,
                regime_score=float(inp.hmm_market_score),
                pair_closes_loader=inp.pair_closes_loader,
            )
            hf_boost = float(hf.boost)
            w_hf = _f("RANK_W_HEDGE_FUND", 1.0)
            comps["hedge_fund"] = w_hf * hf_boost
            score += comps["hedge_fund"]
            hf_meta = hf.meta if hasattr(hf, "meta") else {}
            meta["hedge_fund"] = {
                "boost": hf_boost,
                "momentum": hf.momentum,
                "trend": hf.trend,
                "stat_arb": hf.stat_arb,
                "mean_reversion": hf.mean_reversion,
            }
            meta["strategies"].extend(
                ["hedge_fund_composite", "momentum_trend", "stat_arb_pairs", "mean_reversion"]
            )
        except Exception as e:
            log.debug("[RANK] hedge_fund %s: %s", inp.ticker, e)
    elif not use_hf and inp.row is not None and inp.closes is not None:
        # Legacy separate trend/pair only when HF stack disabled
        try:
            from paper_sim_today import _classic_trend_momentum_signal, _pairs_stat_arb_signal

            classic = _classic_trend_momentum_signal(inp.row, inp.closes)
            pair_sig, _, _ = _pairs_stat_arb_signal(inp.ticker, inp.closes, inp.start_hist)
            comps["trend_classic"] = _f("RANK_W_TREND_CLASSIC", 0.12) * float(classic["trend_signal"])
            comps["pair_arb"] = _f("RANK_W_PAIR_ARB", 0.18) * float(pair_sig)
            score += comps["trend_classic"] + comps["pair_arb"]
        except Exception:
            pass

    if inp.top100:
        try:
            from analytics.signal_enhance import top100_rank_score_boost, top100_score_multiplier

            comps["top100"] = top100_rank_score_boost(inp.ticker)
            score += comps["top100"]
            score *= top100_score_multiplier(True)
        except Exception:
            pass

    comps["news"] = _f("RANK_W_NEWS_FACTOR", 0.05) * float(inp.news_factor)
    comps["transcript"] = _f("RANK_W_TRANSCRIPT_FACTOR", 0.0) * float(inp.transcript_factor)
    score += comps["news"] + comps["transcript"]

    if inp.fund:
        comps["fund"] = _f("RANK_W_FUND", 0.20) * float(inp.fund.get("fund_score", 0.0))
        score += comps["fund"]

    comps["exec_conf"] = _f("RANK_W_EXEC_CONF", 0.35) * float(np.tanh((inp.exec_conf - 0.5) * 4.0))
    score += comps["exec_conf"]

    # Research-backed structure / S/R / trend (candles only as weak context confirmation).
    # Literature: raw candlesticks ≈ coin-flip once trend is controlled — do not dominate ML heads.
    if inp.closes is not None and _b("USE_STRUCTURE_PATTERNS", True):
        try:
            from analytics.structure_patterns import structure_rank_boost

            closes = inp.closes
            if isinstance(closes, pd.Series):
                ohlc = pd.DataFrame({"Close": closes.astype(float)})
                if inp.row is not None:
                    row = inp.row if isinstance(inp.row, dict) else dict(inp.row)
                    for col in ("Open", "High", "Low"):
                        if col in row:
                            ohlc[col] = float(row[col])
            else:
                ohlc = pd.DataFrame({"Close": list(closes)})
            boost, s_meta = structure_rank_boost(ohlc)
            comps["structure"] = boost
            score += boost
            meta["structure"] = s_meta
            if abs(boost) > 1e-6:
                meta["strategies"].append("structure_patterns")
        except Exception as e:
            log.debug("[RANK] structure %s: %s", inp.ticker, e)

    # Bottom-50% / capitulation recovery searcher (agreed long-tail path).
    if _b("USE_BOTTOM_FISHER", True):
        try:
            from bottom_fisher.integrate import bottom_fisher_score_boost

            bf_boost, bf_meta = bottom_fisher_score_boost(inp.ticker)
            comps["bottom_fisher"] = float(bf_boost)
            score += comps["bottom_fisher"]
            meta["bottom_fisher"] = bf_meta
            if comps["bottom_fisher"] > 0:
                meta["strategies"].append("bottom_fisher")
        except Exception as e:
            log.debug("[RANK] bottom_fisher %s: %s", inp.ticker, e)

    if _b("USE_INDUSTRY_PIPELINE", True) and str(resolved) not in ("hft",):
        try:
            from analytics.industries.pipeline import run_industry_pipeline

            pipe = run_industry_pipeline(inp.ticker, inp.row)
            w = _f("RANK_W_INDUSTRY_PIPELINE", 0.06)
            delta = float(pipe.get("score_delta") or 0.0)
            if pipe.get("block_long"):
                delta = min(delta, -0.15)
            comps["industry_ai"] = w * delta
            score += comps["industry_ai"]
            meta["industry_ai"] = {
                "industry_id": pipe.get("industry_id") or pipe.get("primary_industry_id"),
                "score_delta": delta,
                "block_long": pipe.get("block_long"),
            }
            if abs(comps["industry_ai"]) > 1e-6:
                meta["strategies"].append("industry_ai")
        except Exception as e:
            log.debug("[RANK] industry_ai %s: %s", inp.ticker, e)

    if str(resolved) not in ("hft", "day_trade"):
        try:
            from analytics.water_theme import space_rank_boost, water_rank_boost

            wb, wm = water_rank_boost(inp.ticker, p_up=float(inp.p_up), sleeve=str(resolved))
            comps["water_datacenter"] = float(wb)
            score += comps["water_datacenter"]
            meta["water_datacenter"] = wm
            if abs(comps["water_datacenter"]) > 1e-6:
                meta["strategies"].append("water_datacenter")
            sb, sm = space_rank_boost(inp.ticker, p_up=float(inp.p_up), sleeve=str(resolved))
            comps["space_infra"] = float(sb)
            score += comps["space_infra"]
            if abs(comps["space_infra"]) > 1e-6:
                meta["space_infra"] = sm
                meta["strategies"].append("space_infra")
        except Exception as e:
            log.debug("[RANK] water_theme %s: %s", inp.ticker, e)

    if _b("USE_DERIVATIVES_CONTEXT", True) and str(resolved) not in ("hft",):
        try:
            from analytics.contract_select import derivatives_rank_boost

            spot = None
            if inp.closes is not None and len(inp.closes):
                try:
                    spot = float(inp.closes.iloc[-1])
                except Exception:
                    spot = None
            d_boost, d_meta = derivatives_rank_boost(inp.ticker, p_up=float(inp.p_up), spot=spot)
            w = _f("RANK_W_DERIV_CONTEXT", 0.08)
            comps["derivatives_context"] = w * float(d_boost)
            score += comps["derivatives_context"]
            meta["derivatives"] = d_meta
            if abs(comps["derivatives_context"]) > 1e-6:
                meta["strategies"].append("derivatives_context")
        except Exception as e:
            log.debug("[RANK] derivatives %s: %s", inp.ticker, e)

    if inp.row is not None and _b("USE_FEATURE_IC_WEIGHTS", True):
        try:
            from analytics.feature_decision_weights import row_weighted_score

            wmap = (inp.crowd_meta or {}).get("feature_ic_weights") if isinstance(inp.crowd_meta, dict) else None
            if wmap:
                rowd = inp.row if isinstance(inp.row, dict) else dict(inp.row)
                feat_s = row_weighted_score(rowd, wmap)
                w = _f("RANK_W_FEATURE_IC", 0.04)
                comps["feature_ic"] = w * float(feat_s)
                score += comps["feature_ic"]
        except Exception as e:
            log.debug("[RANK] feature_ic %s: %s", inp.ticker, e)

    # Classic value / DCF intrinsic value (book formulas IV + TV).
    if _b("USE_VALUE_INVESTING", True):
        try:
            from analytics.value_investing import value_investing_rank_boost

            v_boost, v_meta = value_investing_rank_boost(inp.ticker)
            comps["value_investing"] = float(v_boost)
            score += comps["value_investing"]
            meta["value_investing"] = v_meta
            if abs(comps["value_investing"]) > 1e-6:
                meta["strategies"].append("value_investing")
        except Exception as e:
            log.debug("[RANK] value_investing %s: %s", inp.ticker, e)

    # Full investing-book composite (GARP, GGM income, factors, technical, …).
    if _b("USE_INVESTING_BOOK", True):
        try:
            from investing.integrate import book_rank_boost

            b_boost, b_meta = book_rank_boost(inp.ticker)
            comps["investing_book"] = float(b_boost)
            score += comps["investing_book"]
            meta["investing_book"] = b_meta
            if abs(comps["investing_book"]) > 1e-6:
                meta["strategies"].append("investing_book")
        except Exception as e:
            log.debug("[RANK] investing_book %s: %s", inp.ticker, e)

    if _b("USE_SHELDON_HEAD", True):
        try:
            from analytics.sheldon_head import sheldon_rank_boost

            sh_boost, sh_meta = sheldon_rank_boost(inp.ticker)
            comps["sheldon"] = float(sh_boost or 0.0)
            score += comps["sheldon"]
            meta["sheldon"] = sh_meta
            if abs(comps["sheldon"]) > 1e-6:
                meta["strategies"].append("sheldon_head")
        except Exception as e:
            log.debug("[RANK] sheldon %s: %s", inp.ticker, e)

    if _b("USE_ALGO_PIPELINE", True):
        try:
            from analytics.algo_generation import algo_rank_boost
            from analytics.algo_universe import features_from_signals

            feats = features_from_signals(
                ticker=inp.ticker,
                p_up=float(inp.p_up),
                exec_conf=float(inp.exec_conf),
                sent=float(inp.sent),
                news_factor=float(inp.news_factor),
                mom_5d=float(inp.mom_5d),
                rs_spy=float(inp.rs_spy),
                vol_ratio=float(inp.vol_ratio),
                dip_signal=float(inp.dip_signal),
                neural_p_up=inp.neural_p_up,
            )
            a_boost, a_meta = algo_rank_boost(inp.ticker, feats)
            comps["algo"] = float(a_boost or 0.0)
            score += comps["algo"]
            meta["algo"] = a_meta
            if abs(comps["algo"]) > 1e-6:
                meta["strategies"].append("algo_generation")
            from analytics.algo_generation import algo_overlay_boost

            o_boost, o_meta = algo_overlay_boost(inp.ticker)
            comps["algo_overlay"] = float(o_boost or 0.0)
            score += comps["algo_overlay"]
            meta["algo_overlay"] = o_meta
            if abs(comps["algo_overlay"]) > 1e-6:
                meta["strategies"].append("algo_overlay")
        except Exception as e:
            log.debug("[RANK] algo %s: %s", inp.ticker, e)

    # Hidden pattern anomalies + cross-listing / regional price imbalances.
    if _b("USE_HIDDEN_PATTERN_ANOMALY", True) or _b("USE_MARKET_IMBALANCE", True):
        try:
            from analytics.hidden_pattern_anomaly import hidden_anomaly_rank_boost

            a_boost, a_meta = hidden_anomaly_rank_boost(inp.ticker)
            comps["hidden_anomaly"] = float(a_boost or 0.0)
            score += comps["hidden_anomaly"]
            meta["hidden_anomaly"] = a_meta
            if abs(comps["hidden_anomaly"]) > 1e-6:
                meta["strategies"].append("hidden_pattern_anomaly")
        except Exception as e:
            log.debug("[RANK] hidden_anomaly %s: %s", inp.ticker, e)

    # Public event clocks (trial binaries / guidance / conferences) — not unpublished results.
    if _b("USE_EVENT_CALENDAR", True) and str(resolved) not in ("hft",):
        try:
            from analytics.event_calendar import event_rank_boost

            ret_1d = None
            if inp.row is not None:
                rowd = inp.row if isinstance(inp.row, dict) else dict(inp.row)
                for k in ("ret_1d", "return_1d", "pct_change"):
                    if rowd.get(k) is not None:
                        try:
                            ret_1d = float(rowd[k])
                            break
                        except (TypeError, ValueError):
                            pass
            e_boost, e_meta = event_rank_boost(
                inp.ticker,
                mom_5d=float(inp.mom_5d),
                ret_1d=ret_1d,
                sleeve=str(resolved),
            )
            w = _f("RANK_W_EVENT_CALENDAR", 0.10)
            comps["event_calendar"] = w * float(e_boost)
            score += comps["event_calendar"]
            meta["event_calendar"] = e_meta
            if abs(comps["event_calendar"]) > 1e-6:
                meta["strategies"].append("event_calendar")
        except Exception as e:
            log.debug("[RANK] event_calendar %s: %s", inp.ticker, e)

    # Learned print-gap model (history-trained, online-adjusted) — not unpublished results.
    if _b("USE_EVENT_LEARN", True) and str(resolved) not in ("hft",):
        try:
            from analytics.event_learn import event_learn_rank_boost

            ret_1d_el = None
            if inp.row is not None:
                rowd = inp.row if isinstance(inp.row, dict) else dict(inp.row)
                for k in ("ret_1d", "return_1d", "pct_change"):
                    if rowd.get(k) is not None:
                        try:
                            ret_1d_el = float(rowd[k])
                            break
                        except (TypeError, ValueError):
                            pass
            vol_el = 0.0
            try:
                vol_el = float(getattr(inp, "vol_20", 0.0) or 0.0)
            except Exception:
                vol_el = 0.0
            el_boost, el_meta = event_learn_rank_boost(
                inp.ticker,
                mom_5d=float(inp.mom_5d),
                ret_1d=ret_1d_el,
                vol_20=vol_el,
                sleeve=str(resolved),
            )
            w_el = _f("RANK_W_EVENT_LEARN", 0.10)
            comps["event_learn"] = w_el * float(el_boost)
            score += comps["event_learn"]
            meta["event_learn"] = el_meta
            if abs(comps["event_learn"]) > 1e-6:
                meta["strategies"].append("event_learn")
        except Exception as e:
            log.debug("[RANK] event_learn %s: %s", inp.ticker, e)

    # Ingenious public tells (peer cascade / 8-K / Form 4 / crowding) — not unpublished results.
    if _b("USE_EVENT_INGENUITY", True) and str(resolved) not in ("hft",):
        try:
            from analytics.event_ingenuity import event_ingenuity_rank_boost
            from intel.historical_events import earnings_event

            snap = earnings_event(inp.ticker)
            dte_i = snap.get("days_to")
            ret_1d_ing = None
            if inp.row is not None:
                rowd = inp.row if isinstance(inp.row, dict) else dict(inp.row)
                for k in ("ret_1d", "return_1d", "pct_change"):
                    if rowd.get(k) is not None:
                        try:
                            ret_1d_ing = float(rowd[k])
                            break
                        except (TypeError, ValueError):
                            pass
            ing_b, ing_m = event_ingenuity_rank_boost(
                inp.ticker,
                mom_5d=float(inp.mom_5d),
                ret_1d=ret_1d_ing,
                dte=int(dte_i) if dte_i is not None else None,
                hist_abs_1d=float(snap.get("avg_abs_move_1d") or 0.0),
                sleeve=str(resolved),
            )
            w_ing = _f("RANK_W_EVENT_INGENUITY", 0.12)
            comps["event_ingenuity"] = w_ing * float(ing_b)
            score += comps["event_ingenuity"]
            meta["event_ingenuity"] = ing_m
            if abs(comps["event_ingenuity"]) > 1e-6:
                meta["strategies"].append("event_ingenuity")
        except Exception as e:
            log.debug("[RANK] event_ingenuity %s: %s", inp.ticker, e)

    # Proven factors + Hedge/Thompson/Platt — highest-conviction names first.
    if _b("USE_PROVEN_ONLINE", True) and str(resolved) not in ("hft",):
        try:
            from analytics.proven_online import proven_online_rank_boost
            from analytics.residual_mom import attach_resid_mom

            row = attach_resid_mom(inp.row, inp.closes, inp.bench_closes)
            po_b, po_m = proven_online_rank_boost(
                inp.ticker,
                p_up=float(inp.p_up),
                exec_c=float(inp.exec_conf),
                mom_5d=float(inp.mom_5d),
                rs_spy=float(inp.rs_spy),
                hmm=float(inp.hmm_market_score),
                row=row,
                sleeve=str(resolved),
            )
            w_po = _f("RANK_W_PROVEN_ONLINE", 0.28)
            comps["proven_online"] = w_po * float(po_b)
            score += comps["proven_online"]
            meta["proven_online"] = po_m
            if abs(comps["proven_online"]) > 1e-6:
                meta["strategies"].append("proven_online")
        except Exception as e:
            log.debug("[RANK] proven_online %s: %s", inp.ticker, e)

    # Crypto / commodity / miner driver math — 0 on ordinary equities and on HFT.
    if _b("USE_ALT_DRIVERS", True) and str(resolved) not in ("hft",):
        try:
            from analytics.alt_drivers import alt_rank_boost

            ad_b, ad_m = alt_rank_boost(inp.ticker, inp.row)
            w_ad = _f("RANK_W_ALT_DRIVERS", 0.16)
            comps["alt_drivers"] = w_ad * float(ad_b)
            score += comps["alt_drivers"]
            meta["alt_drivers"] = ad_m
            if abs(comps["alt_drivers"]) > 1e-6:
                meta["strategies"].append("alt_drivers")
            if str(resolved) in ("weekly", "longterm"):
                w_fx = _f("RANK_W_FX_COMMOD", 0.0)
                if abs(w_fx) > 1e-12 and abs(ad_b) > 1e-9:
                    comps["currency_commodity"] = w_fx * float(ad_b)
                    score += comps["currency_commodity"]
        except Exception as e:
            log.debug("[RANK] alt_drivers %s: %s", inp.ticker, e)

    # Cross-company linkage math (corr/beta/coint/lead-lag between tied names).
    if _b("USE_CROSS_COMPANY_LINKS", True):
        try:
            from analytics.cross_company_links import cross_company_rank_boost

            c_boost, c_meta = cross_company_rank_boost(inp.ticker)
            comps["cross_company"] = float(c_boost or 0.0)
            score += comps["cross_company"]
            meta["cross_company"] = c_meta
            if abs(comps["cross_company"]) > 1e-6:
                meta["strategies"].append("cross_company_links")
        except Exception as e:
            log.debug("[RANK] cross_company %s: %s", inp.ticker, e)

    # Pure-math pivot: reweight components (boost formulas; soften narrative — keep news→z).
    try:
        from analytics.math_pivot import apply_pivot_to_components, pivot_enabled

        if pivot_enabled():
            pivoted = apply_pivot_to_components(comps)
            # Rebuild score from pivoted components (core already in score baseline).
            delta = sum(pivoted.values()) - sum(comps.values())
            comps = pivoted
            score += float(delta)
            meta["pure_math_pivot"] = True
    except Exception as e:
        log.debug("[RANK] math_pivot %s: %s", inp.ticker, e)

    if runtime == "paper":
        try:
            from self_modify.strategy_overlay import paper_score_boost

            boost = paper_score_boost(
                inp.ticker,
                score,
                {
                    "hit_rate": float((inp.crowd_meta or {}).get("hit_rate", 0.5)),
                    "deployed_frac": float(os.getenv("PAPER_SIM_DEPLOY_FRAC", "0") or 0),
                },
            )
            comps["overlay"] = boost
            score += boost
        except Exception:
            pass
        try:
            from cortex.integrate import cortex_paper_boost

            cb = cortex_paper_boost(
                inp.ticker,
                score,
                {
                    "hit_rate": float((inp.crowd_meta or {}).get("hit_rate", 0.5)),
                    "neural_p_up": inp.neural_p_up,
                },
            )
            comps["cortex"] = cb
            score += cb
        except Exception:
            pass
        if os.getenv("AGI_CUSTOM_HOOKS_ENABLED", "true").lower() in ("1", "true", "yes"):
            try:
                from self_modify.custom_hooks import equity_rank_boost

                hook = equity_rank_boost(
                    inp.ticker,
                    score,
                    {
                        "p_up": inp.p_up,
                        "neural_p_up": inp.neural_p_up,
                        "deployed_frac": float(os.getenv("PAPER_SIM_DEPLOY_FRAC", "0") or 0),
                        **(inp.crowd_meta or {}),
                    },
                )
                comps["custom_hooks"] = hook
                score += hook
            except Exception:
                pass

    # Curriculum soft factors (weekly/longterm only) — never HFT
    try:
        fund_sc = float((inp.fund or {}).get("fund_score", 0.0)) if inp.fund else 0.0
        soft = curriculum_soft_boosts(
            sleeve=str(resolved),
            macro_bundle=(inp.crowd_meta or {}).get("macro_bundle")
            if isinstance(inp.crowd_meta, dict)
            else None,
            fund_score=fund_sc,
        )
        for k, v in soft.items():
            comps[k] = float(v)
            score += float(v)
        if soft:
            meta["strategies"].append("curriculum_macro_passive")
            meta["curriculum_soft"] = soft
    except Exception as e:
        log.debug("[RANK] curriculum_soft %s: %s", inp.ticker, e)

    meta["hf"] = hf_meta
    return RankResult(score=float(score), components=comps, meta=meta)


def use_unified_rank() -> bool:
    return _b("USE_UNIFIED_RANK_PIPELINE", True)


def vectorized_target_weights(
    scores: "np.ndarray | list[float]",
    *,
    total_capital: float,
    max_weight: float = 0.12,
    min_score: float = 0.0,
    temperature: float = 1.0,
) -> np.ndarray:
    """Vectorized cross-sectional capital allocation across ranked names.

    Replaces per-ticker sizing loops with a single matrix op:
      1. z-score the scores cross-sectionally (mean/std over the candidate set),
      2. softmax(z / temperature) over names whose score clears `min_score`,
      3. cap any single name at `max_weight` and renormalize the remainder so the
         book consumes ~100% of `total_capital` (the full allowed buying power).

    Returns a notional array (USD) aligned to `scores`. Names below `min_score`
    get 0. If nobody clears the floor, the array is all zeros — leftover cash
    stays cash. Do not force-invest dummy scores.
    """
    s = np.asarray(scores, dtype=float).ravel()
    n = s.size
    if n == 0 or total_capital <= 0:
        return np.zeros(n, dtype=float)

    eligible = s > float(min_score)
    if not eligible.any():
        # Cash can sit. Forcing 100% into zero-score names is how idle-fill
        # dumped $12k into SOLUSD at dummy p=0.55 and went red.
        return np.zeros(n, dtype=float)

    z = np.zeros(n, dtype=float)
    sd = float(s[eligible].std())
    if sd > 1e-9:
        z[eligible] = (s[eligible] - float(s[eligible].mean())) / sd

    temp = max(1e-6, float(temperature))
    w = np.zeros(n, dtype=float)
    ez = np.exp(np.clip(z[eligible] / temp, -50.0, 50.0))
    w[eligible] = ez / ez.sum()

    # Iterative water-filling: cap at max_weight, redistribute excess only to names that
    # are still strictly below the cap (names already AT the cap are frozen, otherwise
    # they ping-pong above it and breach the per-name risk guard).
    cap = max(1e-6, min(1.0, float(max_weight)))
    for _ in range(128):
        over = w > cap + 1e-12
        if not over.any():
            break
        excess = float((w[over] - cap).sum())
        w[over] = cap
        free = eligible & (w > 0) & (w < cap - 1e-12)
        if not free.any() or excess <= 1e-12:
            break  # infeasible to fully invest under the cap → leave residual idle
        w[free] += excess * (w[free] / w[free].sum())

    # Water-filling conserves the unit sum whenever the caps are feasible
    # (n_eligible * cap >= 1), so the book is fully invested. When there are too few
    # names to deploy fully under the cap, we deliberately leave the residual idle
    # rather than breach the per-name risk cap — the cap is a hard guard.
    total = float(w.sum())
    if total > 1.0 + 1e-9:
        w /= total
    return w * float(total_capital)
