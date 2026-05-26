"""bilibili.com searcher.

Spec §8.1.5:
  - Query: "{user_query} 原神 原琴 MIDI"
  - Web search API; Referer must be bilibili.com
  - download_url is extracted from the video description with a regex
    that matches pan.baidu.com / github.com / *.mid|*.midi URLs
"""
from __future__ import annotations

import hashlib
import re

import httpx

from config import MusicSource, SearchResult
from search.base import BaseMusicSearcher

_DOWNLOAD_RE = re.compile(
    r"https?://[^\s,)]+?(?:pan\.baidu\.com|github\.com)[^\s,)]*"
    r"|https?://[^\s,)]+?\.midi?\b",
    flags=re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")


class BilibiliSearcher(BaseMusicSearcher):
    source = MusicSource.BILIBILI

    def __init__(self, *, client: httpx.AsyncClient | None = None) -> None:
        self._client = client
        self._owns_client = client is None

    async def _do_search(self, query: str, limit: int) -> list[SearchResult]:
        keyword = f"{query} 原神 原琴 MIDI"
        url = "https://api.bilibili.com/x/web-interface/search/all/v2"
        params = {"keyword": keyword}
        headers = {
            "Referer": "https://www.bilibili.com/",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://www.bilibili.com",
        }
        client = self._client or httpx.AsyncClient(timeout=10.0)
        try:
            response = await client.get(url, params=params, headers=headers)
            if response.status_code != 200:
                raise RuntimeError(f"HTTP {response.status_code}")
            data = response.json()
            video_data = self._extract_video_section(data)
            results: list[SearchResult] = []
            for item in video_data[:limit]:
                bvid = item.get("bvid") or ""
                title = _TAG_RE.sub("", str(item.get("title", "Untitled")))
                description = str(item.get("description", ""))
                match = _DOWNLOAD_RE.search(description)
                download_url = match.group(0) if match else None
                results.append(
                    SearchResult(
                        id=f"bilibili_{hashlib.sha1(bvid.encode()).hexdigest()[:6]}",
                        title=title,
                        source=self.source,
                        source_url=f"https://www.bilibili.com/video/{bvid}",
                        download_url=download_url,
                        score=0.6 if download_url else 0.4,
                    )
                )
            return results
        finally:
            if self._owns_client:
                await client.aclose()

    @staticmethod
    def _extract_video_section(payload: dict) -> list[dict]:
        result_list = (payload.get("data") or {}).get("result") or []
        for section in result_list:
            # The API uses `result_type` in current responses; older
            # `type` is kept as a fallback.
            kind = section.get("result_type") or section.get("type")
            if kind == "video":
                return section.get("data") or []
        return []

    async def get_download_url(self, result: SearchResult) -> str:
        if not result.download_url:
            raise ValueError("Bilibili result has no extractable download URL")
        return result.download_url
