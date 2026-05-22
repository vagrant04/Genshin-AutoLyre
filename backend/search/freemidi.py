"""freemidi.org searcher.

URL: https://freemidi.org/search?q={query}
Result links use /download3-{id}-{slug}; the download is /getter-{id}.

The original spec described /search-{slug} and /download2-{id}, which no
longer match the live site (404). The implementation here was rewritten
against the actual HTML returned in May 2026.
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
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_DOWNLOAD3_RE = re.compile(r"/download3-(\d+)-([^/?#\s\"']+)")


def _slug_to_title(slug: str) -> str:
    """Turn a URL slug like 'twinkle-twinkle-lucky-stars-merle-haggard'
    into a readable title 'Twinkle Twinkle Lucky Stars Merle Haggard'."""
    return " ".join(part.capitalize() for part in slug.split("-") if part)


class FreeMidiSearcher(BaseMusicSearcher):
    source = MusicSource.FREEMIDI

    def __init__(self, *, client: httpx.AsyncClient | None = None) -> None:
        self._client = client
        self._owns_client = client is None

    async def _do_search(self, query: str, limit: int) -> list[SearchResult]:
        url = "https://freemidi.org/search"
        client = self._client or httpx.AsyncClient(timeout=10.0, follow_redirects=True)
        try:
            response = await client.get(
                url,
                params={"q": query.strip()},
                headers={"User-Agent": _USER_AGENT},
            )
            if response.status_code != 200:
                raise RuntimeError(f"HTTP {response.status_code}")
            soup = BeautifulSoup(response.text, "lxml")

            # Each result is an <a href="/download3-{id}-{slug}">.
            # The anchor's content is sometimes plain text, sometimes
            # just an <img>. When there's no inner text, fall back to
            # turning the URL slug into a readable title.
            seen_ids: set[str] = set()
            results: list[SearchResult] = []
            for anchor in soup.find_all("a", href=True):
                match = _DOWNLOAD3_RE.search(anchor["href"])
                if not match:
                    continue
                fid, slug = match.group(1), match.group(2)
                if fid in seen_ids:
                    continue
                seen_ids.add(fid)
                title = anchor.get_text(strip=True) or _slug_to_title(slug)
                results.append(
                    SearchResult(
                        id=f"freemidi_{hashlib.sha1(fid.encode()).hexdigest()[:6]}",
                        title=title,
                        source=self.source,
                        source_url=f"https://freemidi.org{anchor['href']}",
                        download_url=f"https://freemidi.org/getter-{fid}",
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
