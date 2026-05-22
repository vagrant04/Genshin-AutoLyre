"""bitmidi.com searcher (JSON API first, HTML fallback).

Spec §8.1.3.
"""
from __future__ import annotations

import hashlib
import re

import httpx

from config import MusicSource, SearchResult
from search.base import BaseMusicSearcher


class BitMidiSearcher(BaseMusicSearcher):
    source = MusicSource.BITMIDI

    def __init__(self, *, client: httpx.AsyncClient | None = None) -> None:
        self._client = client
        self._owns_client = client is None

    async def _do_search(self, query: str, limit: int) -> list[SearchResult]:
        url = f"https://bitmidi.com/search?q={query.replace(' ', '+')}"
        client = self._client or httpx.AsyncClient(timeout=10.0)
        try:
            response = await client.get(url, headers={"Accept": "application/json"})
            if response.status_code != 200:
                raise RuntimeError(f"HTTP {response.status_code}")
            try:
                data = response.json()
            except ValueError as exc:
                raise RuntimeError("Invalid JSON from bitmidi") from exc
            results: list[SearchResult] = []
            for entry in data.get("results", [])[:limit]:
                slug = entry.get("slug")
                title = entry.get("name") or slug or "Untitled"
                download_url = entry.get("downloadUrl") or (
                    f"https://bitmidi.com/uploads/{slug}.mid" if slug else None
                )
                file_size_bytes = entry.get("fileSize")
                results.append(
                    SearchResult(
                        id=f"bitmidi_{hashlib.sha1((slug or title).encode()).hexdigest()[:6]}",
                        title=title,
                        source=self.source,
                        source_url=f"https://bitmidi.com/{slug}" if slug else url,
                        download_url=download_url,
                        file_size_kb=(
                            int(round(file_size_bytes / 1024))
                            if file_size_bytes else None
                        ),
                        score=0.7,
                    )
                )
            return results
        finally:
            if self._owns_client:
                await client.aclose()

    async def get_download_url(self, result: SearchResult) -> str:
        if not result.download_url:
            raise ValueError("BitMIDI result has no download URL")
        return result.download_url
