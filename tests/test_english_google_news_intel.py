"""Tests for open English lexicon + Google News intel helpers."""

from __future__ import annotations

from intel.english_lexicon import expand_news_query, lexicon_polarity, synonyms


def test_lexicon_polarity_signs():
    assert lexicon_polarity("stock surge rally beat upgrade growth") > 0.2
    assert lexicon_polarity("plunge crash miss downgrade lawsuit fraud") < -0.2


def test_expand_query_includes_symbol():
    qs = expand_news_query("NVDA", "NVIDIA Corporation")
    assert any("NVDA" in q for q in qs)
    assert len(qs) >= 2


def test_synonyms_optional():
    # WordNet may or may not be downloaded in CI — just ensure no crash
    syns = synonyms("profit", limit=3)
    assert isinstance(syns, list)
