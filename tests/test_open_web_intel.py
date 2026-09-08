from intel.open_web_intel import open_web_intel_for


def test_open_web_intel_uses_mocks(monkeypatch):
    monkeypatch.setenv("OPEN_WEB_INTEL_ENABLED", "true")
    monkeypatch.setattr(
        "intel.open_web_intel.fetch_wikipedia",
        lambda _s: {"ok": True, "extract": "Silver is a metal.", "sentiment": 0.1, "description": "", "url": "", "title": "Silver"},
    )
    monkeypatch.setattr(
        "intel.open_web_intel.fetch_yahoo_analysts",
        lambda _s: {"ok": True, "score": 0.4, "strong_buy": 8, "buy": 4, "hold": 2, "sell": 0, "strong_sell": 0},
    )
    monkeypatch.setattr(
        "intel.open_web_intel.fetch_sec_filings",
        lambda _s, **_k: {"ok": True, "cik": "0001", "filings": [], "form4_count": 1, "eightk_count": 0},
    )
    monkeypatch.setattr("intel.open_web_intel.fetch_ddg_company", lambda _s: "")
    monkeypatch.setattr("intel.open_web_intel._CACHE", {}, raising=False)
    from intel import open_web_intel as m

    m._CACHE.clear()
    monkeypatch.setattr(
        "intel.google_news_feed.symbol_news_headlines",
        lambda *_a, **_k: ["Silver ETF inflows rise"],
        raising=False,
    )
    monkeypatch.setattr("news_reader.fetch_news", lambda *_a, **_k: [])
    doc = open_web_intel_for("SLV", force_refresh=True)
    assert doc["analysts"]["ok"] is True
    assert "wikipedia" in doc["sources"]
    assert doc["boost"] > 0
