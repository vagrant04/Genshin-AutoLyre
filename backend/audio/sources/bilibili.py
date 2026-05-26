"""Bilibili audio source.

Search uses Bilibili's official web search API directly (not yt-dlp's
`bilisearch:` prefix), because the latter mixes plain videos with
Cheese (paid course) URLs and flat-mode AV ids — both of which break
yt-dlp's BiliBili extractor when we later try to fetch them.

Download still uses yt-dlp, which handles the BV → CID → playurl flow
correctly when given a clean BVID URL with browser headers and
adequate retries / timeouts.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Any, Callable, Optional

import httpx

from audio.exceptions import SourceUnavailable
from audio.sources.base import AbstractAudioSource
from config import AudioCandidate, AudioMetadata, AudioSourceKey

_LOG = logging.getLogger(__name__)

# Bilibili rejects requests without a browser-shaped UA + Referer
# (HTTP 412). yt-dlp's extractor doesn't set these by default.
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com/",
}

_SEARCH_API = "https://api.bilibili.com/x/web-interface/search/all/v2"

# yt-dlp returns inline <em class="keyword">...</em> markup in titles.
_TAG_RE = re.compile(r"<[^>]+>")


def _default_factory(params: dict[str, Any]):
    import yt_dlp  # noqa: WPS433
    return yt_dlp.YoutubeDL(params)


def _default_http_client_factory() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=15.0, follow_redirects=True)


class BilibiliSource(AbstractAudioSource):
    source = AudioSourceKey.BILIBILI

    def __init__(
        self,
        *,
        ydl_factory: Callable[[dict[str, Any]], Any] = _default_factory,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._factory = ydl_factory
        # If a client is passed (tests), reuse it. Otherwise lazy-create
        # one per search() call so we don't keep an idle connection.
        self._http_client = http_client

    async def _do_search(self, query: str, limit: int) -> list[AudioCandidate]:
        own_client = self._http_client is None
        client = self._http_client or _default_http_client_factory()
        try:
            search_headers = {
                **_BROWSER_HEADERS,
                "Accept": "application/json, text/plain, */*",
                "Origin": "https://www.bilibili.com",
            }
            response = await client.get(
                _SEARCH_API,
                params={"keyword": query},
                headers=search_headers,
            )
            if response.status_code != 200:
                raise SourceUnavailable(
                    f"bilibili search HTTP {response.status_code}"
                )
            payload = response.json()
        finally:
            if own_client:
                await client.aclose()

        videos = self._extract_video_section(payload)
        out: list[AudioCandidate] = []
        for item in videos[:limit]:
            bvid = item.get("bvid") or ""
            if not bvid:
                continue
            title = _TAG_RE.sub("", str(item.get("title") or "Untitled"))
            duration = _parse_duration(item.get("duration"))
            thumbnail = item.get("pic") or None
            if thumbnail and thumbnail.startswith("//"):
                thumbnail = "https:" + thumbnail
            out.append(
                AudioCandidate(
                    source=self.source,
                    candidate_id=bvid,
                    title=title,
                    artist=item.get("author") or item.get("up_name"),
                    duration_seconds=duration,
                    thumbnail_url=thumbnail,
                    canonical_url=f"https://www.bilibili.com/video/{bvid}",
                )
            )
        return out

    @staticmethod
    def _extract_video_section(payload: dict) -> list[dict]:
        """Pull the `video` results out of the multi-section search response.

        The API returns `{data: {result: [{result_type: 'video', data: [...]}, ...]}}`
        in newer shapes, or `{data: {result: [{type: 'video', data: [...]}, ...]}}`
        in older shapes. Handle both.
        """
        result_list = (payload.get("data") or {}).get("result") or []
        for section in result_list:
            kind = section.get("result_type") or section.get("type")
            if kind == "video":
                return section.get("data") or []
        return []

    async def fetch_to_path(self, url: str, target: Path) -> AudioMetadata:
        target.parent.mkdir(parents=True, exist_ok=True)
        params: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "format": "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio*/best",
            "outtmpl": str(target),
            "noplaylist": True,
            "http_headers": dict(_BROWSER_HEADERS),
            "socket_timeout": 60,
            # Bilibili's metadata endpoint occasionally times out under
            # load. yt-dlp's `extractor_retries` re-runs the extraction
            # transparently; `retries` covers actual download retries.
            "extractor_retries": 5,
            "retries": 5,
            "fragment_retries": 5,
        }
        sessdata = os.environ.get("BILI_SESSDATA")
        if sessdata:
            params["http_headers"]["Cookie"] = f"SESSDATA={sessdata}"
        try:
            info = await asyncio.to_thread(self._extract, params, url, True)
        except SourceUnavailable:
            target.unlink(missing_ok=True)
            raise
        except Exception as exc:  # noqa: BLE001
            target.unlink(missing_ok=True)
            raise SourceUnavailable(f"yt-dlp/bilibili failed: {exc}") from exc
        if not target.is_file():
            raise SourceUnavailable(
                "yt-dlp/bilibili did not produce expected output"
            )
        info_dict = info or {}
        raw_duration = info_dict.get("duration")
        return AudioMetadata(
            source=self.source,
            canonical_url=str(info_dict.get("webpage_url") or url),
            title=str(info_dict.get("title") or target.stem),
            duration_seconds=int(raw_duration) if raw_duration else None,
            file_path=str(target),
            file_size_bytes=target.stat().st_size,
        )

    def _extract(
        self,
        params: dict[str, Any],
        query: str,
        download: bool,
    ) -> dict[str, Any] | None:
        try:
            with self._factory(params) as ydl:
                return ydl.extract_info(query, download=download)
        except Exception as exc:  # noqa: BLE001
            raise SourceUnavailable(str(exc)) from exc


def _parse_duration(raw: Any) -> Optional[int]:
    """The video search API returns duration as 'M:SS' (or 'H:MM:SS').
    Older endpoints returned an integer; handle both."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return int(raw)
    if isinstance(raw, str) and ":" in raw:
        try:
            parts = [int(x) for x in raw.split(":")]
        except ValueError:
            return None
        seconds = 0
        for part in parts:
            seconds = seconds * 60 + part
        return seconds
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None
