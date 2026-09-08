import time

from intel import http_scheduler as hs


def test_wait_host_paces(monkeypatch):
    monkeypatch.setenv("HTTP_RPS_EXAMPLE_COM", "20")
    hs._last.clear()
    hs._cool.clear()
    t0 = time.perf_counter()
    assert hs.wait_host("example.com", block=True)
    assert hs.wait_host("example.com", block=True)
    assert time.perf_counter() - t0 >= 0.04


def test_note_limited_cools(monkeypatch):
    hs._cool.clear()
    hs.note_limited("api.example", seconds=30)
    assert hs.is_cooling("api.example")


def test_cache_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(hs, "CACHE_DIR", tmp_path)
    hs.cache_set("https://x.test/a", {"ok": 1}, ttl_sec=60)
    assert hs.cache_get("https://x.test/a", ttl_sec=60) == {"ok": 1}
