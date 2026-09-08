import pandas as pd

from analytics.chart_structure import chart_structure_score, enrich_chart_structure


def test_chart_structure_columns_and_score():
    idx = pd.date_range("2024-01-01", periods=40, freq="B")
    close = pd.Series(range(100, 140), index=idx, dtype=float)
    df = pd.DataFrame(
        {
            "Open": close - 0.5,
            "High": close + 1.0,
            "Low": close - 1.5,
            "Close": close,
            "Volume": 1_000_000,
        },
        index=idx,
    )
    out = enrich_chart_structure(df)
    for c in (
        "vol_climax_z",
        "atr_channel_pos",
        "close_stretch_20",
        "wick_reject",
        "ema_ribbon_spread",
        "range_compress",
        "broke_high",
        "broke_low",
        "volume_trend",
        "gap_pct",
    ):
        assert c in out.columns
        assert out[c].notna().all()
    s = chart_structure_score(out.iloc[-1])
    assert -0.08 <= s <= 0.08
