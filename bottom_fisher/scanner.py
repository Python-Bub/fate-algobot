"""Main bottom-fisher scan pipeline."""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any

from bottom_fisher.ai_agent import review_batch
from bottom_fisher.config import BottomFisherConfig, bottom_fisher_enabled
from bottom_fisher.news_radar import discover_news_mentions, scan_news_for_ticker
from bottom_fisher.policy import BottomFisherPolicyAgent
from bottom_fisher.trade_gate import trade_eligible
from bottom_fisher.store import save_scan
from bottom_fisher.technical import score_recovery
from bottom_fisher.universe import BottomCandidate, load_bottom_universe
from utils import log


def _composite_row(
    cand: BottomCandidate,
    recovery: dict,
    news: dict,
    ai: dict | None,
    cfg: BottomFisherConfig,
) -> dict[str, Any]:
    ai_score = float(ai.get("ai_score", 0.5)) if ai else 0.5
    composite = (
        cfg.rank_weight_recovery * float(recovery.get("recovery_score", 0))
        + cfg.rank_weight_news * float(news.get("catalyst_score", 0))
        + cfg.rank_weight_ai * ai_score
    )
    return {
        "ticker": cand.ticker,
        "ret_60d": cand.ret_60d,
        "ret_20d": cand.ret_20d,
        "ret_5d": cand.ret_5d,
        "ret_1d": cand.ret_1d,
        "drawdown_52w": cand.drawdown_52w,
        "last_close": cand.last_close,
        "bottom_rank_pct": cand.bottom_rank_pct,
        "recovery_score": recovery.get("recovery_score", 0),
        "recovery_rationale": recovery.get("rationale", ""),
        "reversal_bar": recovery.get("reversal_bar", 0),
        "trend_stabilizing": recovery.get("trend_stabilizing", 0),
        "momentum_turn_score": recovery.get("momentum_turn_score", 0),
        "catalyst_score": news.get("catalyst_score", 0),
        "news_rationale": news.get("rationale", ""),
        "top_headline": news.get("top_headline", ""),
        "news_trigger": news.get("news_trigger", False),
        "ai_grade": (ai or {}).get("grade", "C"),
        "ai_verdict": (ai or {}).get("verdict", "hold"),
        "ai_confidence": (ai or {}).get("confidence", 0),
        "ai_score": ai_score,
        "recovery_thesis": (ai or {}).get("recovery_thesis", ""),
        "risk_flags": (ai or {}).get("risk_flags", []),
        "composite_score": float(composite),
        "source": "bottom_fisher",
    }


def run_bottom_fisher_scan(
    *,
    max_symbols: int | None = None,
    skip_ai: bool = False,
    cfg: BottomFisherConfig | None = None,
) -> dict[str, Any]:
    """Full scan: bottom universe → technical → news → AI → ranked picks."""
    if not bottom_fisher_enabled():
        return {"picks": [], "skipped": "USE_BOTTOM_FISHER=false"}

    cfg = cfg or BottomFisherConfig.from_env()
    if max_symbols:
        cfg = BottomFisherConfig(**{**cfg.__dict__, "max_scan_symbols": max_symbols})

    t0 = time.perf_counter()
    universe = load_bottom_universe(cfg)
    if not universe:
        return {"picks": [], "error": "empty_universe"}

    extra = discover_news_mentions()
    if extra:
        log.info("[BOTTOM_FISHER] news discovery tickers: %s", extra[:8])
        known = {c.ticker for c in universe}
        for sym in extra:
            if sym not in known and len(universe) < cfg.max_scan_symbols + 20:
                universe.append(
                    BottomCandidate(sym, 0, 0, 0, 0, -0.1, 0, 0, 1.0)
                )

    rows: list[dict] = []
    scored_all: list[dict] = []
    ohlc_cache: dict = {}
    batch_syms = [c.ticker for c in universe]
    try:
        from data_platform.market_prices import download

        raw = download(
            batch_syms[: min(len(batch_syms), 200)],
            period="1y",
            interval="1d",
        )
        if raw is not None and not raw.empty:
            from bottom_fisher.universe import frame_for_symbol

            for sym in batch_syms[:200]:
                try:
                    sub = frame_for_symbol(raw, sym)
                    if sub is not None and not getattr(sub, "empty", True):
                        ohlc_cache[sym] = sub
                except Exception:
                    pass
    except Exception as e:
        log.debug("[BOTTOM_FISHER] bulk ohlc: %s", e)

    n_low_rec = n_low_news = n_ok_bars = 0
    for cand in universe:
        df = ohlc_cache.get(cand.ticker)
        # Pass None (not a bad frame) so score_recovery can per-symbol fetch.
        if df is not None and (getattr(df, "empty", True) or len(df) < 30):
            df = None
        rec = score_recovery(cand, df)
        soft = _composite_row(
            cand,
            rec.to_dict(),
            {"catalyst_score": 0, "rationale": "pre", "top_headline": "", "news_trigger": False},
            None,
            cfg,
        )
        scored_all.append(soft)
        if rec.recovery_score <= 0:
            continue
        n_ok_bars += 1
        if rec.recovery_score < cfg.min_recovery_score * 0.85:
            n_low_rec += 1
            continue
        news = scan_news_for_ticker(cand.ticker, cfg) if cfg.use_news_radar else None
        news_d = news.to_dict() if news else {"catalyst_score": 0, "rationale": "off", "top_headline": "", "news_trigger": False}
        if news_d.get("catalyst_score", 0) < cfg.min_news_catalyst and rec.recovery_score < cfg.min_recovery_score:
            if not news_d.get("news_trigger"):
                n_low_news += 1
                continue
        row = _composite_row(cand, rec.to_dict(), news_d, None, cfg)
        row["trade_eligible"] = trade_eligible(row, cfg)
        rows.append(row)

    # Survey fallback: never return an empty bottom-50% scan — keep top recovery
    # names for ranking/train queue even when hard gates wipe the trade pool.
    top_k = int(os.getenv("BOTTOM_FISHER_TOP_K", "25"))
    if not rows and scored_all:
        scored_all.sort(key=lambda r: -float(r.get("recovery_score", 0)))
        survey_n = max(top_k, int(os.getenv("BOTTOM_FISHER_SURVEY_FLOOR", "25")))
        for soft in scored_all[:survey_n]:
            if float(soft.get("recovery_score", 0)) <= 0:
                continue
            soft = dict(soft)
            soft["survey_only"] = True
            soft["trade_eligible"] = False
            soft["source"] = "bottom_fisher_survey"
            rows.append(soft)
        log.warning(
            "[BOTTOM_FISHER] hard gates empty (low_rec=%d low_news=%d ok_bars=%d) — "
            "survey floor kept %d names",
            n_low_rec,
            n_low_news,
            n_ok_bars,
            len(rows),
        )

    rows.sort(key=lambda r: -float(r["composite_score"]))
    ai_reviews = []
    if cfg.use_ai_review and not skip_ai and rows:
        ai_reviews = [r.to_dict() for r in review_batch(rows, cfg)]
        ai_map = {r["ticker"]: r for r in ai_reviews}
        for row in rows:
            ai = ai_map.get(row["ticker"])
            if ai:
                row.update(
                    {
                        "ai_grade": ai.get("grade"),
                        "ai_verdict": ai.get("verdict"),
                        "ai_confidence": ai.get("confidence"),
                        "ai_score": ai.get("ai_score"),
                        "recovery_thesis": ai.get("recovery_thesis"),
                        "risk_flags": ai.get("risk_flags"),
                    }
                )
                row["composite_score"] = (
                    cfg.rank_weight_recovery * row["recovery_score"]
                    + cfg.rank_weight_news * row["catalyst_score"]
                    + cfg.rank_weight_ai * float(ai.get("ai_score", 0.5))
                )
                if not row.get("survey_only"):
                    row["trade_eligible"] = trade_eligible(row, cfg)
        rows = [r for r in rows if r.get("ai_verdict") != "reject" or float(r.get("ai_confidence", 0)) < 0.5]
        rows.sort(key=lambda r: -float(r["composite_score"]))

    picks = rows[:top_k]
    trade_ok = sum(1 for p in picks if p.get("trade_eligible"))
    elapsed = time.perf_counter() - t0

    # Queue survey / trade-eligible bottom names for daily+LSTM heads (promote into
    # trainable coverage — never prune these).
    try:
        from tools.listing_watch import queue_symbols

        promote = [
            str(p["ticker"]).upper()
            for p in picks
            if p.get("trade_eligible") or float(p.get("recovery_score", 0)) >= cfg.min_recovery_score * 0.7
        ]
        if promote and os.getenv("BOTTOM_FISHER_QUEUE_TRAIN", "true").lower() in ("1", "true", "yes"):
            added = queue_symbols(promote[: int(os.getenv("BOTTOM_FISHER_QUEUE_CAP", "40"))])
            log.info("[BOTTOM_FISHER] queued %d for new-head training", len(added) if isinstance(added, list) else added)
        if promote and os.getenv("BOTTOM_FISHER_PROMOTE_TOP50", "true").lower() in ("1", "true", "yes"):
            from bottom_fisher.promote import record_and_train

            # Strong multi-head stack for names climbing out of the bottom half.
            promo = record_and_train(
                promote[: int(os.getenv("BOTTOM_FISHER_PROMOTE_CAP", "20"))],
                train=os.getenv("BOTTOM_FISHER_PROMOTE_TRAIN_NOW", "false").lower()
                in ("1", "true", "yes"),
            )
            log.info("[BOTTOM_FISHER] top50-quality promote %s", {k: promo.get(k) for k in ("added", "trained")})
    except Exception as e:
        log.debug("[BOTTOM_FISHER] train queue: %s", e)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_sec": round(elapsed, 1),
        "universe_scanned": len(universe),
        "candidates_passed": len(rows),
        "picks": picks,
        "funnel": {
            "ok_bars": n_ok_bars,
            "low_recovery": n_low_rec,
            "low_news": n_low_news,
        },
        "config": {
            "bottom_percentile": cfg.bottom_percentile,
            "min_recovery": cfg.min_recovery_score,
        },
    }
    save_scan(payload)

    if os.getenv("BOTTOM_FISHER_POLICY_ENABLED", "true").lower() in ("1", "true", "yes"):
        agent = BottomFisherPolicyAgent()
        agent.observe_and_adapt({"hit_rate": 0.5, "avg_return": 0.0, "n_picks": len(picks)})

    log.info(
        "[BOTTOM_FISHER] scan done picks=%d trade_eligible=%d passed=%d elapsed=%.1fs",
        len(picks),
        trade_ok,
        len(rows),
        elapsed,
    )
    return payload
