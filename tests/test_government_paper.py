"""The government fills a paper ledger and the ministries learn the result."""

from analytics.government_paper import nudge_weights, run_government_paper


def _up(n=48):
    px = 100.0
    out = []
    for _ in range(n):
        out.append(px)
        px *= 1.004
    return out


def test_paper_book_buys_and_credits_the_close():
    learned = []

    def _learn(sym, gain):
        learned.append((sym, gain))
        return {"applied": ["test"]}

    book = run_government_paper({"AAPL": _up()}, equity=100_000, ticket=5_000, learn=_learn)
    buys = [t for t in book["trades"] if t["side"] == "BUY"]
    sells = [t for t in book["trades"] if t["side"] == "SELL"]
    assert buys and sells
    assert buys[0]["n_desks"] >= 2500
    assert learned and learned[-1][0] == "AAPL"
    assert book["equity"] != 100_000
    assert book["open"] == 0


def test_market_book_gives_the_slot_to_the_trend():
    from analytics.government_paper import run_market_book

    def _path(n, step):
        px = 80.0
        dates = []
        closes = []
        for i in range(n):
            dates.append(f"2026-01-{i+1:02d}" if i < 28 else f"2026-02-{i-27:02d}")
            closes.append(px)
            px *= step
        return {"dates": dates, "closes": closes}

    book = run_market_book(
        {"UP": _path(48, 1.004), "DOWN": _path(48, 0.997)},
        equity=100_000,
        ticket=5_000,
        max_names=1,
        sessions=16,
        learn=None,
    )
    buys = [t["symbol"] for t in book["trades"] if t["side"] == "BUY"]
    assert buys
    assert buys[0] == "UP"
    assert book["census"]["n"] == 2
    assert book["desk_rounds"] >= 2500 * 2
    assert book["open"] == 0
    marks = [t for t in book["trades"] if t["side"] == "SELL" and t["symbol"] == "UP" and t["reason"] == "mark"]
    assert marks and marks[-1]["gain"] > 0


def test_online_signal_does_not_see_tomorrow():
    from analytics.history_reward import online_signals

    closes = [50.0 + i * 0.15 for i in range(70)]
    full = online_signals(closes)
    cut = online_signals(closes[:50])
    assert full[40] is not None and cut[40] is not None
    assert abs(full[40][0] - cut[40][0]) < 1e-12


def test_one_session_book_compounds_and_does_not_see_tomorrow():
    from analytics.history_reward import online_signals, run_history

    def panel(step: float, n: int = 45) -> dict:
        px = 50.0
        dates = []
        closes = []
        for i in range(n):
            dates.append(f"2020-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}")
            closes.append(px)
            px *= step
        return {"dates": dates, "closes": closes, "sig": online_signals(closes)}

    up = run_history({"UP": panel(1.004)}, daily=True, max_names=1)
    assert up["days_invested"] > 5
    assert up["bought"] < up["days_invested"]
    assert up["equity"] > 100_000
    # Ten percent of the book in a name that rises every day. Not (1.01)^n on the whole stake.
    assert up["equity"] < 100_000 * (1.004 ** 45)
    down = run_history({"DN": panel(0.997)}, daily=True, max_names=1)
    assert down["equity"] < up["equity"]


def test_a_wider_down_day_is_allowed_when_every_stock_is_in():
    from analytics.history_reward import run_history

    n = 8
    dates = [f"2020-04-{i + 1:02d}" for i in range(n)]
    closes = [50.0 * (1.002 ** i) for i in range(n)]
    sig = [(0.72, 0.02, 0.04) for _ in range(n)]
    panel = {"dates": dates, "closes": closes, "sig": sig}
    tight = run_history({"W": panel}, daily=True, max_names=1, max_avg_down=0.025)
    wide = run_history({"W": panel}, daily=True, max_names=1, max_avg_down=None)
    assert tight["bought"] == 0
    assert wide["bought"] > 0
    assert wide["equity"] != 100_000


def test_model_confidence_is_only_taken_from_the_holdout():
    from analytics.model_edge import confident_tail

    probs = [0.40] * 80 + [0.90, 0.20] + [0.40] * 17 + [0.95]
    dates = [f"d{i:03d}" for i in range(100)]
    got = confident_tail(probs, dates, holdout_frac=0.2, percentile=80)
    assert "d010" not in got
    assert got["d080"] == 0.90
    assert "d081" not in got
    assert got["d099"] == 0.95


def test_timeframes_train_without_seeing_tomorrow():
    from analytics.timeframe_learner import timeframe_signals

    up = [50.0 * (1.002 ** i) for i in range(160)]
    full = timeframe_signals(up)
    cut = timeframe_signals(up[:121])
    assert full[120] == cut[120]
    assert any(row is not None for row in full[100:])
    down = [50.0 * (0.998 ** i) for i in range(160)]
    down_hits = sum(1 for row in timeframe_signals(down) if row is not None)
    up_hits = sum(1 for row in full if row is not None)
    assert up_hits > down_hits


def test_a_loss_is_denied_and_a_win_is_granted():
    from analytics.asymmetric_loss import asymmetric_reward

    win = asymmetric_reward("LONG", 0.02, bars_held=4)
    loss = asymmetric_reward("LONG", -0.04, bars_held=3)
    assert win.reward > 0
    assert loss.reward < 0
    assert abs(loss.reward) > win.reward


def test_three_timeframes_are_required_for_a_long():
    from analytics.ai_government import convene
    agreed = convene(
        {
            "p_up": 0.8,
            "p_1": 0.72,
            "p_5": 0.70,
            "p_20": 0.66,
            "p_60": 0.40,
            "avg_up": 0.02,
            "avg_down": 0.005,
            "exec_conf": 0.8,
        },
        record=False,
    )
    assert agreed["tf_agree"] == 3
    assert agreed["action"] == "LONG"
    split = convene(
        {
            "p_up": 0.8,
            "p_1": 0.80,
            "p_5": 0.42,
            "p_20": 0.42,
            "p_60": 0.42,
            "avg_up": 0.02,
            "avg_down": 0.005,
            "exec_conf": 0.8,
        },
        record=False,
    )
    assert split["tf_agree"] == 1
    assert split["action"] == "FLAT"
    assert split["veto"] == "timeframe"


def test_stopped_trades_are_replayed_into_the_learners():
    from analytics.government_paper import study_losses

    seen = []

    def _learn(sym, gain, extra=None):
        seen.append((sym, round(gain, 3)))
        return {"applied": ["test"]}

    lesson = study_losses(
        [
            {"side": "SELL", "symbol": "PLU", "gain": -0.29, "sections": {"treasury": {"round2": 1.0}}},
            {"side": "SELL", "symbol": "AEHR", "gain": 0.2, "sections": {"treasury": {"round2": 1.0}}},
        ],
        rounds=3,
        learn=_learn,
        train_neural=False,
    )
    assert lesson["losses"] == 1
    assert lesson["steps"] == 3
    assert seen == [("PLU", -0.29)] * 3
    assert lesson["weights"]["treasury"] < 1.6


def test_a_winner_makes_the_yes_ministries_heavier():
    weights = nudge_weights(
        {"treasury": 1.0, "opposition": 0.45},
        {"treasury": {"round2": 1.0}, "opposition": {"round2": -1.0}},
        0.02,
    )
    assert weights["treasury"] > 1.0
    assert weights["opposition"] == 0.45
