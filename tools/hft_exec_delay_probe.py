#!/usr/bin/env python3
"""Measure Alpaca paper API RTT (WiFi/VPN/earth delay) for HFT exec calibration.

Writes data/ops/hft_exec_delay.json consumed by hft/src/obi-tape/exec-delay.ts.

Usage:
  ./venv/bin/python tools/hft_exec_delay_probe.py
  ./run_all.sh exec-delay-probe
"""
from __future__ import annotations

import json
import os
import socket
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")
_scale = ROOT / "data" / "deploy_scale.env"
if _scale.is_file():
    load_dotenv(_scale, override=True)

OUT = Path(os.getenv("HFT_EXEC_DELAY_PATH", str(ROOT / "data" / "ops" / "hft_exec_delay.json")))
HOST = "paper-api.alpaca.markets"
URL = os.getenv("HFT_EXEC_DELAY_URL", f"https://{HOST}/v2/clock")
SAMPLES = int(os.getenv("HFT_EXEC_DELAY_SAMPLES", "12"))


def _headers() -> dict[str, str]:
    key = os.getenv("APCA_API_KEY_ID") or os.getenv("ALPACA_API_KEY") or ""
    sec = os.getenv("APCA_API_SECRET_KEY") or os.getenv("ALPACA_SECRET_KEY") or ""
    return {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec}


def _tcp_connect_ms(host: str, port: int = 443, timeout: float = 5.0) -> float | None:
    t0 = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return (time.perf_counter() - t0) * 1000.0
    except OSError:
        return None


def _http_rtt_ms() -> float | None:
    req = urllib.request.Request(URL, headers=_headers(), method="GET")
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            resp.read(256)
        return (time.perf_counter() - t0) * 1000.0
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        print(f"[exec-delay] HTTP probe failed: {e}", file=sys.stderr)
        return None


def main() -> int:
    tcp_samples: list[float] = []
    http_samples: list[float] = []
    for i in range(max(3, SAMPLES)):
        c = _tcp_connect_ms(HOST)
        if c is not None:
            tcp_samples.append(c)
        h = _http_rtt_ms()
        if h is not None:
            http_samples.append(h)
        time.sleep(0.15)

    if not http_samples and not tcp_samples:
        print("[exec-delay] no samples — check network / Alpaca keys", file=sys.stderr)
        return 1

    def stats(xs: list[float]) -> dict:
        if not xs:
            return {}
        xs_s = sorted(xs)
        p50 = xs_s[len(xs_s) // 2]
        p95 = xs_s[min(len(xs_s) - 1, int(len(xs_s) * 0.95))]
        return {
            "mean": round(statistics.fmean(xs), 2),
            "p50": round(p50, 2),
            "p95": round(p95, 2),
            "min": round(min(xs), 2),
            "max": round(max(xs), 2),
            "n": len(xs),
        }

    http = stats(http_samples)
    tcp = stats(tcp_samples)

    # Prefer TCP connect when HTTP is pathological (VPN SSL stalls).
    tcp_p50 = float(tcp.get("p50") or 0)
    http_p50 = float(http.get("p50") or 0)
    if http_p50 > 0 and tcp_p50 > 0 and http_p50 > tcp_p50 * 2:
        rtt_p50 = tcp_p50
        rtt_p95 = float(tcp.get("p95") or http.get("p95") or 0)
        path_note = "tcp_connect preferred (HTTP RTT inflated by SSL/VPN stalls)"
    else:
        rtt_p50 = http_p50 or tcp_p50
        rtt_p95 = float(http.get("p95") or tcp.get("p95") or 0)
        path_note = "wifi/vpn → ISP → internet → Alpaca us-east paper API"
    # Budget: p50 + 25% headroom, floor 15ms (colo), ceiling 250ms (bad VPN).
    recommended = int(min(250, max(15, rtt_p50 * 1.25 + 5)))

    doc = {
        "updated_ms": int(time.time() * 1000),
        "updated_utc": datetime.now(timezone.utc).isoformat(),
        "host": HOST,
        "url": URL,
        "path": path_note,
        "tcp_connect_ms": tcp,
        "http_rtt_ms": http,
        "rtt_ms_p50": round(rtt_p50, 2),
        "rtt_ms_p95": round(rtt_p95, 2),
        "rtt_ms_mean": float(http.get("mean") or tcp.get("mean") or 0),
        "recommended_budget_ms": recommended,
        "samples": len(http_samples) or len(tcp_samples),
        "note": "HFT uses recommended_budget_ms (capped) for gates; raw HTTP may be VPN-inflated.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(doc, indent=2))
    print(f"[exec-delay] wrote {OUT}")
    print(f"[exec-delay] p50={rtt_p50:.1f}ms p95={rtt_p95:.1f}ms → budget≈{recommended}ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
