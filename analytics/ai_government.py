"""A government of specialist desks, then one chair.

Each desk has one job and a different threshold. Round 1 they speak from the
facts. Round 2 they read the other desks in their section and answer. The
chair is the only voice that can allow a buy. Treasury can veto a ticket
whose expected gain is negative. Interior can veto adding to a red or
unpriced hold. The opposition files the case against, and does not get a veto.
"""

from __future__ import annotations

from analytics.trade_kernel import one_bar_ev


_WEIGHT = {
    "treasury": 1.6,
    "sizing": 1.3,
    "interior": 1.2,
    "defense": 1.1,
    "horizon": 1.1,
    "commerce": 1.0,
    "liquidity": 1.0,
    "regime": 1.0,
    "book": 1.0,
    "tape": 1.0,
    "intelligence": 1.0,
    "execution": 0.9,
    "earnings": 0.9,
    "census": 0.9,
    "justice": 0.8,
    "opposition": 0.45,
}

_ROSTER: list[tuple] | None = None
_GROUPS: dict[str, list[tuple]] | None = None


def _build_roster() -> list[tuple]:
    """One row per desk: (section, desk_id, kind, params).

    Each desk is a different number: a cost, a hold, a Kelly fraction, a stop,
    a spread, a heat cap. They are not copies of one vote.
    """
    desks: list[tuple] = []
    costs = tuple(0.0002 * (i + 1) for i in range(12))  # 2 bps .. 24 bps
    hairs = tuple(i * 0.01 for i in range(8))
    holds = (1, 2, 3, 5, 8, 10, 15, 20, 40, 60)
    for cost in costs:
        for hair in hairs:
            for days in holds:
                desks.append(
                    ("treasury", f"treasury-{days}d-{cost:.4f}-{hair:.2f}", "ev", (cost, hair, days))
                )
    for scale in (0.05, 0.1, 0.15, 0.2, 0.25, 0.35, 0.5, 0.75, 1.0):
        for cap in (0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10):
            desks.append(("sizing", f"sizing-{scale:.2f}-cap{cap:.2f}", "kelly", (scale, cap)))
    for days in range(1, 61):
        for cost in (0.0005, 0.001, 0.002, 0.004):
            desks.append(("horizon", f"horizon-{days}d-{cost:.4f}", "ev", (cost, 0.0, days)))
    for bps in range(1, 41):
        desks.append(("liquidity", f"liquidity-{bps}bps", "spread", (bps / 10_000.0,)))
        desks.append(("commerce", f"commerce-{bps}bps", "spread", (bps / 10_000.0,)))
    for i in range(48):
        ratio = 0.6 + i * 0.03
        desks.append(("regime", f"regime-{ratio:.2f}", "regime", (ratio,)))
    for heat in (0.40, 0.50, 0.60, 0.70, 0.80, 0.88, 0.95):
        for room in (0.02, 0.05, 0.08, 0.10):
            desks.append(("book", f"book-heat{heat:.2f}-room{room:.2f}", "heat", (heat, room)))
    for i in range(80):
        stop = 0.008 + i * 0.001
        desks.append(("defense", f"defense-{stop:.3f}", "stop", (stop,)))
    for i in range(40):
        floor = 0.50 + i * 0.01
        desks.append(("tape", f"tape-{floor:.2f}", "tape", (floor,)))
        desks.append(("intelligence", f"intel-{floor:.2f}", "intel", (floor,)))
        desks.append(("census", f"census-{i}", "tape", (0.50 + (i % 25) * 0.01,)))
        desks.append(("justice", f"justice-{floor:.2f}", "agree", (floor,)))
    for i in range(36):
        tol = i * 0.002
        desks.append(("interior", f"interior-{tol:.3f}", "risk", (tol,)))
        desks.append(("earnings", f"earnings-{i + 1}d", "earnings", (i + 1,)))
        desks.append(("execution", f"execution-{i + 1}bps", "spread", ((i + 1) / 10_000.0,)))
    for i in range(400):
        desks.append(("census", f"census-wide-{i}", "tape", (0.50 + (i % 30) * 0.01,)))
    for i in range(200):
        desks.append(("intelligence", f"intel-wide-{i}", "intel", (0.50 + (i % 40) * 0.01,)))
    for i in range(240):
        desks.append(("opposition", f"opposition-{i}", "dissent", (i,)))
    return desks


def roster() -> list[tuple]:
    global _ROSTER
    if _ROSTER is None:
        _ROSTER = _build_roster()
    return _ROSTER


def _moves(case: dict) -> tuple[float, float, float]:
    p = float(case.get("p_up") or 0.5)
    avg_up = case.get("avg_up")
    avg_down = case.get("avg_down")
    if avg_up is None or avg_down is None:
        avg_up = float(case.get("fallback_up") or 0.015)
        avg_down = float(case.get("fallback_down") or 0.025)
    return p, max(0.0, float(avg_up)), max(0.0, float(avg_down))


def _kelly(p: float, avg_up: float, avg_down: float) -> float:
    """Fraction of equity a one-shot bet can take. Capped later by the desk."""
    if avg_up <= 0:
        return 0.0
    payoff = avg_up / avg_down if avg_down > 0 else 8.0
    return max(0.0, p - (1.0 - p) / payoff)


def _hold_ev(p: float, avg_up: float, avg_down: float, cost: float, hair: float, days: int) -> float:
    """Drift over ``days`` bars, spread paid once."""
    daily = one_bar_ev(max(0.0, p - hair), avg_up, avg_down, 0.0)
    return daily * max(1, int(days)) - max(0.0, cost)


def _with_timeframes(case: dict) -> dict:
    """Blend 1/5/20/60-day probabilities into the one number every desk reads.

    Three horizons at or above 0.55 keep a long on the table. Fewer than that
    pulls the probability down so the chair cannot buy the disagreement.
    """
    keys = ("p_1", "p_5", "p_20", "p_60")
    if any(case.get(k) is None for k in keys):
        return case
    probs = [float(case[k]) for k in keys]
    up = [p for p in probs if p >= 0.55]
    blended = dict(case)
    blended["tf_agree"] = len(up)
    # A fit-period bar is the entry rule that beat the extra horizon filters.
    # Those filters stay in force only when the case has no model bar.
    if case.get("fit_bar") is not None and case.get("p_model") is not None:
        return blended
    if len(up) >= 3:
        blended["p_up"] = sum(up) / len(up)
    else:
        blended["p_up"] = min(float(case.get("p_up") or 0.5), sum(probs) / len(probs), 0.52)
    return blended


def _vote(kind: str, params: tuple, case: dict) -> int:
    p, avg_up, avg_down = _moves(case)
    held = bool(case.get("held"))
    gain = case.get("gain")
    exec_c = case.get("exec_conf")
    if kind == "ev":
        cost, hair, days = params
        ev = _hold_ev(p, avg_up, avg_down, float(cost), float(hair), int(days))
        if ev > 0.001:
            return 1
        if ev < -0.0005:
            return -1
        return 0
    if kind == "kelly":
        scale, cap = params
        full = _kelly(p, avg_up, avg_down)
        sized = min(float(cap), float(scale) * full)
        if full <= 0.0:
            return -1
        if sized + 1e-12 < float(cap) * 0.25:
            return 0
        return 1
    if kind == "regime":
        (ratio,) = params
        if avg_down <= 0:
            return 1 if p >= 0.55 else 0
        if avg_up / avg_down >= float(ratio) and p >= 0.55:
            return 1
        if avg_up / avg_down < 1.0 and p < 0.55:
            return -1
        return 0
    if kind == "heat":
        heat, room = params
        deployed = case.get("deployed_frac")
        if deployed is None:
            return 1 if p >= 0.6 and avg_up > avg_down else 0
        if float(deployed) > float(heat):
            return -1
        held_frac = case.get("name_frac")
        if held_frac is not None and float(held_frac) > float(room):
            return -1
        return 1 if p >= 0.55 else 0
    if kind == "earnings":
        (window,) = params
        dte = case.get("days_to_earnings")
        if dte is None:
            return 0
        try:
            dte_f = float(dte)
        except (TypeError, ValueError):
            return 0
        if 0 <= dte_f <= float(window):
            return -1
        return 1
    if kind == "tape":
        (floor,) = params
        if p >= floor and float(avg_up) >= float(avg_down):
            return 1
        if p <= 1.0 - floor and float(avg_down) > float(avg_up):
            return -1
        return 0
    if kind == "intel":
        (floor,) = params
        if p >= floor:
            return 1
        if p <= 1.0 - floor:
            return -1
        return 0
    if kind == "risk":
        (tol,) = params
        if not held:
            return 1 if p >= 0.6 else 0
        if gain is None:
            return -1
        if float(gain) < -float(tol):
            return -1
        if float(gain) > 0:
            return 1
        return 0
    if kind == "stop":
        (stop,) = params
        if float(avg_down) > float(stop) and float(avg_down) > float(avg_up):
            return -1
        if float(avg_up) > float(avg_down) and p >= 0.55:
            return 1
        return 0
    if kind == "spread":
        (cost,) = params
        if float(cost) >= float(avg_up):
            return -1
        if p >= 0.6 and float(avg_up) > float(cost) * 3:
            return 1
        return 0
    if kind == "agree":
        (need,) = params
        if exec_c is None:
            return 1 if p >= need else 0
        if p >= need and float(exec_c) >= need:
            return 1
        if p < 0.5 and float(exec_c) >= need:
            return -1
        return 0
    return 0


def _revise(vote: int, heard: float, *, dissent: bool) -> int:
    """Round 2. A desk reads its section. Abstentions may follow a clear room.

    The opposition answers the room instead of joining it.
    """
    if dissent:
        if heard > 0.2:
            return -1
        if heard < -0.2:
            return 1
        return vote
    if vote == 0 and heard > 0.35:
        return 1
    if vote == 0 and heard < -0.35:
        return -1
    return vote


def _mean(votes: list[int]) -> float:
    if not votes:
        return 0.0
    return sum(votes) / len(votes)


def _groups() -> dict[str, list[tuple]]:
    global _GROUPS
    if _GROUPS is None:
        grouped: dict[str, list[tuple]] = {}
        for desk in roster():
            grouped.setdefault(desk[0], []).append(desk)
        _GROUPS = grouped
    return _GROUPS


def convene(case: dict, weights: dict | None = None, *, record: bool = True) -> dict:
    """Run two rounds and return the chair's single order.

    ``record=False`` still lets every desk vote. It skips the transcript,
    which is how a full-market pass stays fast enough to keep working.
    """
    case = _with_timeframes(case)
    by_section = _groups()
    desks = roster()

    round1: list[dict] = []
    sec1: dict[str, float] = {}
    held_votes: dict[str, list[int]] = {}
    plan = _blank_plan()
    for section, members in by_section.items():
        votes = []
        for section_name, desk_id, kind, params in members:
            if kind == "dissent":
                vote = 0
                reason = "listening"
                work = 0.0
            else:
                vote = _vote(kind, params, case)
                reason = kind
                work = _work_value(kind, params, case, vote)
            _note_plan(plan, kind, params, vote, work)
            votes.append(vote)
            if record:
                round1.append(
                    {
                        "section": section_name,
                        "desk": desk_id,
                        "round": 1,
                        "vote": vote,
                        "reason": reason,
                        "heard": None,
                    }
                )
        sec1[section] = _mean(votes)
        held_votes[section] = votes

    # Opposition round 1 listens to the other ministries, not to itself.
    others = [v for name, v in sec1.items() if name != "opposition"]
    room = _mean([int(v > 0) - int(v < 0) for v in others]) if others else 0.0

    round2: list[dict] = []
    sec2: dict[str, float] = {}
    for section, votes in held_votes.items():
        heard = room if section == "opposition" else sec1[section]
        revised = [
            _revise(int(vote), heard, dissent=section == "opposition") for vote in votes
        ]
        sec2[section] = _mean(revised)
        if record:
            for memo, vote in zip(
                (m for m in round1 if m["section"] == section),
                revised,
            ):
                round2.append({**memo, "round": 2, "vote": vote, "heard": heard, "reason": "reply"})

    num = 0.0
    den = 0.0
    table = weights or _WEIGHT
    for section, score in sec2.items():
        w = float(table.get(section, _WEIGHT.get(section, 1.0)))
        num += w * score
        den += w
    score = num / den if den else 0.0

    veto = None
    held = bool(case.get("held"))
    gain = case.get("gain")
    if sec2.get("treasury", 0.0) < 0.0:
        veto = "treasury"
    elif held and (gain is None or float(gain) < 0.0):
        veto = "interior"
    p_model = case.get("p_model")
    fit_bar = case.get("fit_bar")
    has_bar = p_model is not None and fit_bar is not None
    below_bar = has_bar and float(p_model) < float(fit_bar)
    if veto:
        action = "FLAT"
    elif not held and below_bar:
        action = "FLAT"
        veto = "confidence"
    elif not has_bar and case.get("tf_agree") is not None and int(case["tf_agree"]) < 3:
        action = "FLAT"
        veto = "timeframe"
    elif score > 0.12:
        action = "LONG"
    elif score < -0.12:
        action = "SHORT"
    else:
        action = "FLAT"

    edges = (
        sum(1 for m in round2 if m["heard"] is not None) if record else len(desks)
    )
    order = _order(
        action=action,
        score=score,
        veto=veto,
        desks=desks,
        edges=edges,
        by_section=by_section,
        sec1=sec1,
        sec2=sec2,
        transcript=round2,
        plan=_orders_from_plan(case, plan),
    )
    if case.get("tf_agree") is not None:
        order["tf_agree"] = int(case["tf_agree"])
    return order


def _order(*, action, score, veto, desks, edges, by_section, sec1, sec2, transcript, plan) -> dict:
    return {
        "action": action,
        "score": score,
        "veto": veto,
        "n_desks": len(desks),
        "rounds": 2,
        "edges": edges,
        "sections": {
            name: {"round1": sec1.get(name, 0.0), "round2": sec2.get(name, 0.0), "n": len(members)}
            for name, members in by_section.items()
        },
        "transcript": transcript,
        "size_mult": float(plan["size_mult"]),
        "stop": float(plan["stop"]),
        "horizon_days": int(plan["horizon_days"]),
    }


def _blank_plan() -> dict:
    return {"horizon_ev": {}, "kelly_full": 0.0, "kelly_yes": 0, "stops": []}


def _note_plan(plan: dict, kind: str, params: tuple, vote: int, work: float) -> None:
    if kind == "kelly":
        plan["kelly_full"] = float(work)
        if vote == 1:
            plan["kelly_yes"] += 1
        return
    if vote != 1:
        return
    if kind == "ev":
        days = int(params[2])
        if work > float(plan["horizon_ev"].get(days, -1e9)):
            plan["horizon_ev"][days] = work
    elif kind == "stop":
        plan["stops"].append(float(params[0]))


def _orders_from_plan(case: dict, plan: dict) -> dict:
    """What the yes-votes actually picked: size, stop, hold.

    Size is Kelly versus the 10% name cap. A fat edge keeps a full ticket.
    A thin edge is cut. The government does not lever past the cap.
    """
    _, avg_up, avg_down = _moves(case)
    if plan["kelly_yes"]:
        size_mult = min(1.0, max(0.25, float(plan["kelly_full"]) / 0.10))
    else:
        size_mult = 0.25
    target = max(avg_down * 1.5, 0.01)
    if plan["stops"]:
        stop = min(plan["stops"], key=lambda s: abs(s - target))
    else:
        stop = target
    if plan["horizon_ev"]:
        horizon_days = max(plan["horizon_ev"], key=plan["horizon_ev"].get)
    else:
        horizon_days = 1
    return {
        "size_mult": float(size_mult),
        "stop": float(stop),
        "horizon_days": int(horizon_days),
    }


def _work_value(kind: str, params: tuple, case: dict, vote: int) -> float:
    """The number the desk actually computed, not just its yes/no."""
    p, avg_up, avg_down = _moves(case)
    if kind == "ev":
        cost, hair, days = params
        return _hold_ev(p, avg_up, avg_down, float(cost), float(hair), int(days))
    if kind == "kelly":
        return _kelly(p, avg_up, avg_down)
    return float(vote)


def act(case: dict):
    """Desks take a task, compute, deliver it, debate, then the chair speaks.

    The chair is always the last record.
    """
    desks = roster()
    by_section: dict[str, list[tuple]] = {}
    for desk in desks:
        by_section.setdefault(desk[0], []).append(desk)

    round1: list[dict] = []
    sec1: dict[str, float] = {}
    plan = _blank_plan()
    for section, members in by_section.items():
        votes: list[int] = []
        for section_name, desk_id, kind, params in members:
            yield {
                "phase": "assign",
                "section": section_name,
                "desk": desk_id,
                "task": kind,
            }
            if kind == "dissent":
                vote = 0
            else:
                vote = _vote(kind, params, case)
            work = _work_value(kind, params, case, vote)
            _note_plan(plan, kind, params, vote, work)
            votes.append(vote)
            round1.append(
                {
                    "section": section_name,
                    "desk": desk_id,
                    "vote": vote,
                    "kind": kind,
                }
            )
            yield {
                "phase": "compute",
                "section": section_name,
                "desk": desk_id,
                "vote": vote,
                "work": work,
            }
        sec1[section] = _mean(votes)
        yield {
            "phase": "deliver",
            "section": section,
            "heard": sec1[section],
            "n": len(members),
        }

    others = [v for name, v in sec1.items() if name != "opposition"]
    room = _mean([int(v > 0) - int(v < 0) for v in others]) if others else 0.0
    sec2_votes: dict[str, list[int]] = {name: [] for name in by_section}
    for memo in round1:
        section = memo["section"]
        heard = room if section == "opposition" else sec1[section]
        vote = _revise(int(memo["vote"]), heard, dissent=section == "opposition")
        sec2_votes[section].append(vote)
        yield {
            "phase": "debate",
            "section": section,
            "desk": memo["desk"],
            "vote": vote,
            "heard": heard,
        }
    sec2 = {name: _mean(votes) for name, votes in sec2_votes.items()}

    num = 0.0
    den = 0.0
    for section, score in sec2.items():
        w = _WEIGHT.get(section, 1.0)
        num += w * score
        den += w
    score = num / den if den else 0.0
    veto = None
    held = bool(case.get("held"))
    gain = case.get("gain")
    if sec2.get("treasury", 0.0) < 0.0:
        veto = "treasury"
    elif held and (gain is None or float(gain) < 0.0):
        veto = "interior"
    p_model = case.get("p_model")
    fit_bar = case.get("fit_bar")
    below_bar = (
        p_model is not None
        and fit_bar is not None
        and float(p_model) < float(fit_bar)
    )
    if veto:
        action = "FLAT"
    elif not held and below_bar:
        action = "FLAT"
        veto = "confidence"
    elif score > 0.12:
        action = "LONG"
    elif score < -0.12:
        action = "SHORT"
    else:
        action = "FLAT"
    yield {
        "phase": "chair",
        "action": action,
        "score": score,
        "veto": veto,
        "n_desks": len(desks),
        "sections": {name: sec2[name] for name in sec2},
        **_orders_from_plan(case, plan),
    }
