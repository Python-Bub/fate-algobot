"""GCP paper is the only host that may POST Alpaca orders."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_observe_blocks_orders(monkeypatch):
    import order_role as orole

    monkeypatch.setenv("FATE_ORDER_ROLE", "observe")
    monkeypatch.setenv("HOSTNAME", "Demirs-MacBook-Pro.local")
    monkeypatch.setattr(orole, "hostname", lambda: "demirs-macbook-pro.local")
    assert orole.order_role() == "observe"
    assert orole.orders_allowed_here() is False


def test_paper_hostname_wins_over_observe_env(monkeypatch):
    import order_role as orole

    monkeypatch.setenv("FATE_ORDER_ROLE", "observe")
    monkeypatch.setattr(orole, "hostname", lambda: "fate-algobot-paper")
    assert orole.order_role() == "gcp-paper"
    assert orole.orders_allowed_here() is True


def test_trainer_never_orders(monkeypatch):
    import order_role as orole

    monkeypatch.setenv("FATE_ORDER_ROLE", "gcp-paper")
    monkeypatch.setattr(orole, "hostname", lambda: "fate-algobot-trainer")
    assert orole.order_role() == "train"
    assert orole.orders_allowed_here() is False


def test_mac_env_gcp_paper_still_observe(monkeypatch):
    import order_role as orole

    monkeypatch.setenv("FATE_ORDER_ROLE", "gcp-paper")
    monkeypatch.delenv("FATE_ALLOW_LOCAL_ORDERS", raising=False)
    monkeypatch.setattr(orole, "hostname", lambda: "demirs-macbook-pro.local")
    assert orole.order_role() == "observe"
    assert orole.orders_allowed_here() is False


def test_broker_and_hft_gate_on_role():
    broker = (ROOT / "alpaca_broker.py").read_text(encoding="utf-8")
    assert "_require_order_host" in broker
    assert "orders_allowed_here" in broker
    cfg = (ROOT / "hft/src/common/config.ts").read_text(encoding="utf-8")
    assert "_orderRoleDryRun" in cfg
    assert "algobot-paper" in cfg
    run = (ROOT / "run_all.sh").read_text(encoding="utf-8")
    assert "*algobot-paper*) export FATE_ORDER_ROLE=gcp-paper" in run
    assert "apply_fate_order_role" in run
