"""QQ Music audio source.

Wraps the qqmusic-api-python community library. The library's public
functions are decorated to return coroutines even though their
signatures look synchronous (qqmusic_api.utils.network.ApiRequest);
both `search.search_by_type` and `song.get_song_urls` must be awaited.

Most tracks are paywalled — we surface those as SourceUnavailable.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
import re
from pathlib import Path
from typing import Any, Optional, Protocol

import httpx

from audio.exceptions import SourceUnavailable
from audio.sources.base import AbstractAudioSource
from config import AudioCandidate, AudioMetadata, AudioSourceKey

_LOG = logging.getLogger(__name__)
_MID_RE = re.compile(r"songDetail/([A-Za-z0-9]+)")


class _ClientProtocol(Protocol):
    """Protocol for the qqmusic client. Implementations may return
    plain values OR awaitables; QQMusicSource handles both."""
    def search(self, keyword: str, limit: int) -> Any: ...
    def get_audio_url(self, song_mid: str) -> Any: ...
    async def download(self, url: str, target: Path) -> None: ...


class _DefaultClient:
    async def search(self, keyword: str, limit: int) -> dict[str, Any]:
        from qqmusic_api import search as qsearch  # noqa: WPS433
        # search_by_type is decorated by qqmusic_api.utils.network and
        # returns a coroutine even though its signature looks sync.
        return await qsearch.search_by_type(keyword, num=limit)

    async def get_audio_url(self, song_mid: str) -> Optional[str]:
        from qqmusic_api import song as qsong  # noqa: WPS433
        urls = await qsong.get_song_urls([song_mid])
        if not isinstance(urls, dict):
            return None
        value = urls.get(song_mid)
        if isinstance(value, tuple):
            # Some result types return (url, vkey) tuples; first element
            # is always the URL.
            value = value[0] if value else None
        return value or None

    async def download(self, url: str, target: Path) -> None:
        try:
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as c:
                async with c.stream("GET", url) as r:
                    if r.status_code != 200:
                        raise SourceUnavailable(f"qq HTTP {r.status_code}")
                    with target.open("wb") as fh:
                        async for chunk in r.aiter_bytes():
                            fh.write(chunk)
        except Exception:
            target.unlink(missing_ok=True)
            raise


async def _maybe_await(value: Any) -> Any:
    """Return `value`, awaiting if it's an awaitable. Lets test stubs
    return plain dicts while production clients return coroutines."""
    if inspect.isawaitable(value):
        return await value
    return value


class QQMusicSource(AbstractAudioSource):
    source = AudioSourceKey.QQMUSIC

    def __init__(self, *, client: Optional[_ClientProtocol] = None) -> None:
        self._client = client or _DefaultClient()

    async def _do_search(self, query: str, limit: int) -> list[AudioCandidate]:
        result = await _maybe_await(self._client.search(query, limit))
        # qqmusic-api-python's modern API returns a flat list[dict] of
        # song records. Older versions and our test stubs return a
        # nested {"data": {"song": {"list": [...]}}} envelope. Handle
        # both.
        if isinstance(result, list):
            songs = result
        elif isinstance(result, dict):
            songs = (((result or {}).get("data") or {}).get("song") or {}).get("list") or []
            if not songs:
                songs = result.get("list") or []
        else:
            songs = []
        out: list[AudioCandidate] = []
        for s in songs[:limit]:
            mid = str(s.get("mid") or s.get("songmid") or "")
            if not mid:
                continue
            singers = s.get("singer") or []
            artist = singers[0].get("name") if singers else None
            interval = s.get("interval")
            out.append(
                AudioCandidate(
                    source=self.source,
                    candidate_id=mid,
                    title=str(s.get("title") or s.get("name") or s.get("songname") or "Untitled"),
                    artist=artist,
                    duration_seconds=int(interval) if interval else None,
                    thumbnail_url=None,
                    canonical_url=f"https://y.qq.com/n/ryqq/songDetail/{mid}",
                )
            )
        return out

    async def fetch_to_path(self, url: str, target: Path) -> AudioMetadata:
        match = _MID_RE.search(url)
        if not match:
            raise SourceUnavailable(f"cannot extract QQ song mid from {url}")
        mid = match.group(1)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            audio_url = await _maybe_await(self._client.get_audio_url(mid))
        except Exception as exc:  # noqa: BLE001
            raise SourceUnavailable(f"qq get_audio_url failed: {exc}") from exc
        if not audio_url:
            raise SourceUnavailable(
                "QQ track requires VIP / payment or is region-blocked"
            )
        try:
            await self._client.download(audio_url, target)
        except SourceUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001
            raise SourceUnavailable(f"qq download failed: {exc}") from exc
        return AudioMetadata(
            source=self.source,
            canonical_url=url,
            title=f"QQ {mid}",
            file_path=str(target),
            file_size_bytes=target.stat().st_size,
        )
