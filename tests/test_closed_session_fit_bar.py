"""A closed session must not spend cash at a fixed probability."""

from pathlib import Path


def test_closed_session_waits_for_the_fit_bar():
    text = (Path(__file__).resolve().parents[1] / "fortress_live.py").read_text()
    gate = text.split("FORTRESS_CLOSED_IDLE_PREFILL", 1)[1]
    body = gate.split("bench_closes", 1)[0]
    assert '"false"' in gate[:240]
    assert '"p_up": 0.58' in body
    assert "cash waits for names that clear the fit-period 95th" in text
    assert "closed session waits for the fit-period 95th" in text
    assert "below the fit-period 95th" in text
