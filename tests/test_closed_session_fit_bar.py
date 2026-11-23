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


def test_paper_launcher_comes_back_with_take_profit_off_and_eight_percent_stops():
    text = (Path(__file__).resolve().parents[1] / "run_all.sh").read_text()
    body = text.split("launch_fortress_alpaca_paper()", 1)[1].split("launch_weekly_paper_daemon()", 1)[0]
    assert 'export ALPACA_BASE_URL="https://paper-api.alpaca.markets"' in body
    assert "export FORTRESS_TAKE_PROFIT_PCT=0" in body
    assert "export FORTRESS_STOP_LOSS_PCT=0.08" in body
    assert "export FORTRESS_HARD_STOP_PCT=0.08" in body
    assert "export LIQUIDATE_MIN_LOSS_PCT=0.08" in body
    assert "export FORTRESS_SCALE_OUT_ENABLED=false" in body
    assert "export FORTRESS_ROTATE_ON_PROFIT=false" in body
    assert "export HFT_EXIT_ON_GREEN=false" in body
    assert "export HFT_SOFT_GREEN_EXIT=false" in body
    assert "FORTRESS_TAKE_PROFIT_PCT:-0.08" not in body
    hft = text.split("launch_subsecond_alpaca_paper()", 1)[1].split("launch_fortress_alpaca_paper()", 1)[0]
    assert 'HFT_EXIT_ON_GREEN="${HFT_EXIT_ON_GREEN:-false}"' in hft
    assert 'HFT_SOFT_GREEN_EXIT="${HFT_SOFT_GREEN_EXIT:-false}"' in hft
    assert 'HFT_EXIT_ON_GREEN="${HFT_EXIT_ON_GREEN:-true}"' not in hft
