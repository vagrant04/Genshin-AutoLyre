"""bitmidi.com searcher.

The site exposes an internal JSON API at /api/midi/all?q=...&page=1.
Results contain `slug` (e.g. "coldplay-viva-la-vida-mid") and
`downloadUrl` (e.g. "/uploads/24946.mid"); the original spec's
/search?q= JSON endpoint is not real — that path serves HTML.

Implementation rewritten against actual API responses observed in
May 2026.
"""
from __future__ import annotations

import hashlib

import httpx

from config import MusicSource, SearchResult
from search.base import BaseMusicSearcher

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class BitMidiSearcher(BaseMusicSearcher):
    source = MusicSource.BITMIDI

    def __init__(self, *, client: httpx.AsyncClient | None = None) -> None:
        self._client = client
        self._owns_client = client is None

    async def _do_search(self, query: str, limit: int) -> list[SearchResult]:
        url = "https://bitmidi.com/api/midi/all"
        client = self._client or httpx.AsyncClient(timeout=10.0)
        try:
            response = await client.get(
                url,
                params={"q": query, "page": 1},
                headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
            )
            if response.status_code != 200:
                raise RuntimeError(f"HTTP {response.status_code}")
            try:
                data = response.json()
            except ValueError as exc:
                raise RuntimeError("Invalid JSON from bitmidi") from exc
            entries = (
                (data.get("result") or {}).get("results")
                or data.get("results")
                or []
            )
            results: list[SearchResult] = []
            for entry in entries[:limit]:
                slug = entry.get("slug")
                title = entry.get("name") or slug or "Untitled"
                relative_download = entry.get("downloadUrl")
                if relative_download:
                    download_url = (
                        relative_download
                        if relative_download.startswith("http")
                        else f"https://bitmidi.com{relative_download}"
                    )
                elif slug:
                    download_url = f"https://bitmidi.com/uploads/{slug}.mid"
                else:
                    download_url = None
                file_size_bytes = entry.get("fileSize")
                source_path = entry.get("url") or (f"/{slug}" if slug else "")
                results.append(
                    SearchResult(
                        id=f"bitmidi_{hashlib.sha1((slug or title).encode()).hexdigest()[:6]}",
                        title=title,
                        source=self.source,
                        source_url=(
                            f"https://bitmidi.com{source_path}"
                            if source_path else url
                        ),
                        download_url=download_url,
                        file_size_kb=(
                            int(round(file_size_bytes / 1024))
                            if file_size_bytes else None
                        ),
                        score=0.75,
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
