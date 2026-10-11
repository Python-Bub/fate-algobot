"""The holdout bar is set on the fit period. One half of the names picks the lever."""

from analytics.holdout_edge import (
    choose_lever,
    clearly_better,
    combiner_probs,
    even_symbols,
    forward_return,
    shot_returns,
    split_halves,
    summarize,
    train_threshold,
)


def _closes(n=120, step=1.001):
    px = 50.0
    out = []
    for _ in range(n):
        out.append(px)
        px *= step
    return out


def test_threshold_comes_from_the_fit_period_only():
    probs = [0.40] * 80 + [0.90] * 20
    cut, thr = train_threshold(probs)
    assert cut == 80
    assert thr == 0.40


def test_a_wild_down_day_is_dropped_and_a_calm_day_is_kept():
    closes = _closes(100)
    # Flat probabilities so the 80th percentile is 0.70 and every holdout row clears it.
    p_short = [0.70] * 100
    avg_down = [0.04] * 100
    votes = [[0.6, 0.6, 0.6, 0.6]] * 100
    avg_down[90] = 0.01
    shots = shot_returns(closes, p_short, avg_down=avg_down, votes=votes)
    assert summarize(shots["A"])["n"] > summarize(shots["B"])["n"]
    assert summarize(shots["B"])["n"] == 1
    assert summarize(shots["D"])["n"] == 1
    assert summarize(shots["C"])["n"] == summarize(shots["A"])["n"]


def test_timeframe_disagreement_drops_the_shot():
    closes = _closes(100)
    p_short = [0.80] * 100
    avg_down = [0.01] * 100
    votes = [[0.2, 0.2, 0.2, 0.9]] * 100
    shots = shot_returns(closes, p_short, avg_down=avg_down, votes=votes)
    assert shots["A"]
    assert shots["C"] == []
    assert shots["D"] == []
    assert shots["F"] == []
    assert shots["B"]
    assert shots["U"]


def test_the_five_day_vote_keeps_a_shot_the_other_horizons_reject():
    closes = _closes(100)
    p_short = [0.80] * 100
    avg_down = [0.01] * 100
    votes = [[0.2, 0.6, 0.2, 0.2]] * 100
    shots = shot_returns(closes, p_short, avg_down=avg_down, votes=votes)
    assert shots["F"]
    assert shots["F"] == shots["A"]
    assert shots["C"] == []


def test_forward_return_does_not_read_past_the_horizon():
    closes = [10.0, 10.0, 10.0, 10.0, 10.0, 11.0]
    assert abs(forward_return(closes, 0, 5) - 0.1) < 1e-12
    assert forward_return(closes, 1, 5) is None


def test_combiner_does_not_see_the_five_day_forward():
    n = 40
    closes = _closes(n, step=1.002)
    p_short = [0.6] * n
    votes = [[0.6, 0.6, 0.6, 0.6]] * n
    avg_up = [0.01] * n
    avg_down = [0.01] * n
    full = combiner_probs(closes, p_short, votes, avg_up, avg_down)
    cut = combiner_probs(closes[:30], p_short[:30], votes[:30], avg_up[:30], avg_down[:30])
    assert full[29] is not None
    assert abs(full[29] - cut[29]) < 1e-12


def test_the_lever_is_chosen_without_the_confirm_half():
    weak = {"n": 200, "mean": 0.010, "hit": 0.5, "mean_net": 0.009}
    strong = {"n": 180, "mean": 0.021, "hit": 0.6, "mean_net": 0.020}
    tiny = {"n": 10, "mean": 0.05, "hit": 0.9, "mean_net": 0.049}
    select = {"A": weak, "B": strong, "C": weak, "D": strong, "E": tiny, "L": weak}
    assert choose_lever(select) == "D"
    assert clearly_better(strong, weak)
    assert not clearly_better(tiny, weak)
    assert not clearly_better({"n": 200, "mean": 0.013}, weak)


def test_a_cutoff_that_misses_the_confirm_bar_is_dropped():
    from analytics.holdout_edge import walk_levers

    def row(mean, n=400):
        return {"n": n, "mean": mean, "hit": 0.6, "mean_net": mean - 0.001}

    select = {"cut80": row(0.020), "cut90": row(0.030), "cut70": row(0.018), "cut95": row(0.015), "cut62": row(0.016)}
    confirm = {"cut80": row(0.020), "cut90": row(0.010), "cut70": row(0.017), "cut95": row(0.011), "cut62": row(0.013)}
    for pct in (70, 80, 90, 95):
        for k in (1, 2, 3, 4):
            select[f"cut{pct}_agree{k}"] = row(0.01)
            confirm[f"cut{pct}_agree{k}"] = row(0.01)
        select[f"cut62_agree{k}"] = row(0.01)
        confirm[f"cut62_agree{k}"] = row(0.01)
    for spec in ("1", "5", "20", "60", "1-5", "5-20", "1-5-20", "20-60"):
        select[f"cut80_h_{spec}"] = row(0.01)
        confirm[f"cut80_h_{spec}"] = row(0.01)
    for hold, mean in ((1, 0.002), (10, 0.02), (20, 0.03)):
        select[f"cut80_hold{hold}"] = row(mean)
        confirm[f"cut80_hold{hold}"] = row(mean)
    walked = walk_levers(select, confirm)
    assert walked["steps"][0]["candidate"] == "cut90"
    assert walked["steps"][0]["action"] == "drop"
    assert walked["rule"] == "cut80"


def test_a_horizon_set_is_kept_only_when_confirm_beats_both_bars():
    from analytics.holdout_edge import walk_levers

    def row(mean, n=400):
        return {"n": n, "mean": mean, "hit": 0.6, "mean_net": mean - 0.001}

    select = {f"cut{pct}": row(0.02) for pct in (70, 80, 90, 95)}
    select["cut62"] = row(0.02)
    confirm = {key: row(0.02) for key in select}
    for pct in (70, 80, 90, 95):
        for k in (1, 2, 3, 4):
            select[f"cut{pct}_agree{k}"] = row(0.015)
            confirm[f"cut{pct}_agree{k}"] = row(0.015)
    for k in (1, 2, 3, 4):
        select[f"cut62_agree{k}"] = row(0.015)
        confirm[f"cut62_agree{k}"] = row(0.015)
    for spec in ("1", "5", "20", "60", "1-5", "5-20", "1-5-20", "20-60"):
        select[f"cut80_h_{spec}"] = row(0.015)
        confirm[f"cut80_h_{spec}"] = row(0.015)
    select["cut80_h_5"] = row(0.028)
    confirm["cut80_h_5"] = row(0.024)
    for hold in (1, 10, 20):
        select[f"cut80_h_5_hold{hold}"] = row(0.001)
        confirm[f"cut80_h_5_hold{hold}"] = row(0.001)
        select[f"cut80_hold{hold}"] = row(0.001)
        confirm[f"cut80_hold{hold}"] = row(0.001)
    walked = walk_levers(select, confirm)
    assert walked["steps"][2]["action"] == "keep"
    assert walked["steps"][2]["candidate"] == "cut80_h_5"
    assert walked["rule"] == "cut80_h_5"


def test_a_longer_hold_does_not_win_just_because_the_raw_move_is_larger():
    from analytics.holdout_edge import five_day_equivalent, walk_levers

    def row(mean, n=400):
        return {"n": n, "mean": mean, "hit": 0.6, "mean_net": mean - 0.001}

    assert five_day_equivalent(0.04, 20) < 0.012
    select = {f"cut{pct}": row(0.03) for pct in (70, 80, 90, 95)}
    select["cut62"] = row(0.02)
    confirm = {key: row(0.028) for key in select}
    for pct in list((70, 80, 90, 95)) + [62]:
        stem = f"cut{pct}"
        for k in (1, 2, 3, 4):
            select[f"{stem}_agree{k}"] = row(0.01)
            confirm[f"{stem}_agree{k}"] = row(0.01)
        for spec in ("1", "5", "20", "60", "1-5", "5-20", "1-5-20", "20-60"):
            select[f"{stem}_h_{spec}"] = row(0.01)
            confirm[f"{stem}_h_{spec}"] = row(0.01)
    select["cut80_hold1"] = row(0.004)
    confirm["cut80_hold1"] = row(0.004)
    select["cut80_hold10"] = row(0.04)
    confirm["cut80_hold10"] = row(0.04)
    select["cut80_hold20"] = row(0.06)
    confirm["cut80_hold20"] = row(0.06)
    walked = walk_levers(select, confirm)
    assert walked["rule"] == "cut80"


def test_symbol_split_is_alphabetical_and_even():
    names = [f"S{i:03d}" for i in range(100)]
    picked = even_symbols(names, 10)
    assert picked[0] == "S000"
    assert picked[-1] == "S099"
    assert len(picked) == 10
    left, right = split_halves(picked)
    assert left[-1] < right[0]
    assert len(left) == len(right)
