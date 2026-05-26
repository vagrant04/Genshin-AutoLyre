"""Tests for /api/search route."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.routes_search import get_searchers
from config import MusicSource, SearchResult
from main import app


class _StubSearcher:
    def __init__(self, source: MusicSource):
        self.source = source

    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        return [
            SearchResult(
                id=f"{self.source.value}_x",
                title=f"{query} hit from {self.source.value}",
                source=self.source,
                source_url="https://example.com/x",
                download_url="https://example.com/x.mid",
                score=0.9,
            )
        ]


def _override_with_stub() -> list:
    return [_StubSearcher(MusicSource.FREEMIDI), _StubSearcher(MusicSource.BITMIDI)]


def test_search_returns_aggregated_results():
    app.dependency_overrides[get_searchers] = _override_with_stub
    try:
        client = TestClient(app)
        resp = client.get("/api/search", params={"q": "twinkle"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["query"] == "twinkle"
        assert body["total"] == 2
        assert len(body["results"]) == 2
    finally:
        app.dependency_overrides.pop(get_searchers, None)


def test_search_missing_q_returns_422():
    client = TestClient(app)
    resp = client.get("/api/search")
    assert resp.status_code == 422
