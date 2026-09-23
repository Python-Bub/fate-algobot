"""Learn from realized Alpaca / paper closes (losers penalized harder via asymmetric_loss)."""

from __future__ import annotations

from utils import log


def learn_from_realized_trade(
    ticker: str,
    side: str,
    realized_return: float,
    *,
    state: dict[str, float] | None = None,
    source: str = "fortress",
    bars_held: int = 1,
) -> None:
    """Single-step meta + neural replay update for one closed leg."""
    sym = str(ticker).strip().upper()
    if not sym:
        return
    entry = ""
    if state:
        entry = str(
            state.get("opened_at")
            or state.get("opened_at_utc")
            or state.get("entry_ts")
            or ""
        )
    credit_key = ""
    if entry:
        try:
            from analytics.honest_learn import already_credited, trade_key

            credit_key = trade_key(sym, entry_ts=entry, side=side)
            if already_credited(credit_key):
                log.info("[LEARN] skip %s — already credited", credit_key)
                return
        except Exception:
            credit_key = ""
    st = state or {
        "p_short": 0.5,
        "p_long": 0.5,
        "p_gap": 0.0,
        "vol_regime_ratio": 0.0,
        "sentiment_impulse": 0.0,
        "regime_transition_flag": 0.0,
        "alpha_proxy_20": 0.0,
    }
    try:
        from analytics.asymmetric_loss import asymmetric_reward
        from online_learning.neural_ensemble import (
            record_neural_experience,
            train_neural_ensemble_for_ticker,
            use_neural_ensemble,
        )
        from online_learning.weight_updater import online_update_meta_for_trade, use_online_updater

        # realized_return here is broker position P&L (Alpaca plpc) — already signed per leg.
        rw = asymmetric_reward(side, float(realized_return), bars_held=bars_held, position_pnl=True)
        if use_online_updater():
            rep = online_update_meta_for_trade(sym, st, side, rw.reward)
            if rep.applied:
                log.info(
                    "[LEARN] %s %s %s ret=%.3f%% reward=%.3f delta_l2=%.4f",
                    source,
                    sym,
                    side,
                    100 * float(realized_return),
                    rw.reward,
                    rep.delta_l2,
                )
        if use_neural_ensemble():
            record_neural_experience(
                ticker=sym,
                state=st,
                action=side,
                realized_return=float(realized_return),
                reward=float(rw.reward),
            )
            train_neural_ensemble_for_ticker(sym)
        try:
            from analytics.industries.industry_rl import update_from_trade
            from analytics.industries.integration import get_industry_profile

            prof = get_industry_profile(sym, use_cache=True)
            update_from_trade(
                sym,
                float(realized_return),
                side,
                blend_weights=prof.get("blend_weights"),
                reward=float(rw.reward),
                bars_held=bars_held,
            )
        except Exception:
            pass
        try:
            from analytics.algo_universe import learn_from_outcome

            row = None
            if state:
                row = {
                    "p_up": float(state.get("p_up") or state.get("p_short") or 0.5),
                    "execution_confidence": float(state.get("execution_confidence") or 0.5),
                    "momentum_5d": float(state.get("momentum_5d") or 0.0),
                    "sentiment": float(state.get("sentiment_impulse") or 0.0),
                }
            learn_from_outcome(sym, float(realized_return), features=row, side=side)
        except Exception:
            pass
        try:
            from intel.insider_signals import learn_from_trade_outcome

            learn_from_trade_outcome(sym, float(realized_return))
        except Exception:
            pass
        try:
            from analytics.hidden_pattern_learn import learn_from_trade_outcome as learn_hidden

            hr = learn_hidden(sym, side, float(realized_return), bars_held=bars_held)
            if hr.get("applied"):
                log.info(
                    "[LEARN] %s %s hidden_pattern success=%s fams=%s blend_scale=%.3f",
                    source,
                    sym,
                    hr.get("success"),
                    hr.get("families"),
                    float(hr.get("blend_scale") or 1.0),
                )
        except Exception:
            pass
        try:
            from analytics.event_learn import credit_event_outcome

            mom = float((state or {}).get("momentum_5d") or (state or {}).get("mom_5d") or 0.0)
            er = credit_event_outcome(sym, float(realized_return), mom_5d=mom)
            if er.get("applied"):
                log.info(
                    "[LEARN] %s %s event_learn skill=%s n=%s",
                    source,
                    sym,
                    er.get("skill"),
                    er.get("n_updates"),
                )
        except Exception:
            pass
        try:
            from analytics.proven_online import credit_outcome as credit_proven

            pr = credit_proven(sym, float(realized_return), side=side)
            if pr.get("applied"):
                log.info(
                    "[LEARN] %s %s proven_online n=%s win=%s p_hedge=%s",
                    source,
                    sym,
                    pr.get("n_updates"),
                    pr.get("win"),
                    pr.get("p_hedge"),
                )
        except Exception:
            pass
        try:
            from analytics.ultimate_learning_engine import (
                active_for_symbol,
                credit_outcome,
                enabled as ule_on,
                last_active,
            )

            if ule_on():
                # realized_return is position P&L (positive = profitable long OR short).
                # Do not flip SHORT — that punished winning shorts and rewarded losers.
                success = float(realized_return) > 0
                reward = float(realized_return)
                chans = active_for_symbol(sym) or last_active() or None
                ule = credit_outcome(
                    success=success,
                    active=chans,
                    reward=reward,
                )
                if ule.get("applied"):
                    log.info(
                        "[ULE] %s %s credit success=%s reward=%.4f active=%s",
                        source,
                        sym,
                        success,
                        reward,
                        last_active(),
                    )
        except Exception:
            pass
    except Exception as e:
        log.debug("[LEARN] %s %s skipped: %s", source, sym, e)
    if credit_key:
        try:
            from analytics.honest_learn import credit_once

            credit_once(credit_key)
        except Exception:
            pass
