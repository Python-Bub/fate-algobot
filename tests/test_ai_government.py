"""Desks brief each other. The chair is the only order."""

from analytics.ai_government import convene, roster


def test_hundreds_of_desks_each_speak_twice():
    desks = roster()
    assert len(desks) >= 2500
    sections = {d[0] for d in desks}
    assert sections >= {
        "treasury",
        "sizing",
        "horizon",
        "liquidity",
        "regime",
        "book",
        "interior",
        "defense",
        "commerce",
        "tape",
        "intelligence",
        "execution",
        "earnings",
        "justice",
        "census",
        "opposition",
    }
    order = convene({"p_up": 0.8, "avg_up": 0.02, "avg_down": 0.005, "exec_conf": 0.8})
    assert order["n_desks"] == len(desks)
    assert order["rounds"] == 2
    assert len(order["transcript"]) == len(desks)
    assert order["edges"] == len(desks)


def test_quiet_convene_matches_the_chair():
    case = {"p_up": 0.78, "avg_up": 0.018, "avg_down": 0.006, "exec_conf": 0.74}
    full = convene(case)
    quiet = convene(case, record=False)
    assert quiet["action"] == full["action"]
    assert quiet["score"] == full["score"]
    assert quiet["size_mult"] == full["size_mult"]
    assert quiet["stop"] == full["stop"]
    assert quiet["horizon_days"] == full["horizon_days"]
    assert quiet["n_desks"] == full["n_desks"]
    assert quiet["edges"] == full["n_desks"]
    assert quiet["transcript"] == []


def test_round_two_is_a_reply_to_the_room():
    order = convene({"p_up": 0.8, "avg_up": 0.02, "avg_down": 0.005, "exec_conf": 0.8})
    replies = [m for m in order["transcript"] if m["round"] == 2]
    assert replies
    assert all(m["heard"] is not None and m["reason"] == "reply" for m in replies)
    opp = [m for m in replies if m["section"] == "opposition"]
    assert opp and all(m["vote"] == -1 for m in opp)
    assert order["action"] == "LONG"
    assert order["veto"] is None
    assert order["size_mult"] == 1.0
    assert order["horizon_days"] > 1
    assert order["stop"] > 0


def test_treasury_vetoes_a_ticket_that_does_not_pay():
    order = convene(
        {
            "p_up": 0.60,
            "avg_up": 0.002,
            "avg_down": 0.008,
            "exec_conf": 0.7,
        }
    )
    assert order["sections"]["treasury"]["round2"] < 0
    assert order["veto"] == "treasury"
    assert order["action"] == "FLAT"


def test_interior_vetoes_adding_to_a_red_hold():
    order = convene(
        {
            "p_up": 0.8,
            "avg_up": 0.02,
            "avg_down": 0.005,
            "exec_conf": 0.8,
            "held": True,
            "gain": -0.04,
        }
    )
    assert order["veto"] == "interior"
    assert order["action"] == "FLAT"


def test_desks_work_and_the_chair_speaks_last():
    from analytics.ai_government import act

    case = {"p_up": 0.78, "avg_up": 0.018, "avg_down": 0.006, "exec_conf": 0.74}
    steps = list(act(case))
    assert steps[0]["phase"] == "assign"
    assert steps[-1]["phase"] == "chair"
    assert steps[-1]["action"] == "LONG"
    computes = [s for s in steps if s["phase"] == "compute"]
    delivers = [s for s in steps if s["phase"] == "deliver"]
    debates = [s for s in steps if s["phase"] == "debate"]
    assert len(computes) >= 2500
    assert len(delivers) >= 15
    assert len(debates) == len(computes)
    assert steps[-1]["size_mult"] == 1.0
    assert steps[-1]["horizon_days"] > 1
    assert all("work" in s for s in computes)
    assert any(isinstance(s["work"], float) and s["work"] != 0 for s in computes)


def test_a_model_below_its_fit_bar_is_not_a_long():
    order = convene(
        {
            "p_up": 0.8,
            "avg_up": 0.02,
            "avg_down": 0.005,
            "exec_conf": 0.8,
            "p_model": 0.40,
            "fit_bar": 0.70,
        }
    )
    assert order["action"] == "FLAT"
    assert order["veto"] == "confidence"


def test_a_confident_model_is_not_flat_just_because_timeframes_split():
    order = convene(
        {
            "p_up": 0.8,
            "p_1": 0.80,
            "p_5": 0.42,
            "p_20": 0.42,
            "p_60": 0.42,
            "avg_up": 0.02,
            "avg_down": 0.005,
            "exec_conf": 0.8,
            "p_model": 0.80,
            "fit_bar": 0.55,
        },
        record=False,
    )
    assert order["action"] == "LONG"
    assert order["veto"] is None


def test_the_fit_bar_ignores_the_holdout_tail():
    from analytics.model_edge import fit_probability_bar

    fit = [float(i) for i in range(80)]
    bar = fit_probability_bar(fit + [1000.0] * 20, percentile=95)
    again = fit_probability_bar(fit + [0.0] * 20, percentile=95)
    assert bar == again
    assert bar < 100


def test_a_new_name_with_a_real_edge_is_a_long():
    order = convene(
        {
            "p_up": 0.78,
            "avg_up": 0.018,
            "avg_down": 0.006,
            "exec_conf": 0.74,
            "held": False,
            "gain": None,
        }
    )
    assert order["action"] == "LONG"
    assert order["score"] > 0.12
