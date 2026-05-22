"""QQ Music audio source.

Wraps the qqmusic-api-python community library. Most tracks are
paywalled; we surface those as SourceUnavailable.
"""
from __future__ import annotations

import asyncio
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
    def search(self, keyword: str, limit: int) -> dict[str, Any]: ...
    def get_audio_url(self, song_mid: str) -> Optional[str]: ...
    async def download(self, url: str, target: Path) -> None: ...


class _DefaultClient:
    def search(self, keyword: str, limit: int) -> dict[str, Any]:
        from qqmusic_api import search as qsearch  # noqa: WPS433
        return qsearch.search_by_type(keyword, num=limit)

    def get_audio_url(self, song_mid: str) -> Optional[str]:
        from qqmusic_api import song as qsong  # noqa: WPS433
        urls = qsong.get_song_urls([song_mid])
        return urls.get(song_mid) if isinstance(urls, dict) else None

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


class QQMusicSource(AbstractAudioSource):
    source = AudioSourceKey.QQMUSIC

    def __init__(self, *, client: Optional[_ClientProtocol] = None) -> None:
        self._client = client or _DefaultClient()

    async def _do_search(self, query: str, limit: int) -> list[AudioCandidate]:
        result = await asyncio.to_thread(self._client.search, query, limit)
        songs = (((result or {}).get("data") or {}).get("song") or {}).get("list") or []
        out: list[AudioCandidate] = []
        for s in songs[:limit]:
            mid = str(s.get("songmid") or s.get("mid") or "")
            if not mid:
                continue
            singers = s.get("singer") or []
            artist = singers[0].get("name") if singers else None
            interval = s.get("interval")
            out.append(
                AudioCandidate(
                    source=self.source,
                    candidate_id=mid,
                    title=str(s.get("songname") or s.get("title") or "Untitled"),
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
            audio_url = await asyncio.to_thread(self._client.get_audio_url, mid)
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
