import time

from intel.llm_cooldown import active, remaining, retry_after_seconds, trip


def test_trip_and_remaining(tmp_path, monkeypatch):
    import intel.llm_cooldown as lc

    monkeypatch.setattr(lc, "PATH", tmp_path / "cd.json")
    monkeypatch.setattr(lc, "LEGACY", tmp_path / "cd.ts")
    assert active() is False
    trip(30, reason="test")
    assert remaining() > 20
    assert active() is True


def test_retry_after_header():
    assert retry_after_seconds({"Retry-After": "45"}, default=120) == 45.0
    assert retry_after_seconds({}, default=120) == 120.0
