"""Tests for search.base. Spec §8.1.1."""
from __future__ import annotations

import pytest

from config import MusicSource, SearchResult
from search.base import BaseMusicSearcher


class _FailingSearcher(BaseMusicSearcher):
    source = MusicSource.FREEMIDI

    async def _do_search(self, query: str, limit: int) -> list[SearchResult]:
        raise RuntimeError("boom")

    async def get_download_url(self, result: SearchResult) -> str:
        raise NotImplementedError


class _OkSearcher(BaseMusicSearcher):
    source = MusicSource.BITMIDI

    async def _do_search(self, query: str, limit: int) -> list[SearchResult]:
        return [
            SearchResult(
                id=f"{self.source.value}_x",
                title="X",
                source=self.source,
                source_url="https://example.com/x",
                score=0.5,
            )
        ]

    async def get_download_url(self, result: SearchResult) -> str:
        return "https://example.com/x.mid"


async def test_search_swallows_exceptions_returns_empty():
    s = _FailingSearcher()
    assert await s.search("foo", limit=5) == []


async def test_search_returns_results_on_success():
    s = _OkSearcher()
    results = await s.search("foo", limit=5)
    assert len(results) == 1
    assert results[0].title == "X"
