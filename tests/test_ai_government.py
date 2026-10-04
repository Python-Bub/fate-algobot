"""Desks brief each other. The chair is the only order."""

from analytics.ai_government import convene, roster


def test_hundreds_of_desks_each_speak_twice():
    desks = roster()
    assert len(desks) >= 200
    sections = {d[0] for d in desks}
    assert sections >= {
        "treasury",
        "interior",
        "defense",
        "commerce",
        "tape",
        "intelligence",
        "justice",
        "census",
        "opposition",
    }
    order = convene({"p_up": 0.8, "avg_up": 0.02, "avg_down": 0.005, "exec_conf": 0.8})
    assert order["n_desks"] == len(desks)
    assert order["rounds"] == 2
    assert len(order["transcript"]) == len(desks)
    assert order["edges"] == len(desks)


def test_round_two_is_a_reply_to_the_room():
    order = convene({"p_up": 0.8, "avg_up": 0.02, "avg_down": 0.005, "exec_conf": 0.8})
    replies = [m for m in order["transcript"] if m["round"] == 2]
    assert replies
    assert all(m["heard"] is not None and m["reason"] == "reply" for m in replies)
    opp = [m for m in replies if m["section"] == "opposition"]
    assert opp and all(m["vote"] == -1 for m in opp)
    assert order["action"] == "LONG"
    assert order["veto"] is None


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
    assert len(computes) >= 200
    assert len(delivers) == 9
    assert len(debates) == len(computes)
    assert all("work" in s for s in computes)
    assert any(isinstance(s["work"], float) and s["work"] != 0 for s in computes)


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
