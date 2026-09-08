from self_modify.gainz_legal_net import filter_urls, url_allowed


def test_public_gainzalgo_oss_allowed():
    ok, reason = url_allowed(
        "https://www.tradingview.com/script/HKBMUhq3-Smart-Money-Structure-GainzAlgo/"
    )
    assert ok, reason


def test_invite_only_and_dumps_blocked():
    assert url_allowed("https://gist.github.com/someone/gainzalgo-v2")[0] is False
    assert url_allowed("https://t.me/cracked")[0] is False
    assert url_allowed("https://pastebin.com/raw/abc")[0] is False
    assert url_allowed("http://www.tradingview.com/script/HKBMUhq3-Smart-Money-Structure-GainzAlgo/")[0] is False


def test_other_tradingview_scripts_blocked():
    ok, reason = url_allowed("https://www.tradingview.com/script/not-the-oss-one/")
    assert ok is False
    assert "tv_not_oss" in reason


def test_filter_urls_splits():
    ok, blocked = filter_urls(
        [
            "https://www.tradingview.com/script/HKBMUhq3-Smart-Money-Structure-GainzAlgo/",
            "https://gist.github.com/leak",
        ]
    )
    assert len(ok) == 1
    assert len(blocked) == 1
