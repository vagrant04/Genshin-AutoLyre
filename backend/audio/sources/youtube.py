"""YouTube audio source via yt-dlp.

`search()` uses the `ytsearch{N}:` prefix; `fetch_to_path()` does a
single-URL extract with `bestaudio` and writes the audio to the
provided target path.

`ydl_factory` is injected so tests can substitute a stub. In production,
use the default factory which returns a real `yt_dlp.YoutubeDL`.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Callable

from audio.exceptions import SourceUnavailable
from audio.sources.base import AbstractAudioSource
from config import AudioCandidate, AudioMetadata, AudioSourceKey

_LOG = logging.getLogger(__name__)


def _default_factory(params: dict[str, Any]):
    import yt_dlp  # noqa: WPS433
    return yt_dlp.YoutubeDL(params)


class YouTubeSource(AbstractAudioSource):
    source = AudioSourceKey.YOUTUBE

    def __init__(
        self,
        *,
        ydl_factory: Callable[[dict[str, Any]], Any] = _default_factory,
    ) -> None:
        self._factory = ydl_factory

    async def _do_search(self, query: str, limit: int) -> list[AudioCandidate]:
        params = {
            "quiet": True,
            "skip_download": True,
            "extract_flat": "in_playlist",
            "default_search": "ytsearch",
        }
        info = await asyncio.to_thread(
            self._extract, params, f"ytsearch{limit}:{query}", False
        )
        entries = (info or {}).get("entries") or []
        out: list[AudioCandidate] = []
        for e in entries[:limit]:
            if not isinstance(e, dict):
                continue
            vid = e.get("id") or ""
            if not vid:
                continue
            out.append(
                AudioCandidate(
                    source=self.source,
                    candidate_id=vid,
                    title=str(e.get("title") or "Untitled"),
                    artist=e.get("uploader"),
                    duration_seconds=e.get("duration"),
                    thumbnail_url=e.get("thumbnail"),
                    canonical_url=e.get("webpage_url")
                    or f"https://www.youtube.com/watch?v={vid}",
                )
            )
        return out

    async def fetch_to_path(self, url: str, target: Path) -> AudioMetadata:
        target.parent.mkdir(parents=True, exist_ok=True)
        params = {
            "quiet": True,
            "no_warnings": True,
            "format": "bestaudio/best",
            "outtmpl": str(target),
            "noplaylist": True,
            "postprocessors": [],
        }
        try:
            info = await asyncio.to_thread(self._extract, params, url, True)
        except SourceUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001
            raise SourceUnavailable(f"yt-dlp failed: {exc}") from exc
        if not target.is_file():
            raise SourceUnavailable(
                "yt-dlp did not produce the expected output file"
            )
        return AudioMetadata(
            source=self.source,
            canonical_url=str((info or {}).get("webpage_url") or url),
            title=str((info or {}).get("title") or target.stem),
            duration_seconds=(info or {}).get("duration"),
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
