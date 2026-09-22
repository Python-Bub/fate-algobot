from news_reader import _item_text, fetch_news


def test_item_text_nested_content():
    title, summary = _item_text(
        {"content": {"title": "Apple beats", "summary": "iPhone sales"}}
    )
    assert title == "Apple beats"
    assert "iPhone" in summary


def test_item_text_legacy_title():
    title, summary = _item_text({"title": "Meta rally", "publisher": "Reuters"})
    assert title == "Meta rally"


def test_item_text_headline_alias():
    title, _ = _item_text({"headline": "NVDA guidance"})
    assert title == "NVDA guidance"


def test_fetch_news_normalizes_keys(monkeypatch):
    class _T:
        news = [
            {"content": {"title": "Hello", "summary": "World"}},
            {"title": ""},
        ]

    monkeypatch.setattr("news_reader.yf.Ticker", lambda _s: _T())
    rows = fetch_news("AAPL", limit=5)
    assert rows
    assert rows[0]["headline"] == "Hello"
    assert rows[0]["title"] == "Hello"
    assert rows[0]["summary"] == "World"
