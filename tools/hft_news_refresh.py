#!/usr/bin/env python3
"""Refresh trade-news intel for HFT tickers only — clean schema, no probability confusion."""

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

OUT = ROOT / "data" / "intel" / "hft_trade_news.json"


def _tickers() -> list[str]:
    from tools.tradeable_universe import hft_trade_tickers

    return hft_trade_tickers()


def _neutral(sym: str) -> dict:
    return {
        "symbol": sym,
        "allow_long": True,
        "tilt": 0.0,
        "good": 0.0,
        "bad": 0.0,
        "headline": "",
    }


def _analyze(sym: str) -> dict:
    try:
        from intel.metric_semantics import reconcile_sentiment_with_headline
        from intel.news_ai_agent import analyze_symbol_news

        intel = analyze_symbol_news(sym, force_refresh=True)
    except Exception as e:
        row = _neutral(sym)
        row["error"] = str(e)[:120]
        return row

    good = float(intel.get("good_news_score") or 0.0)
    bad = float(intel.get("bad_news_score") or 0.0)
    block = bool(intel.get("block_long"))
    verdict = str(intel.get("verdict") or "neutral").lower()

    headline = str(intel.get("llm_thesis") or "").strip()
    bear = list(intel.get("top_bearish") or intel.get("key_bad") or [])
    bull = list(intel.get("top_bullish") or intel.get("key_good") or [])
    if not headline:
        headline = str(bear[0] if bad >= good and bear else (bull[0] if bull else ""))[:240]

    # Intensity for sizing tilt only — NOT P(up)
    intensity = float(intel.get("sentiment") or 0.0)
    if verdict == "bearish" or bad > good + 0.2:
        intensity = min(intensity, -0.05 - 0.35 * bad)
    elif verdict == "bullish" and good > bad + 0.15:
        intensity = max(intensity, 0.05 + 0.25 * good)
    intensity, _ = reconcile_sentiment_with_headline(headline, intensity)
    intensity = max(-1.0, min(1.0, intensity))

    try:
        from intel.morning_club_intel import morning_club_block_long, morning_club_boost_for

        cb = float(morning_club_boost_for(sym))
        if morning_club_block_long(sym):
            block = True
        elif abs(cb) >= 0.1:
            club_scale = float(os.getenv("HFT_MORNING_CLUB_TILT", "0.08"))
            intensity = max(-1.0, min(1.0, intensity + cb * club_scale))
    except Exception:
        pass

    block_bad = float(os.getenv("HFT_NEWS_BLOCK_BAD", "0.62"))
    # Never block longs when bullish evidence dominates (fixes false "bearish" gates).
    if good > bad + 0.05 or verdict == "bullish":
        block = False
    allow = not block and not (verdict == "bearish" and bad >= block_bad and bad > good)

    scale = float(os.getenv("HFT_NEWS_TILT_SCALE", "0.12"))
    cap = float(os.getenv("HFT_NEWS_TILT_CAP", "0.10"))
    tilt = max(-cap, min(cap, intensity * scale)) if allow else 0.0

    return {
        "symbol": sym,
        "allow_long": allow,
        "tilt": round(tilt, 5),
        "intensity": round(intensity, 4),
        "good": round(good, 4),
        "bad": round(bad, 4),
        "verdict": verdict,
        "headline": headline[:240],
    }


def refresh(*, force: bool = False) -> dict:
    interval = float(os.getenv("HFT_NEWS_REFRESH_MIN", "5")) * 60
    if OUT.is_file() and not force:
        try:
            prev = json.loads(OUT.read_text(encoding="utf-8"))
            age = time.time() - float(prev.get("updated_ms", 0)) / 1000.0
            if age < interval:
                return prev
        except Exception:
            pass

    tickers = _tickers()
    rows: dict[str, dict] = {}
    for i, sym in enumerate(tickers):
        if i:
            time.sleep(float(os.getenv("HFT_NEWS_TICKER_PAUSE_SEC", "0.3")))
        rows[sym] = _analyze(sym)

    payload = {
        "updated_ms": int(time.time() * 1000),
        "updated_utc": datetime.now(timezone.utc).isoformat(),
        "note": "tilt is sizing nudge only; allow_long is gate; neither is trade probability",
        "tickers": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    legacy = ROOT / "data" / "intel" / "hft_ticker_boost.json"
    if legacy.is_file():
        legacy.unlink()
    return payload


def main() -> int:
    force = "--force" in sys.argv
    data = refresh(force=force)
    rows = data.get("tickers") or {}
    blocked = [k for k, v in rows.items() if not v.get("allow_long")]
    print(f"[hft-news] clean slate → {OUT} ({len(rows)} tickers)")
    if blocked:
        print(f"  no-new-long: {', '.join(blocked)}")
    for sym, row in sorted(rows.items(), key=lambda x: -abs(x[1].get("tilt", 0)))[:6]:
        t = row.get("tilt", 0)
        if abs(t) > 0.001 or not row.get("allow_long"):
            print(
                f"  {sym}: allow={row.get('allow_long')} tilt={t:+.4f}  "
                f"{str(row.get('headline', ''))[:60]}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
