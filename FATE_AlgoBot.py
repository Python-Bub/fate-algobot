import os
import sys

from dotenv import load_dotenv

load_dotenv()

from data_platform.market_prices import configure_process_prices

configure_process_prices()

from feature_engineering import build_features
from ml_model import predict_row
from utils import log


def train():
    from model_trainer import train_models

    train_models()


def optimize_one(ticker):
    from ml_model import optimize_model

    log.info("Optimizing %s", ticker)
    optimize_model(ticker)


def backtest_one(ticker):
    log.info("Backtesting %s", ticker)
    df = build_features(ticker, "2023-01-01", None)
    if df.empty:
        log.warning("[BACKTEST] Skipping %s — no data", ticker)
        return

    df = df.dropna(subset=["target", "target_long"])
    path = os.path.join("models", f"{ticker}_model.pkl")
    if not os.path.isfile(path):
        log.warning("[BACKTEST] No model for %s at %s", ticker, path)
        return

    row = df.iloc[-2]
    signal, conf = predict_row(path, row)
    log.info("[BACKTEST] %s → class=%s p_up=%.3f", ticker, signal, conf)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "train"
    arg = sys.argv[2] if len(sys.argv) > 2 else None

    if mode == "train":
        train()
    elif mode == "optimize":
        if not arg:
            log.error("Usage: python FATE_AlgoBot.py optimize TICKER")
            sys.exit(1)
        optimize_one(arg)
    elif mode == "backtest":
        if not arg:
            log.error("Usage: python FATE_AlgoBot.py backtest TICKER")
            sys.exit(1)
        backtest_one(arg)
    elif mode == "meta":
        from model_inspector import analyze_models

        analyze_models()
    elif mode == "universe-download":
        from universe_provider import download_us_listed_symbols

        download_us_listed_symbols()
    elif mode == "universe-refresh":
        os.environ["UNIVERSE_FETCH_NETWORK"] = "true"
        from universe_provider import download_us_listed_symbols

        log.info("[CLI] universe-refresh: forcing UNIVERSE_FETCH_NETWORK=true")
        syms = download_us_listed_symbols()
        log.info("[CLI] universe-refresh wrote %d symbols", len(syms))
    elif mode == "alpaca-check":
        from alpaca_diag import diagnose

        diagnose()
    elif mode == "train-universe":
        from model_trainer import train_universe_batch

        mx = int(arg) if arg else None
        refresh = os.getenv("REFRESH_UNIVERSE", "false").lower() in ("1", "true", "yes")
        train_universe_batch(max_symbols=mx, refresh_universe=refresh)
    elif mode == "train-crypto":
        from model_trainer import _train_single_ticker
        from crypto_universe import CRYPTO_YAHOO

        os.environ["FORCE_YAHOO_PRICES"] = "true"
        os.environ["PRICE_DATA_SOURCE"] = "yfinance"
        targets = [t.strip().upper() for t in (arg or "").split(",") if t.strip()] or CRYPTO_YAHOO
        log.info("[CLI] train-crypto: %d symbols", len(targets))
        for sym in targets:
            try:
                _train_single_ticker(sym)
            except Exception:
                log.exception("[CRYPTO] %s failed", sym)
    elif mode == "clear-failed":
        import json as _json
        ck_path = arg or "data/train_checkpoint.json"
        if not os.path.isfile(ck_path):
            log.warning("[CLI] No checkpoint at %s", ck_path)
        else:
            with open(ck_path, encoding="utf-8") as f:
                ck = _json.load(f)
            n = len(ck.get("failed", {}) or {})
            ck["failed"] = {}
            with open(ck_path, "w", encoding="utf-8") as f:
                _json.dump(ck, f, indent=0)
            log.info("[CLI] Cleared %d failed entries from %s", n, ck_path)
    elif mode == "data-sync":
        from data_platform.ingest_yahoo_universe import sync_universe

        sync_mode = (arg or "incremental").strip().lower()
        if sync_mode not in ("full", "incremental"):
            log.error("Usage: python FATE_AlgoBot.py data-sync [full|incremental]")
            sys.exit(1)
        mx = int(sys.argv[3]) if len(sys.argv) > 3 else None
        rep = sync_universe(mode=sync_mode, max_symbols=mx, rebuild_registry=True)
        log.info("[DATA_SYNC] %s", rep)
    elif mode == "data-audit":
        from data_platform.ingest_yahoo_universe import audit_existing_cache

        mx = int(arg) if arg and arg.isdigit() else None
        rep = audit_existing_cache(max_symbols=mx)
        log.info(
            "[DATA_AUDIT] checked=%d ok=%d issues=%d",
            rep.get("symbols_checked", 0),
            rep.get("ok", 0),
            rep.get("issue_count", 0),
        )
    elif mode == "registry-refresh":
        from data_platform.symbol_registry import build_registry, save_registry
        from universe_provider import load_universe_symbols

        syms = load_universe_symbols(refresh=False)
        reg = build_registry(syms)
        p = save_registry(reg)
        log.info("[REGISTRY] wrote %s (%d symbols)", p, len(reg))
    elif mode == "replay-health":
        from data_platform.replay_store import replay_health_report

        rep = replay_health_report()
        log.info("[REPLAY] %s", rep)
    elif mode == "drift-report":
        from analytics.drift_monitor import monitor_feature_drift, write_drift_report
        from feature_engineering import build_features
        from ml_model import FEATURES

        t = arg or "AAPL"
        d = build_features(t, "2018-01-01", None)
        if d.empty or len(d) < 200:
            log.error("[DRIFT] Not enough data for %s", t)
            sys.exit(1)
        cut = int(len(d) * 0.7)
        ref = d.iloc[:cut]
        cur = d.iloc[cut:]
        rep = monitor_feature_drift(ref, cur, FEATURES)
        p = write_drift_report(rep, path=f"reports/drift_{t}.json")
        log.info("[DRIFT] %s high=%d med=%d", p, rep["high_count"], rep["medium_count"])
    elif mode == "policy-status":
        from self_modify.policy_agent import _load_json, OVERRIDE_PATH, STATE_PATH

        o = _load_json(OVERRIDE_PATH, {})
        s = _load_json(STATE_PATH, {})
        log.info("[POLICY] overrides=%s", o)
        log.info("[POLICY] state=%s", s)
    elif mode == "policy-rollback":
        from self_modify.rollback_manager import rollback_snapshot

        if not arg:
            log.error("Usage: python FATE_AlgoBot.py policy-rollback SNAPSHOT_PATH")
            sys.exit(1)
        n = rollback_snapshot(arg)
        log.info("[POLICY] rollback restored %d files", n)
    elif mode == "ai-eval-symbol":
        from intel.news_factor_engine import score_symbol_news_factors
        from intel.transcript_factor_engine import score_symbol_transcripts

        t = arg or "AAPL"
        nf = score_symbol_news_factors(t)
        tf = score_symbol_transcripts(t)
        log.info("[AI] news_factor %s", nf)
        log.info("[AI] transcript_factor %s", tf)
    elif mode == "ai-eval-text":
        from intel.llm_signal_agent import score_text_with_llm

        txt = " ".join(sys.argv[2:]).strip()
        if not txt:
            log.error("Usage: python FATE_AlgoBot.py ai-eval-text \"some text...\"")
            sys.exit(1)
        out = score_text_with_llm(txt, symbol=os.getenv("AI_EVAL_SYMBOL", "GENERIC"))
        log.info("[AI] %s", out)
    elif mode == "adapter-export-signals":
        from platform_adapters import export_quantconnect_signals
        from paper_sim_today import run_paper_simulation_today

        mx = int(arg) if arg and arg.isdigit() else 30
        rep = run_paper_simulation_today(max_symbols=mx)
        rows = rep.get("rows", [])
        sigs = [
            {
                "symbol": r.get("ticker"),
                "action": r.get("action"),
                "score": r.get("score"),
                "p_up": r.get("p_up"),
            }
            for r in rows
        ]
        p = export_quantconnect_signals(sigs)
        log.info("[ADAPTER] quantconnect export -> %s", p)
    elif mode == "adapter-export-ninjatrader":
        from platform_adapters import export_ninjatrader_orders
        from paper_sim_today import run_paper_simulation_today

        mx = int(arg) if arg and arg.isdigit() else 20
        rep = run_paper_simulation_today(max_symbols=mx)
        rows = rep.get("rows", [])
        orders = []
        for r in rows:
            a = str(r.get("action", "HOLD"))
            if a not in ("BUY", "SHORT", "SELL_SIGNAL"):
                continue
            orders.append(
                {
                    "symbol": r.get("ticker"),
                    "action": a,
                    "qty": int(float(os.getenv("ORDER_QUANTITY", "1"))),
                    "notional": float(os.getenv("ORDER_NOTIONAL", "500")),
                    "limit_price": float(r.get("sig_close", 0.0)),
                    "notes": "adapter_export",
                }
            )
        p = export_ninjatrader_orders(orders)
        log.info("[ADAPTER] ninjatrader export -> %s", p)
    elif mode == "hummingbot-bridge":
        from platform_adapters import hummingbot_bridge

        cmd = arg or "status"
        out = hummingbot_bridge(cmd)
        log.info("[ADAPTER][HUMMINGBOT] %s", out)
    elif mode == "live-market":
        import subprocess

        subprocess.run(
            [sys.executable, "live_market.py"] + sys.argv[2:],
            check=False,
        )
    elif mode == "fortress":
        import subprocess

        subprocess.run([sys.executable, "fortress_live.py"] + sys.argv[2:], check=False)
    elif mode == "paper-sim":
        from paper_sim_today import run_paper_simulation_today

        mx = int(arg) if arg else None
        run_paper_simulation_today(max_symbols=mx)
    elif mode == "walk-forward":
        from walk_forward import walk_forward_validate

        t = arg or "AAPL"
        walk_forward_validate(t, "2019-01-01")
    elif mode == "rl-train":
        from rl_train import train_rl

        train_rl(arg or "AAPL")
    elif mode == "live":
        from live_listener import run_live

        if not arg:
            log.error("Usage: python FATE_AlgoBot.py live TICKER")
            sys.exit(1)
        run_live(arg)
    else:
        print(f"[ERROR] Unknown mode '{mode}'")
        sys.exit(1)


if __name__ == "__main__":
    main()
