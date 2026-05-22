"""Tests for search.aggregator. Spec §8.1.6."""
from __future__ import annotations

from typing import Sequence

import pytest

from config import MusicSource, SearchResult
from search.aggregator import aggregate_results, search_all


class _StubSearcher:
    def __init__(self, source: MusicSource, results: Sequence[SearchResult]):
        self.source = source
        self._results = list(results)

    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        return list(self._results)[:limit]


class _RaisingSearcher:
    source = MusicSource.MUSESCORE

    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        # search() should never propagate, but if a custom one does,
        # aggregator must still survive.
        raise RuntimeError("oops")


def _r(source: MusicSource, title: str, *, score: float = 0.5,
       download: str | None = "https://x/y.mid") -> SearchResult:
    return SearchResult(
        id=f"{source.value}_{title.lower().replace(' ', '_')}",
        title=title,
        source=source,
        source_url="https://x/page",
        download_url=download,
        score=score,
    )


async def test_search_all_combines_results_from_all_sources():
    a = _StubSearcher(MusicSource.FREEMIDI, [_r(MusicSource.FREEMIDI, "Tune 1")])
    b = _StubSearcher(MusicSource.BITMIDI, [_r(MusicSource.BITMIDI, "Tune 2")])
    results = await search_all([a, b], "twinkle", per_source_limit=5)
    assert len(results) == 2
    assert {r.source for r in results} == {MusicSource.FREEMIDI, MusicSource.BITMIDI}


async def test_search_all_swallows_searcher_exceptions():
    a = _StubSearcher(MusicSource.FREEMIDI, [_r(MusicSource.FREEMIDI, "Tune 1")])
    b = _RaisingSearcher()
    results = await search_all([a, b], "x", per_source_limit=5)
    assert len(results) == 1


def test_aggregate_dedupes_similar_titles_keeping_higher_score():
    a = _r(MusicSource.FREEMIDI, "Twinkle Twinkle Little Star", score=0.5)
    b = _r(MusicSource.BITMIDI, "Twinkle Twinkle Little Star", score=0.9)
    out = aggregate_results([a, b])
    assert len(out) == 1
    assert out[0].score == 0.9


def test_aggregate_orders_results_with_download_first():
    a = _r(MusicSource.MUSESCORE, "Has No Download", download=None, score=0.9)
    b = _r(MusicSource.FREEMIDI, "Has Download", score=0.5)
    out = aggregate_results([a, b])
    assert out[0].title == "Has Download"
    assert out[1].title == "Has No Download"


def test_aggregate_total_capped_at_20():
    items = [
        _r(MusicSource.FREEMIDI, f"Tune {i}", score=0.5)
        for i in range(30)
    ]
    out = aggregate_results(items)
    assert len(out) == 20


def test_aggregate_empty_input_returns_empty():
    assert aggregate_results([]) == []
