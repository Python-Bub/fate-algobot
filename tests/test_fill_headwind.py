"""Soft CapEx / 200d playbook blocks must not park idle cash during fill/fade."""

from intel.near_term_headwinds import blocks_playbook_buy


def test_soft_capex_blocked_when_flags_off(monkeypatch):
    monkeypatch.delenv("DOWNPRESS_SOFT_OK_WHEN_UNDERDEPLOY", raising=False)
    monkeypatch.delenv("FORTRESS_FILL_SKIP_SOFT_HEADWIND", raising=False)
    monkeypatch.delenv("FORTRESS_FADE_SKIP_SOFT_DOWNPRESS", raising=False)
    monkeypatch.setattr(
        "intel.algo_risk_filter.blocks_buy",
        lambda *_a, **_k: (False, ""),
    )
    monkeypatch.setattr(
        "intel.near_term_headwinds.assess_near_term_headwind",
        lambda *_a, **_k: {
            "block_playbook": True,
            "reasons": ["High AI CapEx ($125B–$145B) — near-term volatility"],
        },
    )
    blocked, _why = blocks_playbook_buy("META")
    assert blocked


def test_soft_capex_allowed_when_filling(monkeypatch):
    monkeypatch.setenv("FORTRESS_FILL_SKIP_SOFT_HEADWIND", "true")
    monkeypatch.setattr(
        "intel.algo_risk_filter.blocks_buy",
        lambda *_a, **_k: (False, ""),
    )
    monkeypatch.setattr(
        "intel.near_term_headwinds.assess_near_term_headwind",
        lambda *_a, **_k: {
            "block_playbook": True,
            "reasons": ["High AI CapEx ($125B–$145B) — near-term volatility"],
        },
    )
    blocked, _why = blocks_playbook_buy("META")
    assert not blocked


def test_earnings_today_still_blocks_when_filling(monkeypatch):
    monkeypatch.setenv("FORTRESS_FILL_SKIP_SOFT_HEADWIND", "true")
    monkeypatch.setattr(
        "intel.algo_risk_filter.blocks_buy",
        lambda *_a, **_k: (True, "earnings today — print window"),
    )
    blocked, why = blocks_playbook_buy("NVDA")
    assert blocked
    assert "earnings" in why[0].lower()
