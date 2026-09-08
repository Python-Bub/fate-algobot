"""FATE_AlgoBot dashboard — TradingView candle charts + Undercut & Rally + online updates.

Run with:
    ./venv/bin/python -m streamlit run dashboard/app.py
"""

from __future__ import annotations

import json
import os
from typing import Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from dashboard.chart_data import (
    fetch_ohlcv,
    latest_paper_sim_report,
    to_lightweight_candles,
    to_lightweight_line,
    to_lightweight_volume,
    ur_overlay_markers,
)


st.set_page_config(page_title="FATE_AlgoBot — Live Picks", layout="wide")


def _ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False, min_periods=max(1, span // 2)).mean()


def render_tv_chart(
    ticker: str,
    candles: list[dict[str, Any]],
    volumes: list[dict[str, Any]],
    ema20: list[dict[str, Any]],
    ema50: list[dict[str, Any]],
    pivot_low: float | None,
    markers: list[dict[str, Any]],
    height: int = 520,
) -> None:
    payload = {
        "ticker": ticker,
        "candles": candles,
        "volumes": volumes,
        "ema20": ema20,
        "ema50": ema50,
        "pivot_low": pivot_low,
        "markers": markers,
    }
    html = """
<div id="container_TICKER" style="position: relative; width: 100%; height: HEIGHTpx;"></div>
<script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
<script>
  const data = PAYLOAD;
  const el = document.getElementById('container_' + data.ticker);
  const chart = LightweightCharts.createChart(el, {
      layout: { background: { color: '#0E1117' }, textColor: '#D9D9D9' },
      grid: { vertLines: { color: '#222' }, horzLines: { color: '#222' } },
      rightPriceScale: { borderColor: '#444' },
      timeScale: { borderColor: '#444', timeVisible: true, secondsVisible: false },
      crosshair: { mode: 1 },
      width: el.clientWidth,
      height: HEIGHT,
  });
  const candleSeries = chart.addCandlestickSeries({
      upColor: '#26a69a', downColor: '#ef5350',
      borderUpColor: '#26a69a', borderDownColor: '#ef5350',
      wickUpColor: '#26a69a', wickDownColor: '#ef5350',
  });
  candleSeries.setData(data.candles);
  if (data.markers && data.markers.length) candleSeries.setMarkers(data.markers);

  if (data.ema20 && data.ema20.length) {
      const e20 = chart.addLineSeries({ color: '#2962FF', lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
      e20.setData(data.ema20);
  }
  if (data.ema50 && data.ema50.length) {
      const e50 = chart.addLineSeries({ color: '#FF6D00', lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
      e50.setData(data.ema50);
  }
  if (data.pivot_low) {
      candleSeries.createPriceLine({
          price: data.pivot_low, color: '#FFD600', lineWidth: 1,
          lineStyle: 2, axisLabelVisible: true, title: 'pivot low'
      });
  }
  if (data.volumes && data.volumes.length) {
      const vol = chart.addHistogramSeries({
          priceFormat: { type: 'volume' },
          priceScaleId: '',
          scaleMargins: { top: 0.85, bottom: 0 },
      });
      vol.setData(data.volumes);
  }

  const resize = () => chart.applyOptions({ width: el.clientWidth });
  window.addEventListener('resize', resize);
</script>
"""
    html = html.replace("TICKER", ticker.replace("-", "_").replace(".", "_"))
    html = html.replace("HEIGHT", str(int(height)))
    html = html.replace("PAYLOAD", json.dumps(payload))
    components.html(html, height=height + 20)


def main() -> None:
    st.title("FATE_AlgoBot — TradingView candles + Undercut & Rally")
    st.caption("Live view of today's paper-sim picks with U&R overlays, EMAs, and pivot lines.")

    col1, col2, col3 = st.columns([2, 2, 2])
    report = latest_paper_sim_report()
    with col1:
        st.metric("Universe scored", report.get("symbols_scored", "?") if report else "—")
    with col2:
        st.metric("Hypothetical Buys", report.get("hypothetical_buys", "?") if report else "—")
    with col3:
        st.metric("PnL (USD, ex fees)", f"{report.get('sum_hypothetical_pnl_usd', 0.0):,.2f}" if report else "—")

    if report is None:
        st.warning("No paper-sim report found in `reports/`. Run `./venv/bin/python -m paper_sim_today` first.")
        return

    with st.expander("Asymmetric filter metrics + FRED macro (latest paper-sim)", expanded=False):
        st.json(
            {
                "asym_filter_metrics": report.get("asym_filter_metrics"),
                "fred_macro": report.get("fred_macro"),
            }
        )

    neural_dash = report.get("neural_dashboard")
    if neural_dash:
        with st.expander("Neural ensemble dashboard", expanded=True):
            c1, c2, c3 = st.columns(3)
            c1.metric("Replay samples", neural_dash.get("replay_n_samples", 0))
            c2.metric("Symbols w/ neural", neural_dash.get("symbols_with_neural", 0))
            c3.metric(
                "Tickers in win-rate eval",
                neural_dash.get("tickers_evaluated_for_win_rate", 0),
            )
            lb = neural_dash.get("model_leaderboard") or []
            if lb:
                st.markdown("**Model holdout win-rates** (direction vs realized move)")
                st.dataframe(
                    pd.DataFrame(lb),
                    use_container_width=True,
                    hide_index=True,
                )
            hi = neural_dash.get("highest_disagreement") or []
            if hi:
                st.markdown("**Highest disagreement** (std across model p_up)")
                st.dataframe(
                    pd.DataFrame(hi),
                    use_container_width=True,
                    hide_index=True,
                )
            picks = neural_dash.get("trade_picks_neural") or []
            if picks:
                st.markdown("**BUY/SHORT picks with neural blend**")
                st.dataframe(
                    pd.DataFrame(picks),
                    use_container_width=True,
                    hide_index=True,
                )

    ai_meta = report.get("ai_pick_review")
    if ai_meta and isinstance(ai_meta, dict) and ai_meta.get("enabled"):
        with st.expander("AI final pick review (web snippets + LLM)", expanded=False):
            st.json(ai_meta)

    rows = report.get("rows", [])
    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    if df.empty:
        st.info("Report exists but no scored rows.")
        return

    show_actions = st.multiselect(
        "Show actions",
        options=sorted(df["action"].dropna().unique().tolist()) if "action" in df.columns else [],
        default=["BUY", "SHORT"] if "action" in df.columns else [],
    )
    show_ur_only = st.checkbox("Only Undercut & Rally fires (ur_detected = true)", value=False)
    max_charts = st.slider("Max charts", min_value=1, max_value=20, value=6, step=1)

    if show_actions and "action" in df.columns:
        df = df[df["action"].isin(show_actions)]
    if show_ur_only and "ur_detected" in df.columns:
        df = df[df["ur_detected"] == True]  # noqa: E712

    sort_col = "score" if "score" in df.columns else df.columns[0]
    df = df.sort_values(sort_col, ascending=False).head(max_charts)

    if df.empty:
        st.info("No rows match filters.")
        return

    online_updates = {u["ticker"]: u for u in report.get("online_updates", [])}

    for _, r in df.iterrows():
        ticker = str(r["ticker"])
        st.subheader(f"{ticker}  —  {r.get('action', '?')}  (score={r.get('score', 0.0):.3f})")

        meta_cols = st.columns(6)
        meta_cols[0].metric("p_up", f"{r.get('p_up', 0.0):.3f}")
        meta_cols[1].metric("exec_conf", f"{r.get('execution_confidence', 0.0):.3f}")
        meta_cols[2].metric("asym", str(r.get("asym_action", "?")))
        meta_cols[3].metric("U&R", f"{r.get('ur_score', 0.0):.2f}")
        meta_cols[4].metric("fwd_1d_%", f"{float(r.get('fwd_1d_return', 0.0)) * 100:+.2f}")
        ou = online_updates.get(ticker)
        if ou:
            meta_cols[5].metric(
                "ΔL2 / pre→post p",
                f"{ou.get('delta_l2', 0):.4f}",
                delta=f"{ou.get('pre_p', 0):.3f}→{ou.get('post_p', 0):.3f}",
            )
        else:
            meta_cols[5].metric("online update", "—")

        ohlcv = fetch_ohlcv(ticker, period=os.getenv("DASH_CHART_PERIOD", "6mo"))
        if ohlcv.empty:
            st.warning(f"{ticker}: no OHLCV from yfinance.")
            continue

        candles = to_lightweight_candles(ohlcv)
        volumes = to_lightweight_volume(ohlcv)
        ema20 = to_lightweight_line(_ema(ohlcv["Close"], 20), "#2962FF")
        ema50 = to_lightweight_line(_ema(ohlcv["Close"], 50), "#FF6D00")
        pivot_low = r.get("ur_pivot_low") if r.get("ur_detected") else None
        markers = ur_overlay_markers(
            ohlcv,
            {"ur_detected": bool(r.get("ur_detected", False)), "ur_score": float(r.get("ur_score", 0.0))},
        )

        render_tv_chart(
            ticker=ticker,
            candles=candles,
            volumes=volumes,
            ema20=ema20,
            ema50=ema50,
            pivot_low=float(pivot_low) if pivot_low else None,
            markers=markers,
        )

        with st.expander("Details (rationale, pivot, ratios)"):
            st.json(
                {
                    "asym_rationale": r.get("asym_rationale"),
                    "ur_rationale": r.get("ur_rationale"),
                    "ur_pivot_low": r.get("ur_pivot_low"),
                    "ur_pivot_age_bars": r.get("ur_pivot_age_bars"),
                    "ur_undercut_depth_pct": r.get("ur_undercut_depth_pct"),
                    "ur_reclaim_pct": r.get("ur_reclaim_pct"),
                    "ur_volume_expansion": r.get("ur_volume_expansion"),
                    "ur_trend_ok": r.get("ur_trend_ok"),
                    "online_update": ou,
                    "neural_breakdown": r.get("neural_breakdown"),
                }
            )


if __name__ == "__main__":
    main()
