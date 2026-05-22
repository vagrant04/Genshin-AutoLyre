"""musescore.com searcher (discovery only — no download_url).

MuseScore aggressively blocks non-browser traffic via Cloudflare. We
send realistic browser headers; if Cloudflare still 403s, base.search()
swallows the exception and the aggregator skips this source. The user
experience degrades gracefully.

If you want reliable MuseScore results in production, add a paid scraping
proxy or run a headless browser — both out of scope here.
"""
from __future__ import annotations

import hashlib
import json

import httpx
from bs4 import BeautifulSoup

from config import MusicSource, SearchResult
from search.base import BaseMusicSearcher

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_BROWSER_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}
_PREVIEW_NOTE = "请前往 MuseScore 手动下载 MIDI"


class MuseScoreSearcher(BaseMusicSearcher):
    source = MusicSource.MUSESCORE

    def __init__(self, *, client: httpx.AsyncClient | None = None) -> None:
        self._client = client
        self._owns_client = client is None

    async def _do_search(self, query: str, limit: int) -> list[SearchResult]:
        url = "https://musescore.com/sheetmusic"
        params = {"text": query, "instrument": "piano"}
        client = self._client or httpx.AsyncClient(timeout=10.0, follow_redirects=True)
        try:
            response = await client.get(url, params=params, headers=_BROWSER_HEADERS)
            if response.status_code != 200:
                raise RuntimeError(f"HTTP {response.status_code}")
            soup = BeautifulSoup(response.text, "lxml")
            jsonld_blocks = soup.find_all(
                "script", attrs={"type": "application/ld+json"}
            )
            results: list[SearchResult] = []
            for block in jsonld_blocks:
                try:
                    data = json.loads(block.string or "")
                except (TypeError, json.JSONDecodeError):
                    continue
                graph = data.get("@graph", []) if isinstance(data, dict) else []
                for entry in graph:
                    if not isinstance(entry, dict):
                        continue
                    if entry.get("@type") != "MusicComposition":
                        continue
                    title = entry.get("name") or "Untitled"
                    page_url = entry.get("url") or url
                    results.append(
                        SearchResult(
                            id=f"musescore_{hashlib.sha1(title.encode()).hexdigest()[:6]}",
                            title=title,
                            source=self.source,
                            source_url=page_url,
                            download_url=None,
                            preview_keys=_PREVIEW_NOTE,
                            score=0.5,
                        )
                    )
                    if len(results) >= limit:
                        return results
            return results
        finally:
            if self._owns_client:
                await client.aclose()

    async def get_download_url(self, result: SearchResult) -> str:
        raise ValueError("MuseScore does not expose direct MIDI downloads")
