#!/usr/bin/env python3
"""Always-on industry AI daemon — classifies top-50% in auto-resuming chunks."""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

LOG = ROOT / "logs" / "industry_ai_watch.log"
STATE = ROOT / "data" / "industry" / "ai_watch_state.json"
WATCHDOG_LOG = ROOT / "data" / "watchdog_log.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(msg: str, *, ok: bool = True) -> None:
    line = f"[{_now()}] {msg}\n"
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line)
    print(line, end="", flush=True)
    try:
        WATCHDOG_LOG.parent.mkdir(parents=True, exist_ok=True)
        with WATCHDOG_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": _now(), "action": "industry_ai_watch", "detail": msg, "ok": ok}) + "\n")
    except Exception:
        pass


def _load_watch_state() -> dict:
    if not STATE.is_file():
        return {}
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_watch_state(**fields: object) -> None:
    st = _load_watch_state()
    st.update(fields)
    st["updated_at_utc"] = _now()
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, indent=2), encoding="utf-8")


def _days_since(key: str) -> float:
    st = _load_watch_state()
    ts = st.get(key)
    if not ts:
        return 9999.0
    try:
        then = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - then).total_seconds() / 86400.0
    except Exception:
        return 9999.0


def _llm_configured() -> bool:
    return bool((os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip())


def _maybe_refresh_top50() -> None:
    if os.getenv("INDUSTRY_AI_AUTO_REFRESH_TOP50", "true").lower() not in ("1", "true", "yes"):
        return
    weekly = float(os.getenv("INDUSTRY_AI_TOP50_REFRESH_DAYS", "7"))
    if _days_since("last_top50_refresh_utc") < weekly:
        return
    try:
        from universe_lifecycle.rankings import refresh_market_cap_tiers

        out = refresh_market_cap_tiers()
        _save_watch_state(last_top50_refresh_utc=_now())
        _log(f"top50 refreshed count={len(out.get('top50pct') or [])} universe={out.get('universe_size')}")
    except Exception as e:
        _log(f"top50 refresh failed: {e}", ok=False)


def _maybe_refresh_peer_map() -> None:
    daily = float(os.getenv("INDUSTRY_AI_PEER_MAP_DAYS", "1"))
    if _days_since("last_peer_map_utc") < daily:
        return
    try:
        from tools.emit_peer_ticker_map import main as emit_peer

        emit_peer()
        _save_watch_state(last_peer_map_utc=_now())
        _log("peer_ticker_map refreshed")
    except Exception as e:
        _log(f"peer map failed: {e}", ok=False)


def _run_one_cycle() -> dict:
    from tools.industry_ai_train import run_train

    tier = os.getenv("INDUSTRY_AI_TIER", "top50")
    chunk = int(os.getenv("INDUSTRY_AI_TRAIN_CHUNK", "24"))
    max_chunks = int(os.getenv("INDUSTRY_AI_WATCH_CHUNKS_PER_CYCLE", "1"))
    return run_train(
        tier=tier,
        chunk_size=chunk,
        max_chunks=max_chunks,
        force=False,
        refresh_peer=False,
    )


def run_once() -> int:
    if os.getenv("USE_INDUSTRY_AI", "true").lower() not in ("1", "true", "yes"):
        _log("USE_INDUSTRY_AI=false — skip")
        return 0
    if not _llm_configured():
        _log("LLM_API_KEY missing — skip", ok=False)
        return 1

    _maybe_refresh_top50()
    report = _run_one_cycle()
    classified = int(report.get("classified") or 0)
    complete = bool(report.get("complete"))
    progress = report.get("progress", "?")

    if classified > 0:
        _save_watch_state(last_classify_utc=_now(), last_progress=progress)
        try:
            from analytics.industries.ai_registry import emit_ai_override_module

            emit_ai_override_module()
        except Exception:
            pass
        _maybe_refresh_peer_map()

    if complete:
        _save_watch_state(last_cycle_complete_utc=_now(), last_progress="complete")
        _log(f"cycle complete — all due symbols classified ({progress})")
    else:
        _log(f"chunk ok={classified} err={report.get('errors', 0)} progress={progress}")

    return 0


def main() -> int:
    once = "--once" in sys.argv or os.getenv("INDUSTRY_AI_WATCH_ONCE", "").lower() in ("1", "true", "yes")
    poll = int(os.getenv("INDUSTRY_AI_POLL_SEC", "300"))
    idle_poll = int(os.getenv("INDUSTRY_AI_IDLE_POLL_SEC", "1800"))

    _log(f"industry_ai_watch started poll={poll}s idle={idle_poll}s")
    if once:
        return run_once()

    while True:
        try:
            report = {}
            if _llm_configured():
                _maybe_refresh_top50()
                from tools.industry_ai_train import run_train

                tier = os.getenv("INDUSTRY_AI_TIER", "top50")
                chunk = int(os.getenv("INDUSTRY_AI_TRAIN_CHUNK", "24"))
                report = run_train(
                    tier=tier,
                    chunk_size=chunk,
                    max_chunks=int(os.getenv("INDUSTRY_AI_WATCH_CHUNKS_PER_CYCLE", "1")),
                    force=False,
                    refresh_peer=False,
                )
                classified = int(report.get("classified") or 0)
                if classified > 0:
                    _save_watch_state(last_classify_utc=_now(), last_progress=report.get("progress"))
                    from analytics.industries.ai_registry import emit_ai_override_module

                    emit_ai_override_module()
                    _maybe_refresh_peer_map()
                if report.get("complete"):
                    _save_watch_state(last_cycle_complete_utc=_now())
                    _log(f"full pass complete progress={report.get('progress')}")
                    time.sleep(idle_poll)
                    continue
                _log(
                    f"progress={report.get('progress')} ok={classified} err={report.get('errors', 0)}"
                )
            else:
                _log("LLM key missing — waiting", ok=False)
        except Exception as e:
            _log(f"cycle error: {e}", ok=False)

        sleep_s = idle_poll if report.get("complete") else poll
        time.sleep(sleep_s)


if __name__ == "__main__":
    raise SystemExit(main())
