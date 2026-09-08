"""Historical validation of the passive-entry / bracket-exit scalper.

Replays the multi-second scalper execution model over real Yahoo intraday bars:
  - Signal: dip below VWAP by >= dip_pct (proxy for OBI long / dip-scalp).
  - Entry:  passive limit at the BID (filled only if the next bar trades down
            into it within the entry-timeout window).
  - Exit:   profit target at entry + spread + profit (sell HIGH at ask), OR
            hard stop-loss at stop_pct below entry, OR max-hold market-out.

This proves the edge math (win rate vs break-even) BEFORE risking capital.
Rule-based scalper has no ML model to train — this is the equivalent backtest.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
except Exception:
    pass

import numpy as np
import pandas as pd


@dataclass
class TradeStats:
    trades: int = 0
    wins: int = 0
    losses: int = 0
    timeouts: int = 0
    gross_win: float = 0.0
    gross_loss: float = 0.0
    fills_attempted: int = 0
    pnls: list[float] = field(default_factory=list)

    @property
    def win_rate(self) -> float:
        return self.wins / self.trades if self.trades else 0.0

    @property
    def avg_win(self) -> float:
        return self.gross_win / self.wins if self.wins else 0.0

    @property
    def avg_loss(self) -> float:
        return self.gross_loss / self.losses if self.losses else 0.0

    @property
    def net(self) -> float:
        return self.gross_win - self.gross_loss

    @property
    def breakeven_win_rate(self) -> float:
        aw, al = self.avg_win, self.avg_loss
        return al / (aw + al) if (aw + al) > 0 else 0.0


def _spread_est(px: float, bps: float) -> float:
    return px * bps / 10_000.0


def backtest_symbol(
    df: pd.DataFrame,
    *,
    dip_pct: float,
    profit_bps: float,
    stop_pct: float,
    spread_bps: float,
    max_hold_bars: int,
    entry_timeout_bars: int,
    latency_bars: int = 0,
    fee_bps: float = 0.0,
    mode: str = "dip",
    breakout_lookback: int = 5,
    vol_mult: float = 1.5,
) -> TradeStats:
    st = TradeStats()
    if df is None or len(df) < 30:
        return st
    df = df.reset_index(drop=True)
    close = df["Close"].astype(float).to_numpy()
    high = df["High"].astype(float).to_numpy()
    low = df["Low"].astype(float).to_numpy()
    vol = df["Volume"].astype(float).to_numpy()
    typ = (df["High"].astype(float) + df["Low"].astype(float) + df["Close"].astype(float)) / 3.0
    cum_pv = np.cumsum(typ.to_numpy() * vol)
    cum_v = np.cumsum(vol)
    vwap = np.divide(cum_pv, cum_v, out=np.full_like(cum_pv, np.nan), where=cum_v > 0)
    vol_ma = pd.Series(vol).rolling(20, min_periods=5).mean().to_numpy()

    n = len(df)
    i = max(breakout_lookback, 1)
    while i < n - 1:
        px = close[i]
        vw = vwap[i]
        if not (px > 0 and vw > 0):
            i += 1
            continue

        spread = _spread_est(px, spread_bps)
        if mode == "breakout":
            # Momentum: break above recent high with above-average volume, above VWAP.
            prior_high = high[i - breakout_lookback : i].max()
            vma = vol_ma[i] if vol_ma[i] > 0 else vol[i]
            if not (px > prior_high and px > vw and vol[i] >= vol_mult * vma):
                i += 1
                continue
            st.fills_attempted += 1
            # Breakouts leave the bid behind → taker entry at the ask.
            entry_px = px + spread / 2.0
            j = i  # filled immediately (marketable)
        else:
            # Mean-reversion: dip below VWAP, passive bid entry.
            if (vw - px) / vw < dip_pct:
                i += 1
                continue
            st.fills_attempted += 1
            bid = px - spread / 2.0
            entry_px = bid
            filled = False
            j = i + 1
            timeout_j = min(n - 1, i + entry_timeout_bars)
            while j <= timeout_j:
                if low[j] <= bid:
                    filled = True
                    break
                j += 1
            if not filled:
                i += 1
                continue

        target = entry_px + spread + _spread_est(entry_px, profit_bps)
        stop = entry_px * (1.0 - stop_pct)
        # Event-driven latency: order cannot react until transit + queue delay.
        k0 = min(n - 1, j + max(0, latency_bars))
        exit_deadline = min(n - 1, k0 + max_hold_bars)
        outcome_pnl = None
        k = k0
        while k <= exit_deadline:
            # Stop first (conservative: assume stop hit before target if both in-bar).
            if low[k] <= stop:
                outcome_pnl = stop - entry_px
                st.losses += 1
                st.gross_loss += abs(outcome_pnl)
                break
            if high[k] >= target:
                outcome_pnl = target - entry_px
                st.wins += 1
                st.gross_win += outcome_pnl
                break
            k += 1
        if outcome_pnl is None:
            # Max-hold market-out at bar close (pay half spread to exit).
            exit_px = close[exit_deadline] - spread / 2.0
            outcome_pnl = exit_px - entry_px
            st.timeouts += 1
            if outcome_pnl >= 0:
                st.wins += 1
                st.gross_win += outcome_pnl
            else:
                st.losses += 1
                st.gross_loss += abs(outcome_pnl)
            k = exit_deadline

        if fee_bps > 0:
            fee = entry_px * fee_bps / 10_000.0 * 2.0
            outcome_pnl -= fee

        st.trades += 1
        st.pnls.append(outcome_pnl)
        i = k + 1
    return st


def run(tickers: list[str], args: argparse.Namespace) -> None:
    from analytics.day_trade_yahoo import fetch_yahoo_bars

    agg = TradeStats()
    per_ticker: list[tuple[str, TradeStats]] = []
    for t in tickers:
        try:
            df = fetch_yahoo_bars(t, interval=args.interval, period=args.period)
        except Exception as e:
            print(f"  {t:6s} fetch failed: {e}")
            continue
        st = backtest_symbol(
            df,
            dip_pct=args.dip_pct,
            profit_bps=args.profit_bps,
            stop_pct=args.stop_pct,
            spread_bps=args.spread_bps,
            max_hold_bars=args.max_hold_bars,
            entry_timeout_bars=args.entry_timeout_bars,
            latency_bars=args.latency_bars,
            fee_bps=args.fee_bps,
            mode=args.mode,
            breakout_lookback=args.breakout_lookback,
            vol_mult=args.vol_mult,
        )
        per_ticker.append((t, st))
        agg.trades += st.trades
        agg.wins += st.wins
        agg.losses += st.losses
        agg.timeouts += st.timeouts
        agg.gross_win += st.gross_win
        agg.gross_loss += st.gross_loss
        agg.fills_attempted += st.fills_attempted
        agg.pnls.extend(st.pnls)
        if st.trades:
            print(
                f"  {t:6s} trades={st.trades:4d} win%={st.win_rate*100:5.1f} "
                f"net=${st.net:+8.3f} avgW=${st.avg_win:.3f} avgL=${st.avg_loss:.3f}"
            )

    print("\n=== AGGREGATE (passive entry + bracket exit + stop) ===")
    print(f"  signals (fill attempts):  {agg.fills_attempted}")
    print(f"  filled trades:            {agg.trades}")
    fill_rate = agg.trades / agg.fills_attempted if agg.fills_attempted else 0
    print(f"  fill rate:                {fill_rate*100:.1f}%")
    print(f"  win rate:                 {agg.win_rate*100:.1f}%")
    print(f"  break-even win rate:      {agg.breakeven_win_rate*100:.1f}%")
    print(f"  avg win:                  ${agg.avg_win:.4f}")
    print(f"  avg loss:                 ${agg.avg_loss:.4f}")
    print(f"  timeouts:                 {agg.timeouts}")
    print(f"  NET P&L (per share):      ${agg.net:+.3f}")
    edge = agg.win_rate - agg.breakeven_win_rate
    verdict = "POSITIVE EDGE ✓" if edge > 0 and agg.net > 0 else "NO EDGE — do not deploy"
    print(f"  edge (win% - breakeven):  {edge*100:+.1f} pts  →  {verdict}")


def main() -> None:
    p = argparse.ArgumentParser(description="HFT scalper historical validation")
    p.add_argument("--tickers", default=os.getenv("OBI_TICKER_WHITELIST", "SPY,QQQ,IWM,NVDA,AMD,TSLA,MSFT,NFLX,AMZN"))
    p.add_argument("--interval", default="1m")
    p.add_argument("--period", default="5d")
    p.add_argument("--dip-pct", type=float, default=float(os.getenv("HFT_MR_DIP_PCT", "0.00055")))
    p.add_argument("--profit-bps", type=float, default=float(os.getenv("HFT_MIN_EXIT_PROFIT_BPS", "3")))
    p.add_argument("--stop-pct", type=float, default=float(os.getenv("HFT_MR_STOP_PCT", "0.0015")))
    p.add_argument("--spread-bps", type=float, default=8.0)
    p.add_argument("--max-hold-bars", type=int, default=12)
    p.add_argument("--entry-timeout-bars", type=int, default=3)
    p.add_argument(
        "--latency-bars",
        type=int,
        default=int(os.getenv("HFT_BACKTEST_LATENCY_BARS", "0")),
        help="Bars between fill and first exit check (simulates wire+queue delay)",
    )
    p.add_argument(
        "--fee-bps",
        type=float,
        default=float(os.getenv("HFT_BACKTEST_FEE_BPS", "0")),
        help="Round-trip maker+taker fee in bps (subtracted per trade)",
    )
    p.add_argument("--mode", choices=["dip", "breakout"], default="dip")
    p.add_argument("--breakout-lookback", type=int, default=5)
    p.add_argument("--vol-mult", type=float, default=1.5)
    args = p.parse_args()

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    print(f"Backtesting {len(tickers)} tickers ({args.interval}/{args.period}) ...")
    print(
        f"params: dip={args.dip_pct} profit_bps={args.profit_bps} stop_pct={args.stop_pct} "
        f"spread_bps={args.spread_bps} max_hold={args.max_hold_bars} entry_to={args.entry_timeout_bars} "
        f"latency_bars={args.latency_bars} fee_bps={args.fee_bps}\n"
    )
    run(tickers, args)


if __name__ == "__main__":
    main()
