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
    "treasury": 1.4,
    "interior": 1.2,
    "defense": 1.1,
    "commerce": 1.0,
    "tape": 1.0,
    "intelligence": 1.0,
    "justice": 0.8,
    "census": 0.9,
    "opposition": 0.45,
}


def roster() -> list[tuple]:
    """One row per desk: (section, desk_id, kind, params)."""
    desks: list[tuple] = []
    costs = (0.0004, 0.0008, 0.001, 0.0015, 0.002, 0.003, 0.004, 0.006, 0.008, 0.01)
    hairs = (0.0, 0.02, 0.04, 0.06, 0.08, 0.10)
    for cost in costs:
        for hair in hairs:
            desks.append(("treasury", f"treasury-{cost:.4f}-{hair:.2f}", "ev", (cost, hair)))
    for floor in (0.52, 0.54, 0.55, 0.57, 0.58, 0.60, 0.62, 0.65, 0.68, 0.70, 0.72, 0.75):
        desks.append(("tape", f"tape-{floor:.2f}", "tape", (floor,)))
        desks.append(("intelligence", f"intel-{floor:.2f}", "intel", (floor,)))
    for tol in (0.0, 0.005, 0.01, 0.015, 0.02, 0.03, 0.04, 0.05):
        desks.append(("interior", f"interior-{tol:.3f}", "risk", (tol,)))
        desks.append(("defense", f"defense-{tol:.3f}", "stop", (max(tol, 0.01),)))
        desks.append(("commerce", f"commerce-{tol:.3f}", "spread", (max(tol, 0.0005),)))
        desks.append(("justice", f"justice-{tol:.3f}", "agree", (0.5 + tol,)))
    for k in range(40):
        desks.append(("census", f"census-{k}", "tape", (0.50 + (k % 20) * 0.01,)))
    for k in range(30):
        desks.append(("defense", f"defense-wide-{k}", "stop", (0.008 + k * 0.001,)))
    for i in range(24):
        desks.append(("opposition", f"opposition-{i}", "dissent", (i,)))
    return desks


def _vote(kind: str, params: tuple, case: dict) -> int:
    p = float(case.get("p_up") or 0.5)
    avg_up = case.get("avg_up")
    avg_down = case.get("avg_down")
    if avg_up is None or avg_down is None:
        avg_up = float(case.get("fallback_up") or 0.015)
        avg_down = float(case.get("fallback_down") or 0.025)
    held = bool(case.get("held"))
    gain = case.get("gain")
    exec_c = case.get("exec_conf")
    if kind == "ev":
        cost, hair = params
        ev = one_bar_ev(max(0.0, p - hair), float(avg_up), float(avg_down), float(cost))
        if ev > 0.001:
            return 1
        if ev < -0.0005:
            return -1
        return 0
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


def convene(case: dict) -> dict:
    """Run two rounds and return the chair's single order."""
    desks = roster()
    by_section: dict[str, list[tuple]] = {}
    for desk in desks:
        by_section.setdefault(desk[0], []).append(desk)

    round1: list[dict] = []
    sec1: dict[str, float] = {}
    for section, members in by_section.items():
        votes = []
        for section_name, desk_id, kind, params in members:
            if kind == "dissent":
                vote = 0
                reason = "listening"
            else:
                vote = _vote(kind, params, case)
                reason = kind
            votes.append(vote)
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

    # Opposition round 1 listens to the other ministries, not to itself.
    others = [v for name, v in sec1.items() if name != "opposition"]
    room = _mean([int(v > 0) - int(v < 0) for v in others]) if others else 0.0

    round2: list[dict] = []
    sec2: dict[str, float] = {}
    for memo in round1:
        section = memo["section"]
        heard = room if section == "opposition" else sec1[section]
        vote = _revise(int(memo["vote"]), heard, dissent=section == "opposition")
        round2.append({**memo, "round": 2, "vote": vote, "heard": heard, "reason": "reply"})
    for section in by_section:
        sec2[section] = _mean([m["vote"] for m in round2 if m["section"] == section])

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
    if veto:
        action = "FLAT"
    elif score > 0.12:
        action = "LONG"
    elif score < -0.12:
        action = "SHORT"
    else:
        action = "FLAT"

    edges = sum(1 for m in round2 if m["heard"] is not None)
    return _order(
        action=action,
        score=score,
        veto=veto,
        desks=desks,
        edges=edges,
        by_section=by_section,
        sec1=sec1,
        sec2=sec2,
        transcript=round2,
    )


def _order(*, action, score, veto, desks, edges, by_section, sec1, sec2, transcript) -> dict:
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
    }


def _work_value(kind: str, params: tuple, case: dict, vote: int) -> float:
    """The number the desk actually computed, not just its yes/no."""
    if kind != "ev":
        return float(vote)
    cost, hair = params
    p = float(case.get("p_up") or 0.5)
    avg_up = case.get("avg_up")
    avg_down = case.get("avg_down")
    if avg_up is None or avg_down is None:
        avg_up = float(case.get("fallback_up") or 0.015)
        avg_down = float(case.get("fallback_down") or 0.025)
    return one_bar_ev(max(0.0, p - float(hair)), float(avg_up), float(avg_down), float(cost))


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
    if veto:
        action = "FLAT"
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
    }
