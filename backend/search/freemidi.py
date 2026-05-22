"""freemidi.org searcher.

Spec §8.1.2:
  - URL: https://freemidi.org/search-{query}, spaces → hyphens
  - Parse search-result anchors with /download-{id}
  - Download URL: https://freemidi.org/download2-{id}
"""
from __future__ import annotations

import hashlib
import re

import httpx
from bs4 import BeautifulSoup

from config import MusicSource, SearchResult
from search.base import BaseMusicSearcher

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
_DOWNLOAD_ID_RE = re.compile(r"/download-(\d+)")


class FreeMidiSearcher(BaseMusicSearcher):
    source = MusicSource.FREEMIDI

    def __init__(self, *, client: httpx.AsyncClient | None = None) -> None:
        self._client = client
        self._owns_client = client is None

    async def _do_search(self, query: str, limit: int) -> list[SearchResult]:
        slug = re.sub(r"\s+", "-", query.strip())
        url = f"https://freemidi.org/search-{slug}"
        client = self._client or httpx.AsyncClient(timeout=10.0)
        try:
            response = await client.get(url, headers={"User-Agent": _USER_AGENT})
            if response.status_code != 200:
                raise RuntimeError(f"HTTP {response.status_code}")
            soup = BeautifulSoup(response.text, "lxml")
            results: list[SearchResult] = []
            for anchor in soup.select("a.search-result-anchor"):
                href = anchor.get("href", "")
                match = _DOWNLOAD_ID_RE.search(href)
                if not match:
                    continue
                fid = match.group(1)
                title = anchor.get_text(strip=True)
                results.append(
                    SearchResult(
                        id=f"freemidi_{hashlib.sha1(fid.encode()).hexdigest()[:6]}",
                        title=title,
                        source=self.source,
                        source_url=f"https://freemidi.org{href}",
                        download_url=f"https://freemidi.org/download2-{fid}",
                        score=0.7,
                    )
                )
                if len(results) >= limit:
                    break
            return results
        finally:
            if self._owns_client:
                await client.aclose()

    async def get_download_url(self, result: SearchResult) -> str:
        if not result.download_url:
            raise ValueError("FreeMidi result has no download URL")
        return result.download_url
