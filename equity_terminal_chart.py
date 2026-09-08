"""
Detailed terminal equity / portfolio-value line chart.

CLI (also: ``./run_all.sh equity``):
  python equity_terminal_chart.py
  python equity_terminal_chart.py 1d|1h|1w|1m|3m|6m|1y|2y|3y|5y|10y|all
  python equity_terminal_chart.py --range 1w --source alpaca|history|auto
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

BLOCKS = "▁▂▃▄▅▆▇█"
ROOT = Path(__file__).resolve().parent
HISTORY_PATH = Path(
    os.getenv("OBJECTIVE_EQUITY_HISTORY", str(ROOT / "data" / "self_improve" / "equity_history.jsonl"))
)

# CLI range → (label, lookback seconds or None=all, Alpaca period, Alpaca timeframe)
RANGE_SPECS: dict[str, tuple[str, float | None, str, str]] = {
    "1h": ("1 hour", 3600.0, "1D", "1Min"),
    "1d": ("1 day", 86400.0, "1D", "1Min"),
    "1w": ("1 week", 7 * 86400.0, "1W", "15Min"),
    "1m": ("1 month", 30 * 86400.0, "1M", "1D"),
    "3m": ("3 months", 90 * 86400.0, "3M", "1D"),
    "6m": ("6 months", 180 * 86400.0, "6M", "1D"),
    "1y": ("1 year", 365 * 86400.0, "1A", "1D"),
    "2y": ("2 years", 2 * 365 * 86400.0, "2A", "1D"),
    "3y": ("3 years", 3 * 365 * 86400.0, "3A", "1D"),
    "5y": ("5 years", 5 * 365 * 86400.0, "5A", "1D"),
    "10y": ("10 years", 10 * 365 * 86400.0, "10A", "1D"),
    "all": ("all time", None, "all", "1D"),
}
RANGE_ALIASES = {
    "hour": "1h",
    "1hour": "1h",
    "day": "1d",
    "1day": "1d",
    "week": "1w",
    "1week": "1w",
    "7d": "1w",
    "month": "1m",
    "1month": "1m",
    "30d": "1m",
    "90d": "3m",
    "180d": "6m",
    "year": "1y",
    "1year": "1y",
    "12m": "1y",
    "24m": "2y",
    "36m": "3y",
    "60m": "5y",
    "120m": "10y",
    "*": "all",
    "max": "all",
    "everything": "all",
}


def normalize_range(raw: str | None) -> str:
    key = (raw or "1d").strip().lower().replace("_", "").replace("-", "")
    key = RANGE_ALIASES.get(key, key)
    if key not in RANGE_SPECS:
        allowed = ", ".join(RANGE_SPECS)
        raise SystemExit(f"[equity] unknown range {raw!r}; use one of: {allowed}")
    return key


def sparkline(values: list[float], width: int = 72) -> str:
    if not values:
        return ""
    v = values[-width:]
    lo, hi = min(v), max(v)
    if hi <= lo:
        return BLOCKS[4] * len(v)
    out = []
    for x in v:
        t = (x - lo) / (hi - lo)
        idx = min(len(BLOCKS) - 1, int(t * (len(BLOCKS) - 1)))
        out.append(BLOCKS[idx])
    return "".join(out)


def print_equity_panel(name: str, equity_series: list[float], pnl_today: float | None = None) -> None:
    if not equity_series:
        print(f"[{name}] (no data)")
        return
    cur = equity_series[-1]
    start = equity_series[0]
    chg = (cur - start) / max(abs(start), 1e-9) * 100
    line = sparkline(equity_series)
    extra = f"  today PnL: {pnl_today:+.2f}" if pnl_today is not None else ""
    print(f"\n═══ {name}  equity={cur:,.2f}  Δ={chg:+.2f}% {extra}")
    print(line)
    print(f"min={min(equity_series):,.2f}  max={max(equity_series):,.2f}  pts={len(equity_series)}\n")


def _ascii_line_chart(values: list[float], *, width: int = 88, height: int = 18) -> str:
    """Pure-ASCII fallback when plotext is unavailable."""
    if not values:
        return "(no data)"
    w = max(16, min(width, len(values), shutil.get_terminal_size((88, 24)).columns - 12))
    h = max(8, height)
    # Downsample to chart width
    if len(values) <= w:
        series = list(values)
    else:
        series = []
        for i in range(w):
            a = int(i * (len(values) - 1) / (w - 1))
            series.append(values[a])
    lo, hi = min(series), max(series)
    span = hi - lo if hi > lo else 1.0
    rows = [[" "] * len(series) for _ in range(h)]
    prev_y: int | None = None
    for x, v in enumerate(series):
        y = int(round((h - 1) * (v - lo) / span))
        y = max(0, min(h - 1, y))
        if prev_y is None or prev_y == y:
            rows[h - 1 - y][x] = "•"
        else:
            step = 1 if y > prev_y else -1
            for yy in range(prev_y, y + step, step):
                rows[h - 1 - yy][x] = "│" if yy != y else "•"
        prev_y = y
    lines = []
    for i, row in enumerate(rows):
        if i == 0:
            label = f"{hi:,.0f}"
        elif i == h - 1:
            label = f"{lo:,.0f}"
        else:
            label = ""
        lines.append(f"{label:>10} │{''.join(row)}")
    lines.append(f"{'':>10} └{'─' * len(series)}")
    return "\n".join(lines)


def plot_line(
    timestamps: list[float],
    values: list[float],
    *,
    title: str,
    width: int | None = None,
    height: int | None = None,
) -> None:
    """Render a continuous LINE chart (never bars/histogram)."""
    cols, rows = shutil.get_terminal_size((100, 28))
    w = width or max(60, min(cols - 2, 120))
    h = height or max(16, min(rows - 8, 28))
    try:
        import plotext as plt

        plt.clear_figure()
        plt.plotsize(w, h)
        plt.title(title)
        plt.ylabel("equity ($)")
        xs = list(range(len(values)))
        # Explicit line markers only — braille/hd can look bar-like in some terminals.
        # "fhd" / "dot" draw a connected line path.
        try:
            plt.plot(xs, values, marker="fhd")
        except Exception:
            try:
                plt.plot(xs, values, marker="hd")
            except Exception:
                plt.plot(xs, values, marker="dot")
        n = len(values)
        if timestamps and len(timestamps) == len(values) and n > 1:
            ticks = sorted({0, n // 4, n // 2, (3 * n) // 4, n - 1})
            labels = []
            for i in ticks:
                dt = datetime.fromtimestamp(timestamps[i], tz=timezone.utc)
                if timestamps[-1] - timestamps[0] <= 2 * 86400:
                    labels.append(dt.strftime("%H:%M"))
                elif timestamps[-1] - timestamps[0] <= 40 * 86400:
                    labels.append(dt.strftime("%m-%d"))
                else:
                    labels.append(dt.strftime("%Y-%m"))
            plt.xticks(ticks, labels)
        plt.theme("clear")
        plt.grid(True, True)
        plt.show()
        print("[equity] renderer=plotext LINE (not bars)")
    except Exception as e:
        print(f"[equity] plotext line unavailable ({e}); ASCII line fallback")
        print(_ascii_line_chart(values, width=w, height=max(12, h - 4)))
        print("[equity] renderer=ascii LINE (not bars)")


def load_history_points(
    path: Path | None = None,
    *,
    max_points: int = 0,
) -> list[tuple[float, float]]:
    """Load (unix_ts, equity) from self-improve JSONL (skip zero glitches)."""
    p = path or HISTORY_PATH
    if not p.is_file():
        return []
    pts: list[tuple[float, float]] = []
    try:
        with p.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                eq = row.get("equity")
                if eq is None:
                    continue
                try:
                    v = float(eq)
                except (TypeError, ValueError):
                    continue
                if v <= 1.0:
                    continue
                ts_raw = row.get("ts_utc") or row.get("ts") or row.get("timestamp")
                try:
                    if isinstance(ts_raw, (int, float)):
                        ts = float(ts_raw)
                        if ts > 1e12:
                            ts /= 1000.0
                    elif isinstance(ts_raw, str) and ts_raw:
                        ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00")).timestamp()
                    else:
                        continue
                except Exception:
                    continue
                pts.append((ts, v))
    except OSError:
        return []
    pts.sort(key=lambda x: x[0])
    if max_points > 0 and len(pts) > max_points:
        pts = pts[-max_points:]
    return pts


def load_history_series(path: Path | None = None, *, max_points: int = 500) -> list[float]:
    """Load equity curve from self-improve / objective JSONL (skip zero glitches)."""
    return [v for _, v in load_history_points(path, max_points=max_points)]


def load_alpaca_snapshot() -> tuple[float | None, float | None, float | None]:
    """Return (equity, last_equity, day_pnl) from Alpaca paper/live account."""
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env", override=False)
    except Exception:
        pass
    try:
        from alpaca_broker import get_account

        acct = get_account() or {}
        if not acct:
            return None, None, None
        eq = float(acct.get("equity") or acct.get("portfolio_value") or 0) or None
        last = float(acct.get("last_equity") or 0) or None
        pnl = None
        if eq is not None and last:
            pnl = eq - last
        return eq, last, pnl
    except Exception:
        return None, None, None


def load_alpaca_history(period: str, timeframe: str) -> list[tuple[float, float]]:
    """Fetch Alpaca portfolio history as (unix_ts, equity) pairs."""
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env", override=False)
    except Exception:
        pass
    try:
        from alpaca_broker import get_portfolio_history
    except Exception:
        return []
    raw = get_portfolio_history(period=period, timeframe=timeframe, extended_hours=True)
    if not raw:
        return []
    ts_list = raw.get("timestamp") or []
    eq_list = raw.get("equity") or []
    pts: list[tuple[float, float]] = []
    for ts, eq in zip(ts_list, eq_list):
        if ts is None or eq is None:
            continue
        try:
            v = float(eq)
            t = float(ts)
        except (TypeError, ValueError):
            continue
        if v <= 1.0:
            continue
        pts.append((t, v))
    return pts


def filter_range(
    points: list[tuple[float, float]],
    lookback_sec: float | None,
    *,
    now: float | None = None,
) -> tuple[list[tuple[float, float]], bool]:
    """
    Keep points inside lookback window.
    Returns (filtered, shorter_than_requested).
    """
    if not points:
        return [], False
    now = now if now is not None else time.time()
    if lookback_sec is None:
        return points, False
    start = now - lookback_sec
    filtered = [(t, v) for t, v in points if t >= start]
    if not filtered:
        # nothing in window — keep all available and mark shorter
        return points, True
    shorter = filtered[0][0] > start + max(60.0, lookback_sec * 0.05)
    return filtered, shorter


def downsample(points: list[tuple[float, float]], max_points: int) -> list[tuple[float, float]]:
    if max_points <= 0 or len(points) <= max_points:
        return points
    out: list[tuple[float, float]] = []
    n = len(points)
    for i in range(max_points):
        idx = int(i * (n - 1) / (max_points - 1))
        out.append(points[idx])
    return out


def equity_snapshot() -> dict:
    """Compact dict for talk / observe paths (read-only)."""
    hist = load_history_series(max_points=120)
    eq, last, pnl = load_alpaca_snapshot()
    out: dict = {
        "equity": eq,
        "last_equity": last,
        "day_pnl": pnl,
        "history_pts": len(hist),
        "history_last": hist[-1] if hist else None,
        "history_min": min(hist) if hist else None,
        "history_max": max(hist) if hist else None,
        "source": "alpaca" if eq is not None else ("history" if hist else "none"),
    }
    if hist:
        out["spark"] = sparkline(hist, width=min(48, len(hist)))
    return out


def _fmt_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def render_range_chart(
    *,
    range_key: str = "1d",
    source: str = "auto",
    width: int | None = None,
    height: int | None = None,
    max_points: int = 1200,
    spark_only: bool = False,
) -> int:
    rk = normalize_range(range_key)
    label, lookback, alp_period, alp_tf = RANGE_SPECS[rk]
    src = (source or "auto").strip().lower()
    eq, last, pnl = load_alpaca_snapshot()

    alpaca_pts: list[tuple[float, float]] = []
    hist_pts: list[tuple[float, float]] = []

    if src in ("auto", "alpaca"):
        alpaca_pts = load_alpaca_history(alp_period, alp_tf)
    if src in ("auto", "history"):
        hist_pts = load_history_points(max_points=0)

    chosen: list[tuple[float, float]] = []
    origin = "none"
    if src == "alpaca":
        chosen, origin = alpaca_pts, "alpaca"
    elif src == "history":
        chosen, origin = hist_pts, "local"
    else:
        # Prefer Alpaca official portfolio history; fall back to local JSONL.
        if alpaca_pts:
            chosen, origin = alpaca_pts, "alpaca"
        elif hist_pts:
            chosen, origin = hist_pts, "local"

    if not chosen and eq is not None:
        now = time.time()
        chosen = [(now - 60, float(last or eq)), (now, float(eq))]
        origin = "alpaca-live"

    chosen, shorter = filter_range(chosen, lookback)
    if not chosen:
        print(f"[equity] no data for range={rk} source={src}")
        if src != "history":
            print("[equity] tip: check Alpaca keys or local data/self_improve/equity_history.jsonl")
        return 1

    # Tip live equity onto the series when close enough in time
    if eq is not None and origin.startswith("alpaca"):
        if abs(chosen[-1][1] - eq) > 0.5:
            chosen = chosen + [(time.time(), float(eq))]

    plotted = downsample(chosen, max_points)
    ts = [t for t, _ in plotted]
    vals = [v for _, v in plotted]
    start_v, end_v = vals[0], vals[-1]
    chg = (end_v - start_v) / max(abs(start_v), 1e-9) * 100.0
    span_sec = max(0.0, ts[-1] - ts[0])
    span_label = (
        f"{span_sec / 3600:.1f}h"
        if span_sec < 2 * 86400
        else f"{span_sec / 86400:.1f}d"
        if span_sec < 400 * 86400
        else f"{span_sec / (365.25 * 86400):.2f}y"
    )

    # 1h/1d Alpaca bars are session-scoped; don't warn on calendar-day gaps.
    # For longer ranges, warn when available span is clearly under the ask.
    if rk in ("1h", "1d"):
        min_ok = 900.0 if rk == "1h" else 3600.0
        shorter = span_sec < min_ok
    elif lookback is not None:
        shorter = shorter or (span_sec < lookback * 0.45)

    print()
    print(f"═══ Portfolio value  range={rk} ({label})  source={origin}")
    print(f"    {_fmt_ts(ts[0])}  →  {_fmt_ts(ts[-1])}  span≈{span_label}  pts={len(plotted)}")
    print(f"    start=${start_v:,.2f}  end=${end_v:,.2f}  Δ={chg:+.2f}%  min=${min(vals):,.2f}  max=${max(vals):,.2f}")
    if pnl is not None:
        print(f"    Alpaca day PnL (last_equity→equity): {pnl:+.2f}")
    if shorter and lookback is not None:
        if lookback >= 86400:
            req = f"~{lookback / 86400.0:.0f}d"
        else:
            req = f"~{lookback / 3600.0:.0f}h"
        print(
            f"    NOTE: available history (~{span_label}) is shorter than requested "
            f"{label} ({req}). Plotting all available."
        )
        if origin == "alpaca" and lookback >= 30 * 86400:
            print(
                "    Alpaca portfolio history only covers account lifetime "
                "(paper often months, not multi-year)."
            )
    print()

    if spark_only:
        print_equity_panel(f"{label} ({origin})", vals, pnl_today=pnl)
    else:
        plot_line(
            ts,
            vals,
            title=f"Portfolio equity LINE — {label} [{origin}]",
            width=width,
            height=height,
        )
        # Tiny secondary spark is optional context — never the primary chart.
        print(f"    (spark preview) {sparkline(vals, width=min(48, max(16, len(vals))))}")
        print()
    return 0


def render_cli(*, source: str = "auto", width: int = 72, max_points: int = 500) -> int:
    """Legacy sparkline path (no range). Prefer render_range_chart."""
    src = (source or "auto").strip().lower()
    eq, last, pnl = load_alpaca_snapshot()
    hist = load_history_series(max_points=max_points)

    if src == "alpaca":
        if eq is None:
            print("[equity] Alpaca account unavailable")
            return 1
        series = hist[:] if hist else []
        if not series or abs(series[-1] - eq) > 1.0:
            series = series + [eq] if series else [float(last or eq), eq]
        print_equity_panel("Alpaca paper/live", series[-width:], pnl_today=pnl)
        return 0

    if src == "history":
        if not hist:
            print(f"[equity] no history at {HISTORY_PATH}")
            return 1
        print_equity_panel(f"History ({HISTORY_PATH.name})", hist[-width:], pnl_today=pnl)
        return 0

    if hist:
        label = "Paper equity history"
        if eq is not None:
            label = f"Paper equity history + live ${eq:,.0f}"
            if abs(hist[-1] - eq) > 1.0:
                hist = hist + [eq]
        print_equity_panel(label, hist[-width:], pnl_today=pnl)
        return 0
    if eq is not None:
        series = [float(last or eq), eq]
        print_equity_panel("Alpaca (live only — no history file)", series, pnl_today=pnl)
        return 0
    print("[equity] no Alpaca account and no equity_history.jsonl")
    return 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Detailed terminal portfolio equity chart (Alpaca history + local fallback)"
    )
    ap.add_argument(
        "range",
        nargs="?",
        default=None,
        help="1h|1d|1w|1m|3m|6m|1y|2y|3y|5y|10y|all (default: 1d detailed)",
    )
    ap.add_argument(
        "--range",
        dest="range_opt",
        default=None,
        help="Same as positional range",
    )
    ap.add_argument(
        "--source",
        choices=("auto", "alpaca", "history"),
        default=os.getenv("EQUITY_CHART_SOURCE", "auto"),
    )
    ap.add_argument("--width", type=int, default=None)
    ap.add_argument("--height", type=int, default=None)
    ap.add_argument(
        "--max-points",
        type=int,
        default=int(os.getenv("EQUITY_CHART_MAX_POINTS", "1200")),
    )
    ap.add_argument(
        "--spark-only",
        action="store_true",
        help="Legacy block sparkline only (no plotext line chart)",
    )
    ap.add_argument(
        "--legacy",
        action="store_true",
        help="Old sparkline CLI without timeframe filtering",
    )
    args = ap.parse_args(argv)
    if args.legacy:
        w = args.width if args.width is not None else int(os.getenv("EQUITY_CHART_WIDTH", "72"))
        return render_cli(source=args.source, width=max(8, w), max_points=max(10, args.max_points))

    rk = args.range_opt or args.range or os.getenv("EQUITY_CHART_RANGE", "1d")
    return render_range_chart(
        range_key=rk,
        source=args.source,
        width=args.width,
        height=args.height,
        max_points=max(50, args.max_points),
        spark_only=args.spark_only,
    )


if __name__ == "__main__":
    raise SystemExit(main())
