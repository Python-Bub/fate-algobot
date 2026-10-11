"""5-day holdout edge. The fit period sets the bar. The last 20% is the score.

A shot's outcome is the overlapping 5-day forward return. That return is never
a feature, and it is never used to pick the threshold. One lever is chosen on
the first half of a fixed symbol list. The second half only confirms it.
"""

from __future__ import annotations

import math

import numpy as np

COST_BPS = 0.001
CALM_AVG_DOWN = 0.025
AGREE_NEED = 3
AGREE_FLOOR = 0.55
FIXED_P = 0.62
CLEAR_LIFT = 0.004
CLEAR_FLOOR = 0.012
MIN_SHOTS = 100
LEVERS = ("F", "D", "B", "C", "E", "L")


def train_cut(n: int, holdout_frac: float = 0.2) -> int | None:
    """Index where the holdout starts. None when the series is too short."""
    if n < 80:
        return None
    cut = int(n * (1.0 - holdout_frac))
    return min(max(cut, 40), n - 15)


def train_threshold(probs: list[float], *, holdout_frac: float = 0.2, percentile: float = 80.0) -> tuple[int, float] | None:
    """80th percentile of fit-period probabilities, and the holdout index."""
    cut = train_cut(len(probs), holdout_frac)
    if cut is None:
        return None
    thr = float(np.percentile(np.asarray(probs[:cut], dtype=float), percentile))
    return cut, thr


def forward_return(closes: list[float], i: int, horizon: int = 5) -> float | None:
    """Close-to-close return over the next ``horizon`` bars. None at the edge."""
    j = i + horizon
    if i < 0 or j >= len(closes):
        return None
    entry = float(closes[i])
    exit_px = float(closes[j])
    if entry <= 0 or exit_px <= 0:
        return None
    return exit_px / entry - 1.0


def _sigmoid(z: float) -> float:
    z = max(-20.0, min(20.0, z))
    return 1.0 / (1.0 + math.exp(-z))


def combiner_probs(
    closes: list[float],
    p_short: list[float],
    votes: list[list[float] | None],
    avg_up: list[float | None],
    avg_down: list[float | None],
    *,
    lr: float = 0.15,
) -> list[float | None]:
    """P(the next 5 sessions finish up), updated only after that span has printed.

    At bar ``t`` the weight update uses the decision made at ``t - 5``. Its
    label is ``close[t]`` against ``close[t - 5]``, both already known.
    ``close[t + 1]`` and later never enter the weight or the feature.
    """
    n = len(closes)
    out: list[float | None] = [None] * n
    w = np.zeros(8, dtype=float)
    for t in range(n):
        src = t - 5
        if (
            src >= 0
            and votes[src] is not None
            and avg_up[src] is not None
            and avg_down[src] is not None
            and closes[src] > 0
            and closes[t] > 0
        ):
            x = _comb_x(p_short[src], votes[src], float(avg_up[src]), float(avg_down[src]))
            y = 1.0 if closes[t] > closes[src] else 0.0
            p = _sigmoid(float(x @ w))
            w -= lr * (p - y) * x
        if votes[t] is None or avg_up[t] is None or avg_down[t] is None:
            continue
        x = _comb_x(p_short[t], votes[t], float(avg_up[t]), float(avg_down[t]))
        out[t] = _sigmoid(float(x @ w))
    return out


def _comb_x(p_short: float, votes: list[float], avg_up: float, avg_down: float) -> np.ndarray:
    return np.asarray(
        [1.0, float(p_short), float(votes[0]), float(votes[1]), float(votes[2]), float(votes[3]), float(avg_up), float(avg_down)],
        dtype=float,
    )


def _agree(votes: list[float] | None) -> int:
    if not votes:
        return 0
    return sum(1 for p in votes if p >= AGREE_FLOOR)


def shot_returns(
    closes: list[float],
    p_short: list[float],
    *,
    avg_down: list[float | None],
    votes: list[list[float] | None],
    p_long: list[float] | None = None,
    p_comb: list[float | None] | None = None,
    holdout_frac: float = 0.2,
    percentile: float = 80.0,
) -> dict[str, list[float]]:
    """Overlapping 5-day returns for each pre-registered rule. Holdout rows only."""
    empty = {k: [] for k in ("P62", "A", "B", "C", "D", "E", "L", "F", "U")}
    if len(closes) != len(p_short) or len(avg_down) != len(closes) or len(votes) != len(closes):
        return empty
    bar = train_threshold(p_short, holdout_frac=holdout_frac, percentile=percentile)
    if bar is None:
        return empty
    cut, thr = bar
    comb_thr = None
    if p_comb is not None and len(p_comb) == len(closes):
        fit = [float(p) for p in p_comb[:cut] if p is not None]
        if len(fit) >= 40:
            comb_thr = float(np.percentile(np.asarray(fit, dtype=float), percentile))
    for i in range(cut, len(closes)):
        ret = forward_return(closes, i, 5)
        if ret is None:
            continue
        p = float(p_short[i])
        down = avg_down[i]
        agree = _agree(votes[i])
        calm = down is not None and down <= CALM_AVG_DOWN
        agreed = agree >= AGREE_NEED
        long_ok = p_long is not None and i < len(p_long) and float(p_long[i]) >= 0.5
        p5 = None if not votes[i] else float(votes[i][1])
        confident = p >= thr
        empty["U"].append(ret)
        if p >= FIXED_P:
            empty["P62"].append(ret)
        if confident:
            empty["A"].append(ret)
        if confident and calm:
            empty["B"].append(ret)
        if confident and agreed:
            empty["C"].append(ret)
        if confident and calm and agreed:
            empty["D"].append(ret)
        if long_ok and confident:
            empty["L"].append(ret)
        if comb_thr is not None and p_comb is not None and p_comb[i] is not None and float(p_comb[i]) >= comb_thr:
            empty["E"].append(ret)
        if confident and p5 is not None and p5 >= 0.5:
            empty["F"].append(ret)
    return empty


def summarize(returns: list[float]) -> dict:
    """Hit rate, raw mean, and mean after a 10 bp round trip."""
    n = len(returns)
    if n == 0:
        return {"n": 0, "hit": None, "mean": None, "mean_net": None}
    hit = sum(1 for r in returns if r > 0) / n
    mean = sum(returns) / n
    return {"n": n, "hit": hit, "mean": mean, "mean_net": mean - COST_BPS}


def daily_accuracy(p_daily: list[float], closes: list[float], cut: int) -> dict:
    """Holdout days where P(up) >= 0.5 versus the next close. No confidence filter."""
    n = 0
    hit = 0
    for i in range(cut, len(closes) - 1):
        if closes[i] <= 0 or closes[i + 1] <= 0:
            continue
        n += 1
        pred = float(p_daily[i]) >= 0.5
        actual = closes[i + 1] > closes[i]
        if pred == actual:
            hit += 1
    return {"n": n, "hit": (hit / n) if n else None}


def pool_summaries(per_symbol: list[dict], symbols: list[str]) -> dict[str, dict]:
    """Concatenate shots for ``symbols`` and summarize every rule."""
    want = set(symbols)
    bags: dict[str, list[float]] = {k: [] for k in ("P62", "A", "B", "C", "D", "E", "L", "F", "U")}
    for row in per_symbol:
        if row.get("symbol") not in want or row.get("error"):
            continue
        shots = row.get("shots") or {}
        for key in bags:
            bags[key].extend(shots.get(key) or [])
    return {key: summarize(vals) for key, vals in bags.items()}


def clearly_better(lever: dict, base: dict) -> bool:
    """True when the lever beats the baseline by a pre-stated margin.

    The mean has to clear the measured baseline, clear about 1.2% over five
    days, and add at least 0.4 percentage points. Fewer than 100 shots is not
    a result.
    """
    if int(lever.get("n") or 0) < MIN_SHOTS:
        return False
    if lever.get("mean") is None or base.get("mean") is None:
        return False
    if float(lever["mean"]) <= float(base["mean"]):
        return False
    if float(lever["mean"]) - float(base["mean"]) < CLEAR_LIFT:
        return False
    if float(lever["mean"]) <= CLEAR_FLOOR:
        return False
    return True


def choose_lever(select: dict[str, dict]) -> str | None:
    """Highest-mean lever on the select half. The confirm half is not an input."""
    base = select.get("A") or {}
    winners = [name for name in LEVERS if clearly_better(select.get(name) or {}, base)]
    if not winners:
        return None
    return max(winners, key=lambda name: (float(select[name]["mean"]), -LEVERS.index(name)))


CUTOFFS = (70, 80, 90, 95)
AGREE_COUNTS = (1, 2, 3, 4)
HORIZON_SETS = ("1", "5", "20", "60", "1-5", "5-20", "1-5-20", "20-60")
HOLD_DAYS = (1, 5, 10, 20)
_HORIZON_AT = {"1": 0, "5": 1, "20": 2, "60": 3}


def _blank() -> dict:
    return {"n": 0, "n_up": 0, "sum": 0.0}


def _add(bucket: dict, ret: float) -> None:
    bucket["n"] += 1
    bucket["sum"] += float(ret)
    if ret > 0:
        bucket["n_up"] += 1


def finish_bucket(bucket: dict) -> dict:
    """Turn a shot counter into the same summary shape as ``summarize``."""
    n = int(bucket.get("n") or 0)
    if n == 0:
        return {"n": 0, "hit": None, "mean": None, "mean_net": None}
    mean = float(bucket["sum"]) / n
    return {
        "n": n,
        "hit": int(bucket.get("n_up") or 0) / n,
        "mean": mean,
        "mean_net": mean - COST_BPS,
    }


def pool_buckets(per_symbol: list[dict], symbols: list[str]) -> dict[str, dict]:
    """Add shot counters across names, then summarize."""
    want = set(symbols)
    totals: dict[str, dict] = {}
    for row in per_symbol:
        if row.get("symbol") not in want or row.get("error"):
            continue
        for key, bucket in (row.get("grid") or {}).items():
            dest = totals.setdefault(key, _blank())
            dest["n"] += int(bucket.get("n") or 0)
            dest["n_up"] += int(bucket.get("n_up") or 0)
            dest["sum"] += float(bucket.get("sum") or 0.0)
    return {key: finish_bucket(bucket) for key, bucket in totals.items()}


def five_day_equivalent(mean: float | None, hold: int) -> float | None:
    """Compound ``mean`` over ``hold`` sessions down to a five-session return."""
    if mean is None or hold <= 0 or mean <= -1.0:
        return None
    return (1.0 + float(mean)) ** (5.0 / float(hold)) - 1.0


def beats_five_day_baseline(summary: dict, *, hold: int = 5) -> bool:
    """True when the confirm half clears about 1.2% over five days, with enough shots."""
    if int(summary.get("n") or 0) < MIN_SHOTS:
        return False
    equiv = five_day_equivalent(summary.get("mean"), hold)
    return equiv is not None and equiv > CLEAR_FLOOR


def lever_grid(
    closes: list[float],
    p_short: list[float],
    votes: list[list[float] | None],
) -> dict[str, dict]:
    """Shot counters for cutoff, agreement, horizon set, and hold length.

    Every threshold is the fit-period percentile (or the fixed 0.62 probe).
    Outcomes use only closes after the decision bar. The confirm half is not
    an input here; this is one symbol.
    """
    stems = [f"cut{pct}" for pct in CUTOFFS] + ["cut62"]
    keys = ["U"]
    for stem in stems:
        keys.append(stem)
        for k in AGREE_COUNTS:
            keys.append(f"{stem}_agree{k}")
        for spec in HORIZON_SETS:
            keys.append(f"{stem}_h_{spec}")
        for hold in HOLD_DAYS:
            keys.append(f"{stem}_hold{hold}")
            for k in AGREE_COUNTS:
                keys.append(f"{stem}_agree{k}_hold{hold}")
            for spec in HORIZON_SETS:
                keys.append(f"{stem}_h_{spec}_hold{hold}")
    out = {key: _blank() for key in keys}
    n = len(closes)
    if n != len(p_short) or n != len(votes):
        return out
    cut = train_cut(n)
    if cut is None:
        return out
    fit = np.asarray(p_short[:cut], dtype=float)
    bars = {pct: float(np.percentile(fit, pct)) for pct in CUTOFFS}
    bars[62] = FIXED_P
    last = n - 1
    for i in range(cut, n):
        vote = votes[i]
        agree = _agree(vote)
        p = float(p_short[i])
        rets = {}
        for hold in HOLD_DAYS:
            if i + hold <= last:
                rets[hold] = forward_return(closes, i, hold)
        ret5 = rets.get(5)
        if ret5 is not None:
            _add(out["U"], ret5)
        passed = {name: p >= thr for name, thr in (("70", bars[70]), ("80", bars[80]), ("90", bars[90]), ("95", bars[95]), ("62", bars[62]))}
        if not any(passed.values()):
            continue
        horizon_ok = {}
        if vote is not None and len(vote) >= 4:
            for spec in HORIZON_SETS:
                need = spec.split("-")
                horizon_ok[spec] = all(float(vote[_HORIZON_AT[h]]) >= AGREE_FLOOR for h in need)
        for name, ok in passed.items():
            if not ok:
                continue
            stem = f"cut{name}"
            if ret5 is not None:
                _add(out[stem], ret5)
                for k in AGREE_COUNTS:
                    if agree >= k:
                        _add(out[f"{stem}_agree{k}"], ret5)
                for spec, h_ok in horizon_ok.items():
                    if h_ok:
                        _add(out[f"{stem}_h_{spec}"], ret5)
            for hold, ret in rets.items():
                if ret is None:
                    continue
                _add(out[f"{stem}_hold{hold}"], ret)
                for k in AGREE_COUNTS:
                    if agree >= k:
                        _add(out[f"{stem}_agree{k}_hold{hold}"], ret)
                for spec, h_ok in horizon_ok.items():
                    if h_ok:
                        _add(out[f"{stem}_h_{spec}_hold{hold}"], ret)
    return out


def _hold_of(rule: str) -> int:
    if "_hold" not in rule:
        return 5
    return int(rule.rsplit("_hold", 1)[1])


def _equiv(summary: dict, rule: str) -> float | None:
    return five_day_equivalent(summary.get("mean"), _hold_of(rule))


def _better(select: dict[str, dict], keys: list[str]) -> str | None:
    """Highest five-day-equivalent on the select half. Short samples are ignored."""
    best = None
    best_eq = None
    for key in keys:
        summary = select.get(key) or {}
        if int(summary.get("n") or 0) < MIN_SHOTS:
            continue
        eq = _equiv(summary, key)
        if eq is None:
            continue
        if best_eq is None or eq > best_eq:
            best = key
            best_eq = eq
    return best


def _keep(confirm: dict[str, dict], candidate: str, current: str) -> bool:
    """Keep a lever only when the untouched half beats 1.2% and the rule it replaces."""
    cand = confirm.get(candidate) or {}
    cur = confirm.get(current) or {}
    if not beats_five_day_baseline(cand, hold=_hold_of(candidate)):
        return False
    cand_eq = _equiv(cand, candidate)
    cur_eq = _equiv(cur, current)
    if cand_eq is None or cur_eq is None:
        return False
    return cand_eq > cur_eq


def walk_levers(select: dict[str, dict], confirm: dict[str, dict]) -> dict:
    """Try cutoff, agreement, horizon set, then hold. Confirm is only an accept/reject.

    A candidate is chosen on ``select``. It is dropped when the confirm half
    does not beat about 1.2% over five days, or when it loses to the rule
    already kept. The next family starts from whatever survived.
    """
    rule = "cut80"
    steps = []

    def _step(family: str, keys: list[str]) -> None:
        nonlocal rule
        cand = _better(select, keys)
        if cand is None or cand == rule:
            steps.append({"family": family, "candidate": cand, "action": "unchanged", "rule": rule})
            return
        if _keep(confirm, cand, rule):
            steps.append({"family": family, "candidate": cand, "action": "keep", "rule": cand})
            rule = cand
            return
        steps.append({"family": family, "candidate": cand, "action": "drop", "rule": rule})

    _step("cutoff", [f"cut{pct}" for pct in CUTOFFS] + ["cut62"])
    base = rule.split("_")[0]
    _step("agree", [rule] + [f"{base}_agree{k}" for k in AGREE_COUNTS])
    base = rule.split("_")[0]
    if "_agree" in rule or "_h_" in rule:
        kept_filter = rule
    else:
        kept_filter = base
    _step("horizon", [rule] + [f"{base}_h_{spec}" for spec in HORIZON_SETS])
    entry = rule
    _step("hold", [f"{entry}_hold{h}" if h != 5 else entry for h in HOLD_DAYS])
    # Holding five sessions is the entry rule itself, so the key may be ``cut80``
    # rather than ``cut80_hold5``. Both name the same shots when no earlier
    # filter was kept. When a filter was kept, hold-5 is that filter's 5-day mean.
    return {"rule": rule, "steps": steps, "entry": entry, "filter": kept_filter}


def even_symbols(symbols: list[str], k: int = 48) -> list[str]:
    """``k`` names spread evenly through a sorted universe. Deterministic."""
    uniq = sorted({s.strip().upper() for s in symbols if str(s).strip()})
    if k <= 0 or len(uniq) <= k:
        return uniq
    picked: list[str] = []
    for i in range(k):
        sym = uniq[round(i * (len(uniq) - 1) / (k - 1))]
        if not picked or picked[-1] != sym:
            picked.append(sym)
    return picked


def split_halves(symbols: list[str]) -> tuple[list[str], list[str]]:
    """Alphabetical first half selects the lever. Second half confirms it."""
    ordered = list(symbols)
    mid = len(ordered) // 2
    return ordered[:mid], ordered[mid:]
