"""HFT keep-alive: pgrep must match real Node argv; earnings must not unref-exit."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_run_all_pgrep_matches_cwd_relative_and_abs_argv():
    text = (ROOT / "run_all.sh").read_text(encoding="utf-8")
    assert "hft_earn_pid()" in text and "earnings/index.js" in text
    assert "hft_obi_pid()" in text and "obi-tape/index.js" in text
    assert 'ps -p "$pid" -o comm=' in text
    assert "subsecond-earnings) found=$(hft_earn_pid)" in text
    assert "cmd_ensure_earnings()" in text
    # Already-running check must precede the 12-sample RTT probe.
    launch = text.split("launch_subsecond_alpaca_paper()")[1].split("checkpoint_done_count()")[0]
    assert launch.find("already running") < launch.find("cmd_exec_delay_probe")
    assert "daemon_loop.sh" in text.split("launch_node()")[1].split("launch_subsecond_alpaca_paper()")[0]


def test_rotator_skips_swap_when_both_alive():
    text = (ROOT / "tools/hft_earnings_rotator.sh").read_text(encoding="utf-8")
    block = text.split("ensure_both()")[1].split("log \"rotator started")[0]
    assert 'pgrep -f "earnings/index.js"' in block
    assert 'pgrep -f "obi-tape/index.js"' in block
    assert "return 0" in block
    assert block.find("return 0") < block.find("swap-hft both")


def test_watchdog_detects_earnings_and_ensures_it():
    text = (ROOT / "tools/stack_watchdog.py").read_text(encoding="utf-8")
    assert r'"subsecond-earnings": r"earnings/index\.js"' in text
    assert r'"subsecond-obi": r"obi-tape/index\.js"' in text
    assert '"./run_all.sh", "ensure-earnings"' in text


def test_earnings_rest_timers_keep_event_loop_alive():
    feed = (ROOT / "hft/src/earnings/rest-market-feed.ts").read_text(encoding="utf-8")
    start = feed.split("start():")[1].split("stop():")[0]
    assert ".unref" not in start
    earn = (ROOT / "hft/src/earnings/index.ts").read_text(encoding="utf-8")
    assert "statsTimer.unref" not in earn
    assert 'process.exit(1)' in earn.split("uncaughtException")[1]


def test_obi_silence_skips_when_rest_is_heartbeat():
    text = (ROOT / "hft/src/obi-tape/index.ts").read_text(encoding="utf-8")
    assert "HFT_REST_POLL_ALWAYS" in text
    assert "restAlways" in text
    assert "process.exit(1)" in text.split("uncaughtException")[1]


def test_hft_boot_cancels_orphan_exits_before_adopt():
    text = (ROOT / "hft/src/obi-tape/index.ts").read_text(encoding="utf-8")
    boot = text.split("orphanTimer")[0].rsplit("void broker", 1)[-1]
    assert "cancelHftExits" in boot
    assert "adoptWorkingBuys" in boot
    assert boot.find("cancelHftExits") < boot.find("adoptWorkingBuys")


def test_boot_cancel_hft_exits_skips_live_longs():
    src = (ROOT / "hft/src/common/alpaca-exec.ts").read_text(encoding="utf-8")
    block = src.split("async cancelHftExits")[1].split("async getOrder")[0]
    assert "orphansOnly" in block
    assert "cachedLongQty" in block


def test_resolve_fill_never_invents_requested_qty():
    src = (ROOT / "hft/src/common/order-lifecycle.ts").read_text(encoding="utf-8")
    assert "snap.filledQty || reqQty" not in src
    assert "interpretFillSnapshot" in src
    assert 'st === "filled" && fq <= 1e-8' in src


def test_last_wins_news_off_hft_full_cash():
    text = (ROOT / "data/deploy_scale.env").read_text(encoding="utf-8")
    last = text.rsplit("cancel≠sell", 1)[-1]
    assert "HFT_NEWS_GATE=false" in last
    assert "HFT_W_NEWS_PROB=0" in last
    assert "FORTRESS_TARGET_DEPLOY_FRAC=1.0" in last
    assert "FORTRESS_MAX_GROSS_FRAC=1.0" in last
    assert "FORTRESS_BP_USE_FRAC=1.0" in last
    assert "FORTRESS_ALLOW_ADD_ON=true" in last
    assert "FORTRESS_FILL_IDLE_CASH=true" in last
    assert "FORTRESS_TICK_TIMEOUT_SEC=25" in last
    assert "HFT_MIN_DUAL_STRENGTH=0.18" in last
    assert "PAPER_SIM_TOP_K=16" in last
    assert "MICRO_SCALP_BP_USE_FRAC=0.30" in last
    assert "HFT_FILL_PERSIST=false" in last
    assert "HFT_BLOCK_ADD_TO_BROKER_LONG=false" in last
    assert "HFT_SKIP_LATENCY_BUDGET=true" in last
    assert "HFT_LIMIT_TIF=ioc" in last
    assert "HFT_REST_POLL_MS=800" in last
    assert "HFT_REST_POLL_ALWAYS=false" in last
    assert "HFT_CANCEL_ENTRY_UNFILLED=false" in last
    dummy = text.rsplit("stop dummy idle-cash dumps", 1)[-1]
    assert "FORTRESS_RELAX_GATES_ON_FILL=false" in dummy
    assert "FORTRESS_VEC_MIN_SCORE=0.02" in dummy
    assert "FORTRESS_OVERNIGHT_CASH_DEPLOY=false" in dummy


def test_hft_flatten_reprices_unfillable_exits():
    risk = (ROOT / "hft/src/obi-tape/obi-tape-risk.ts").read_text(encoding="utf-8")
    assert "sellLimitUnfillable" in risk
    assert "flatten-reprice" in risk
    sig = (ROOT / "hft/src/obi-tape/obi-tape-signals.ts").read_text(encoding="utf-8")
    assert "entry-working-ttl-cancel" in sig
    idx = (ROOT / "hft/src/obi-tape/index.ts").read_text(encoding="utf-8")
    assert "cancel-stale-hft-entries" in idx
    assert "cancelHftEntries" in idx


def test_watchdog_hft_alive_is_node_not_wrapper():
    text = (ROOT / "tools/stack_watchdog.py").read_text(encoding="utf-8")
    assert "def _node_script_alive" in text
    assert '_node_script_alive("obi-tape/index.js")' in text
    assert '_node_script_alive("earnings/index.js")' in text
    assert "algobot-paper" in text
    assert 'role in ("gcp-paper"' in text
    assert '"./run_all.sh", "valuation-news-watch"' in text
    assert '"./run_all.sh", "event-calendar-watch"' in text
    assert '"./run_all.sh", "exec-delay-daemon"' in text


def test_is_running_does_not_treat_wrapper_as_obi():
    text = (ROOT / "run_all.sh").read_text(encoding="utf-8")
    block = text.split("is_running()")[1].split("resolve_pid()")[0]
    assert 'hft_obi_pid' in block
    assert 'subsecond-obi' in block
    assert "case \"$comm\" in" in text.split("hft_obi_pid()")[1].split("hft_earn_pid()")[0]
    assert "node*)" in text.split("hft_obi_pid()")[1].split("hft_earn_pid()")[0]


def test_last_wins_aggressive_ioc_and_dtbp():
    text = (ROOT / "data/deploy_scale.env").read_text(encoding="utf-8")
    last = text.rsplit("IOC take-the-ask", 1)[-1]
    assert "HFT_AGGRESSIVE_ENTRY=true" in last
    assert "HFT_BUY_LOW=false" in last
    assert "HFT_LIMIT_TIF=ioc" in last
    assert "HFT_REST_POLL_ALWAYS=true" in last
    assert "HFT_USE_DTBP=true" in last
    assert "HFT_BLOCK_ADD_TO_BROKER_LONG=true" in last
    assert "HFT_BP_RESERVE_USD=500" in last
    assert "MAX_GROSS_LEVERAGE=1.0" in last
    assert "FORTRESS_LITE_INTEL=false" in last


def test_rsync_excludes_mac_autopilot_pause():
    text = (ROOT / "cloud/gcp_bootstrap.sh").read_text(encoding="utf-8")
    assert "--exclude='data/autopilot_state.json'" in text
    assert "stop-hft-obi" in text.split("cmd_push_paper()")[1].split("cmd_push_train()")[0]
    assert "ensure-subsecond" in text.split("cmd_push_paper()")[1].split("cmd_push_train()")[0]
    paper = text.split("cmd_push_paper()")[1].split("cmd_push_train()")[0]
    assert "GCP_PAPER_INSTANCE:-fate-algobot-paper" in paper
    assert "GCP_INSTANCE:-fate-algobot-paper" not in paper


def test_paper_startup_reensures_hft_even_if_fortress_up():
    text = (ROOT / "cloud/gcp_startup_paper.sh").read_text(encoding="utf-8")
    assert "fortress_live" not in text.split("skip paper start")[-1].split("./run_all.sh paper")[0]
    assert "ensure-subsecond" in text
    assert "FATE_ORDER_ROLE=gcp-paper" in text
    svc = (ROOT / "cloud/fate-algobot-watchdog.service").read_text(encoding="utf-8")
    assert "Restart=always" in svc
    assert "FATE_ORDER_ROLE=gcp-paper" in svc
    inst = (ROOT / "cloud/install_paper_systemd.sh").read_text(encoding="utf-8")
    assert "fate-algobot-watchdog.service" in inst


def test_aggressive_entry_crosses_ask_not_mid():
    src = (ROOT / "hft/src/obi-tape/order-pricing.ts").read_text(encoding="utf-8")
    fn = src.split("export function entryLimitPx")[1].split("export function exitLimitPx")[0]
    assert "wantAggressiveEntry()" in fn
    assert "bestAsk * (1 + slipBps)" in fn
    assert "bidAnchored" not in fn

