import numpy as np
import pandas as pd
from feature_engineering import build_features
from strategy import generate_signals


def performance_stats(strategy_ret: pd.Series) -> dict:
    """Sharpe (ann.), max drawdown, hit rate — Johnston backtest bar."""
    r = pd.Series(strategy_ret).dropna().astype(float)
    n = int(len(r))
    if n < 2:
        return {"sharpe": 0.0, "max_dd": 0.0, "hit_rate": 0.0, "n": n, "mean": 0.0}
    mu = float(r.mean())
    sd = float(r.std(ddof=1) or 0.0)
    sharpe = (mu / sd) * float(np.sqrt(252.0)) if sd > 0 else 0.0
    equity = (1.0 + r).cumprod()
    from analytics.quant_risk import max_drawdown

    dd = float(max_drawdown(equity.to_numpy()))
    hits = r[r != 0]
    hit_rate = float((hits > 0).mean()) if len(hits) else 0.0
    return {
        "sharpe": round(sharpe, 4),
        "max_dd": round(dd, 4),
        "hit_rate": round(hit_rate, 4),
        "n": n,
        "mean": round(mu, 6),
    }


def run_backtest(
    ticker: str,
    start: str = "2023-01-01",
    end: str | None = None,
    capital: float = 10000.0,
) -> pd.DataFrame:
    df = build_features(ticker, start, end)
    if df.empty:
        return pd.DataFrame()

    if "returns" not in df.columns:
        raise ValueError("build_features must include 'returns'")

    df["signal"] = generate_signals(df)
    df["position"] = df["signal"].replace(0, np.nan).ffill().shift().fillna(0)
    df["strategy_ret"] = df["position"] * df["returns"]
    df["equity"] = (1 + df["strategy_ret"]).cumprod() * capital
    return df


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Run backtest for one ticker.")
    p.add_argument("--ticker", required=True)
    p.add_argument("--start", default="2023-01-01")
    p.add_argument("--end", default=None)
    p.add_argument("--capital", type=float, default=10000)
    args = p.parse_args()

    result = run_backtest(
        ticker=args.ticker,
        start=args.start,
        end=args.end,
        capital=args.capital,
    )
    if result.empty:
        print("No data for backtest.")
    else:
        stats = performance_stats(result["strategy_ret"])
        print(f"Final equity for {args.ticker}: {result['equity'].iloc[-1]:.2f}")
        print(
            f"Sharpe={stats['sharpe']:.2f}  maxDD={stats['max_dd']:.2%}  "
            f"hit={stats['hit_rate']:.2%}  n={stats['n']}"
        )
        print(result[["equity"]].tail())
